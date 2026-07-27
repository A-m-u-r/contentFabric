"""Measure a clip's lip-vs-sound offset from real face landmarks.

Mouth openness (inner lip gap, normalised by face height) against the audio
envelope. Unlike a brightness/motion block, this is actually the mouth, so the
lag it reports can be read as the real offset, not just a delta between two
renders of the same content.

Reported lag is (mouth - sound): positive = the mouth moves LATER than the
sound, negative = the mouth moves BEFORE it.

    python voice_test/lip_open_probe.py clip.mp4 [clip.mp4@start:duration ...]
"""
import subprocess
import sys

import numpy as np

FPS = 30
SR = 16000
W, H = 360, 640
UPPER_INNER_LIP, LOWER_INNER_LIP = 13, 14
FOREHEAD, CHIN = 10, 152


def _frames(path, start=None, duration=None):
    cmd = ["ffmpeg", "-v", "error"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", path]
    if duration is not None:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-vf", f"fps={FPS},scale={W}:{H}", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    n = len(raw) // (W * H * 3)
    return np.frombuffer(raw[: n * W * H * 3], dtype=np.uint8).reshape(n, H, W, 3)


def _audio(path, start=None, duration=None):
    cmd = ["ffmpeg", "-v", "error"]
    if start is not None:
        cmd += ["-ss", f"{start:.3f}"]
    cmd += ["-i", path]
    if duration is not None:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).astype(np.float64)


def mouth_openness(frames):
    """Inner lip gap per frame, normalised by face height. NaN where no face."""
    import mediapipe as mp

    mesh = mp.solutions.face_mesh.FaceMesh(
        static_image_mode=False, max_num_faces=1, refine_landmarks=True,
        min_detection_confidence=0.5, min_tracking_confidence=0.5,
    )
    values = []
    for frame in frames:
        result = mesh.process(frame)
        if not result.multi_face_landmarks:
            values.append(np.nan)
            continue
        pts = result.multi_face_landmarks[0].landmark
        gap = abs(pts[UPPER_INNER_LIP].y - pts[LOWER_INNER_LIP].y)
        face = abs(pts[FOREHEAD].y - pts[CHIN].y) or 1e-6
        values.append(gap / face)
    mesh.close()
    return np.array(values)


def _envelope(pcm, frames):
    hop = SR // FPS
    usable = min(frames, len(pcm) // hop)
    return np.array([
        np.sqrt(np.mean(pcm[i * hop:(i + 1) * hop] ** 2) + 1e-12) for i in range(usable)
    ])


def _fill_gaps(x):
    idx = np.arange(len(x))
    good = ~np.isnan(x)
    if good.sum() < 5:
        return None
    return np.interp(idx, idx[good], x[good])


def best_lag(sound, mouth, max_lag_frames=15):
    sound = (sound - sound.mean()) / (sound.std() + 1e-12)
    mouth = (mouth - mouth.mean()) / (mouth.std() + 1e-12)
    n = min(len(sound), len(mouth))
    sound, mouth = sound[:n], mouth[:n]
    table = []
    for lag in range(-max_lag_frames, max_lag_frames + 1):
        if lag >= 0:
            a, b = sound[: n - lag], mouth[lag:]
        else:
            a, b = sound[-lag:], mouth[: n + lag]
        if len(a) < FPS:
            continue
        table.append((lag, float(np.corrcoef(a, b)[0, 1])))
    lags = np.array([t[0] for t in table], dtype=float)
    corrs = np.array([t[1] for t in table])
    i = int(np.argmax(corrs))
    lag = lags[i]
    if 0 < i < len(corrs) - 1:
        y0, y1, y2 = corrs[i - 1], corrs[i], corrs[i + 1]
        denom = y0 - 2 * y1 + y2
        if denom != 0:
            lag += -0.5 * (y2 - y0) / denom
    return lag * 1000.0 / FPS, corrs[i], table


def probe(spec):
    path, start, duration = spec, None, None
    if "@" in spec:
        path, rng = spec.split("@")
        start, duration = (float(v) for v in rng.split(":"))
    frames = _frames(path, start, duration)
    pcm = _audio(path, start, duration)
    env = _envelope(pcm, len(frames))
    frames = frames[: len(env)]
    open_raw = mouth_openness(frames)
    tracked = int((~np.isnan(open_raw)).sum())
    mouth = _fill_gaps(open_raw)
    label = path.split("/")[-1] + (f"@{start}" if start is not None else "")
    if mouth is None:
        print(f"{label}: no face tracked")
        return
    lag, r, _ = best_lag(env, mouth)
    print(f"{label}: {len(frames)} frames, face on {tracked} of them")
    print(f"    mouth openness vs sound: {lag:+.0f} ms (r={r:+.2f})")


if __name__ == "__main__":
    for spec in sys.argv[1:]:
        probe(spec)
