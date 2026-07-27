"""Estimate the lip-vs-sound offset of a clip from the pixels themselves.

No face landmarks: the mouth is found as the small block whose brightness
changes most over the clip (on a talking-head shot that is the mouth), then its
motion energy is correlated with the audio envelope at frame resolution.

Reported lag is (video - audio): positive = the mouth moves LATER than the
sound, negative = the mouth moves BEFORE the sound.
"""
import subprocess
import sys

import numpy as np

FPS = 30
SR = 16000
W, H = 96, 170  # small gray raster, keeps the 9:16 shape


def decode_video(path, start=None, duration=None):
    cmd = ["ffmpeg", "-v", "error"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", path]
    if duration is not None:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-vf", f"fps={FPS},scale={W}:{H},format=gray", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    n = len(raw) // (W * H)
    return np.frombuffer(raw[: n * W * H], dtype=np.uint8).reshape(n, H, W).astype(np.float64)


def decode_audio(path, start=None, duration=None):
    cmd = ["ffmpeg", "-v", "error"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", path]
    if duration is not None:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).astype(np.float64)


def audio_envelope(pcm, frames):
    """RMS per video frame; frames past the end of the audio are dropped."""
    hop = SR // FPS
    usable = min(frames, len(pcm) // hop)
    env = np.array([
        np.sqrt(np.mean(pcm[i * hop:(i + 1) * hop] ** 2) + 1e-12)
        for i in range(usable)
    ])
    return env


def mouth_roi(frames, block=12):
    """Block that flickers at syllable rate — the mouth, not hands or captions.

    Plain temporal variance picks whatever moves most (a hand, a caption card,
    a panning background). Speech articulation lives at 2.5-8 Hz, so score each
    block by the share of its temporal energy inside that band, and keep out of
    the bottom fifth of the frame where burned-in subtitles live.
    """
    n = frames.shape[0]
    detrended = frames - frames.mean(axis=0)
    spec = np.abs(np.fft.rfft(detrended, axis=0)) ** 2
    freqs = np.fft.rfftfreq(n, d=1.0 / FPS)
    band = (freqs >= 2.5) & (freqs <= 8.0)
    total = spec[1:].sum(axis=0) + 1e-9
    speechiness = spec[band].sum(axis=0) * (spec[band].sum(axis=0) / total)
    limit = int(H * 0.8)
    best, best_score = (0, 0), -1.0
    for y in range(0, limit - block, block // 2):
        for x in range(0, W - block, block // 2):
            score = speechiness[y:y + block, x:x + block].mean()
            if score > best_score:
                best, best_score = (y, x), score
    y, x = best
    return (slice(y, y + block), slice(x, x + block)), float(np.sqrt(best_score)), best


def zscore(x):
    x = np.asarray(x, dtype=np.float64)
    return (x - x.mean()) / (x.std() + 1e-12)


def best_lag(a, v, max_lag_frames=12):
    """Lag of v relative to a, in frames, allowing an inverted relationship."""
    a, v = zscore(a), zscore(v)
    n = min(len(a), len(v))
    a, v = a[:n], v[:n]
    results = []
    for lag in range(-max_lag_frames, max_lag_frames + 1):
        if lag >= 0:
            x, y = a[: n - lag], v[lag:]
        else:
            x, y = a[-lag:], v[: n + lag]
        if len(x) < FPS:
            continue
        r = float(np.corrcoef(x, y)[0, 1])
        results.append((lag, r))
    lags = np.array([r[0] for r in results])
    corrs = np.array([r[1] for r in results])
    idx = int(np.argmax(np.abs(corrs)))
    # parabolic refinement on |corr| for sub-frame resolution
    lag = float(lags[idx])
    if 0 < idx < len(corrs) - 1:
        y0, y1, y2 = np.abs(corrs[idx - 1]), np.abs(corrs[idx]), np.abs(corrs[idx + 1])
        denom = (y0 - 2 * y1 + y2)
        if denom != 0:
            lag += -0.5 * (y2 - y0) / denom
    return lag, float(corrs[idx]), list(zip(lags.tolist(), np.round(corrs, 3).tolist()))


def probe(path, label, start=None, duration=None, audio_path=None, verbose=False):
    frames = decode_video(path, start, duration)
    pcm = decode_audio(audio_path or path, start, duration)
    if frames.shape[0] < FPS or pcm.size < SR // 2:
        print(f"{label}: too short to measure")
        return
    env = audio_envelope(pcm, frames.shape[0])
    frames = frames[: len(env)]
    roi, roi_score, roi_pos = mouth_roi(frames)
    patch = frames[:, roi[0], roi[1]]
    motion = np.concatenate([[0.0], np.abs(np.diff(patch, axis=0)).mean(axis=(1, 2))])
    bright = patch.mean(axis=(1, 2))
    lag_m, r_m, _ = best_lag(env, motion)
    # brightness tracks openness, which tracks the envelope with the same timing
    lag_b, r_b, table = best_lag(env, bright)
    print(f"{label}: {frames.shape[0]} frames, roi std {roi_score:.1f} at "
          f"x={roi_pos[1]}/{W} y={roi_pos[0]}/{H}")
    print(f"    mouth motion vs audio: {lag_m * 1000 / FPS:+.0f} ms (r={r_m:+.2f})")
    print(f"    mouth brightness vs audio: {lag_b * 1000 / FPS:+.0f} ms (r={r_b:+.2f})")
    if verbose:
        print(f"    corr table (lag frames, r): {table}")


if __name__ == "__main__":
    args = sys.argv[1:]
    verbose = "-v" in args
    args = [a for a in args if a != "-v"]
    for spec in args:
        parts = spec.split("@")
        path = parts[0]
        start = duration = None
        if len(parts) > 1:
            start, duration = (float(x) for x in parts[1].split(":"))
        probe(path, path.split("/")[-1] + (f"@{start}" if start is not None else ""),
              start, duration, verbose=verbose)
