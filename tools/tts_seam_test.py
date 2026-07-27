"""Measure how audible a per-shot voiceover's seams are.

Today one ElevenLabs request voices the whole reel, so editing any shot
regenerates the whole take — and every avatar clip lip-synced against the old
one dies with it. Voicing shot by shot would make an untouched shot's audio
byte-identical across renders (its clip survives), but only if the joins
between chunks are inaudible.

Three versions of the same script get compared:

  single   one request for the whole narration (what production does today)
  naive    one request per shot, concatenated as-is
  leveled  the same chunks, each matched to one loudness target first

"Audible" needs a yardstick, so the control group comes from the audio itself:
inside one continuous take the voice already changes loudness, pitch and pace
from sentence to sentence, and nobody hears a splice. Measure that natural
step, then compare the step across a shot join to it. A join that lands inside
the natural distribution is a join nobody can hear.

Costs a few ElevenLabs cents (--reuse re-runs the analysis for free). Touches
no fal.ai model.
"""

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx  # noqa: E402

from saasshorts import ELEVENLABS_API_BASE  # noqa: E402

# PCM keeps concatenation honest: joining mp3 files inserts each file's encoder
# delay as a gap, which would show up as a "seam artifact" we invented ourselves.
# Highest rate first — the lower ones exist on every ElevenLabs tier.
PCM_FORMATS = (("pcm_44100", 44100), ("pcm_24000", 24000), ("pcm_22050", 22050))
TARGET_LUFS = -16.0
UNSUPPORTED = []


# ---------------------------------------------------------------- generation

def resolve_key(user_email: str = "") -> str:
    """The ElevenLabs key the app itself would use. Never printed, only returned."""
    for env_name in ("ELEVENLABS_API_KEY", "ELEVENLABS_KEY"):
        if os.environ.get(env_name):
            return os.environ[env_name]
    from app import _auth_db, get_user_api_key

    with _auth_db() as conn:
        rows = conn.execute("SELECT id, email FROM users ORDER BY created_at").fetchall()
    for row in rows:
        if user_email and row["email"] != user_email:
            continue
        key = get_user_api_key(row["id"], "elevenlabs")
        if key:
            print(f"[key] Using the ElevenLabs key saved by {row['email']}.")
            return key
    raise SystemExit("No ElevenLabs key found in env or in any user's saved keys.")


def load_shots(job_dir: str) -> tuple:
    with open(os.path.join(job_dir, "gallery_metadata.json"), encoding="utf-8") as f:
        meta = json.load(f)
    shots = [
        (shot.get("speech") or "").strip()
        for shot in (meta.get("shots") or [])
        if (shot.get("speech") or "").strip()
    ]
    voice_id = ""
    for name in os.listdir(job_dir):
        if name.endswith("_voice.mp3.meta.json"):
            with open(os.path.join(job_dir, name), encoding="utf-8") as f:
                voice_id = (json.load(f).get("voice_id") or "").strip()
            break
    return meta.get("title") or "", shots, voice_id


def tts(text, key, voice_id, previous_text="", next_text=""):
    """One ElevenLabs call in production's settings. Returns (samples, rate).

    Continuity parameters are optional on purpose: the model behind our approved
    voice may refuse them, and the point is to learn which ones survive rather
    than to die on the first refusal.
    """
    body = {"text": text, "model_id": "eleven_v3", "voice_settings": {"stability": 0.0}}
    if previous_text:
        body["previous_text"] = previous_text
    if next_text:
        body["next_text"] = next_text

    headers = {"xi-api-key": key, "Content-Type": "application/json"}
    last_error = ""
    with httpx.Client(timeout=300.0) as client:
        for fmt, rate in PCM_FORMATS:
            url = f"{ELEVENLABS_API_BASE}/text-to-speech/{voice_id}?output_format={fmt}"
            for _ in range(2):
                resp = client.post(url, headers=headers, json=body)
                if resp.status_code == 200:
                    pcm = np.frombuffer(resp.content, dtype="<i2").astype(np.float32) / 32768.0
                    return pcm, rate
                last_error = f"{resp.status_code}: {resp.text[:200]}"
                if resp.status_code == 400 and "unsupported_model" in resp.text:
                    dropped = [k for k in ("previous_text", "next_text") if k in body]
                    for name in dropped:
                        body.pop(name)
                        if name not in UNSUPPORTED:
                            UNSUPPORTED.append(name)
                    continue
                break
            # Only a format the account cannot reach is worth retrying smaller.
            if "output_format" not in last_error and "422" not in last_error:
                break
    raise SystemExit(f"ElevenLabs refused the request ({last_error})")


def write_wav(path, samples, rate):
    clipped = np.clip(samples, -1.0, 1.0)
    with wave.open(path, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes((clipped * 32767).astype("<i2").tobytes())


def read_wav(path):
    with wave.open(path, "rb") as f:
        data = f.readframes(f.getnframes())
        return np.frombuffer(data, dtype="<i2").astype(np.float32) / 32768.0, f.getframerate()


# ----------------------------------------------------------------- measuring

def lufs(samples, rate):
    """Integrated loudness (EBU R128) of a piece of audio, via ffmpeg."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        write_wav(tmp_path, samples, rate)
        proc = subprocess.run(
            ["ffmpeg", "-nostdin", "-i", tmp_path, "-af",
             "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"],
            capture_output=True, text=True,
        )
        # The JSON block is followed by ffmpeg's own summary lines, so it has to
        # be cut at its closing brace — feeding the rest to json.loads fails.
        marker = proc.stderr.rfind('"input_i"')
        if marker < 0:
            return float("nan")
        start = proc.stderr.rfind("{", 0, marker)
        end = proc.stderr.find("}", marker)
        try:
            return float(json.loads(proc.stderr[start:end + 1])["input_i"])
        except (ValueError, KeyError, json.JSONDecodeError):
            return float("nan")
    finally:
        os.unlink(tmp_path)


def envelope(samples, rate, win_ms=10):
    win = max(1, int(rate * win_ms / 1000))
    usable = len(samples) - len(samples) % win
    frames = samples[:usable].reshape(-1, win)
    return np.sqrt((frames ** 2).mean(axis=1) + 1e-12), win


def speech_segments(samples, rate, min_pause_ms=180, min_speech_ms=300):
    """Stretches of speech separated by pauses, as (start, end) sample indices."""
    env, win = envelope(samples, rate)
    floor = max(np.percentile(env, 15) * 3, env.max() * 0.02)
    loud = env > floor
    pause_frames = int(min_pause_ms / 10)

    segments, start = [], None
    quiet_run = 0
    for i, is_loud in enumerate(loud):
        if is_loud:
            if start is None:
                start = i
            quiet_run = 0
        elif start is not None:
            quiet_run += 1
            if quiet_run >= pause_frames:
                segments.append((start * win, (i - quiet_run) * win))
                start = None
    if start is not None:
        segments.append((start * win, len(loud) * win))
    return [(a, b) for a, b in segments if (b - a) / rate * 1000 >= min_speech_ms]


def median_f0(samples, rate):
    """Median pitch across the voiced frames of a segment, in Hz. 0 when unvoiced.

    Normalised autocorrelation with an octave-error guard: the raw peak often
    lands on twice the true period, which would report a jump of an octave where
    the voice never moved.
    """
    step = max(1, rate // 8000)  # 8 kHz resolves 80-350 Hz with a short lag search
    sig = samples[::step].astype(np.float64)
    rate_ds = rate / step
    win = int(rate_ds * 0.04)
    if len(sig) < win * 2:
        return 0.0
    lo, hi = int(rate_ds / 350), int(rate_ds / 80)

    pitches = []
    for start in range(0, len(sig) - win, win // 2):
        frame = sig[start:start + win]
        frame = frame - frame.mean()
        if np.sqrt((frame ** 2).mean()) < 0.01:
            continue
        corr = np.correlate(frame, frame, mode="full")[len(frame) - 1:]
        energy = corr[0]
        if energy <= 0:
            continue
        window = corr[lo:hi] / energy
        if not len(window):
            continue
        lag = int(np.argmax(window)) + lo
        if corr[lag] / energy < 0.35:
            continue
        half = lag // 2
        if half >= lo and corr[half] / energy > 0.8 * (corr[lag] / energy):
            lag = half
        pitches.append(rate_ds / lag)
    return float(np.median(pitches)) if pitches else 0.0


def syllable_rate(samples, rate):
    """Syllables per second, counted as peaks of the loudness envelope.

    A proxy, not a phonetic count — but a consistent one, which is all that a
    comparison of pace across a join needs.
    """
    env, win = envelope(samples, rate, win_ms=20)
    if len(env) < 3:
        return 0.0
    smooth = np.convolve(env, np.ones(3) / 3, mode="same")
    threshold = smooth.max() * 0.25
    peaks, last = 0, -99
    for i in range(1, len(smooth) - 1):
        if smooth[i] > threshold and smooth[i] >= smooth[i - 1] and smooth[i] > smooth[i + 1]:
            if i - last >= 5:  # 100 ms apart: no syllable is shorter
                peaks += 1
                last = i
    return peaks / (len(env) * win / rate)


def trim_silence(samples, rate):
    """Drop the silence each take carries at its edges, so joins are predictable."""
    env, win = envelope(samples, rate)
    floor = max(np.percentile(env, 15) * 3, env.max() * 0.02)
    loud = np.flatnonzero(env > floor)
    if not len(loud):
        return samples
    return samples[loud[0] * win:min(len(samples), (loud[-1] + 1) * win)]


def join_takes(chunks, rate, pause_ms, target_lufs=TARGET_LUFS):
    """Concatenate separate takes the way an editor would.

    Two takes butt together with whatever silence each happened to end and start
    with — in practice near zero, which reads as the speaker gasping through a
    full stop. So: trim both edges, match loudness, and put back a pause of the
    length this voice takes between sentences anyway.
    """
    silence = np.zeros(int(rate * pause_ms / 1000), dtype=np.float32)
    pieces = []
    for chunk in chunks:
        trimmed = trim_silence(chunk, rate)
        measured = lufs(trimmed, rate)
        gain = 10 ** ((target_lufs - measured) / 20) if measured == measured else 1.0
        pieces.append(trimmed * gain)
    joined, boundaries = [pieces[0]], []
    for piece in pieces[1:]:
        boundaries.append(sum(len(p) for p in joined) + len(silence) // 2)
        joined.extend([silence, piece])
    return np.concatenate(joined), boundaries


def segment_profile(samples, rate, segment):
    start, end = segment
    piece = samples[start:end]
    return {
        "lufs": lufs(piece, rate),
        "f0": median_f0(piece, rate),
        "rate": syllable_rate(piece, rate),
        "start": start / rate,
        "end": end / rate,
    }


def step_between(left, right):
    """How far the voice moves between two neighbouring speech segments."""
    semitones = (
        abs(12 * math.log2(right["f0"] / left["f0"]))
        if left["f0"] > 0 and right["f0"] > 0 else float("nan")
    )
    return {
        "loudness_db": abs(right["lufs"] - left["lufs"]),
        "pitch_st": semitones,
        "pace_pct": abs(right["rate"] - left["rate"]) / max(left["rate"], 1e-6) * 100,
        "pause_ms": (right["start"] - left["end"]) * 1000,
    }


METRICS = (("loudness_db", "dB"), ("pitch_st", "st"), ("pace_pct", "%"), ("pause_ms", "ms"))


def analyse(samples, rate, boundaries=()):
    """Profile every speech segment and label the steps that cross a chunk join."""
    segments = speech_segments(samples, rate)
    profiles = [segment_profile(samples, rate, s) for s in segments]
    steps = []
    for i in range(len(profiles) - 1):
        gap_start, gap_end = segments[i][1], segments[i + 1][0]
        crossed = [b for b in boundaries if gap_start <= b <= gap_end]
        steps.append({
            **step_between(profiles[i], profiles[i + 1]),
            "seam": bool(crossed),
            "mid_phrase_seam": False,
            "at": profiles[i]["end"],
        })

    # Two takes can butt together with no pause between them, in which case no
    # pair of segments straddles the join and it would be measured as nothing at
    # all. That is the harshest kind of join, so measure it head-on: the speech
    # just before against the speech just after.
    window = int(rate * 1.2)
    for boundary in boundaries:
        containing = next((s for s in segments if s[0] < boundary < s[1]), None)
        if not containing:
            continue
        left = (max(containing[0], boundary - window), boundary)
        right = (boundary, min(containing[1], boundary + window))
        if left[1] - left[0] < rate // 4 or right[1] - right[0] < rate // 4:
            continue
        steps.append({
            **step_between(segment_profile(samples, rate, left),
                           segment_profile(samples, rate, right)),
            "seam": True,
            "mid_phrase_seam": True,
            "at": boundary / rate,
        })
    steps.sort(key=lambda s: s["at"])
    return profiles, steps


def describe(label, steps):
    print(f"\n  {label} ({len(steps)} steps)")
    stats = {}
    for metric, unit in METRICS:
        values = np.array([s[metric] for s in steps if s[metric] == s[metric]])
        if not len(values):
            continue
        stats[metric] = {
            "median": float(np.median(values)),
            "p90": float(np.percentile(values, 90)),
            "max": float(values.max()),
        }
        print(f"    {metric:<12} median {np.median(values):7.2f}{unit:<3}"
              f" p90 {np.percentile(values, 90):7.2f}{unit:<3}"
              f" max {values.max():7.2f}{unit}")
    return stats


# ---------------------------------------------------------------------- main

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-dir", default="output/saas_feddb8e4-f627-4f1d-a626-cc59562c2275")
    parser.add_argument("--out-dir", default="output/tts_seam_test")
    parser.add_argument("--user-email", default="")
    parser.add_argument("--reuse", action="store_true", help="re-analyse audio already on disk")
    parser.add_argument(
        "--split-after", type=int, default=2,
        help="voice shots 1..N as one request and the rest as another — what an edit "
             "actually produces, where only the edited boundary is a seam",
    )
    args = parser.parse_args()

    title, shots, voice_id = load_shots(args.job_dir)
    if len(shots) < 2:
        raise SystemExit("Need at least two shots with speech.")
    print(f"Script: {title} — {len(shots)} shots, voice {voice_id}")
    os.makedirs(args.out_dir, exist_ok=True)

    chunk_paths = [os.path.join(args.out_dir, f"chunk_{i + 1:02d}.wav") for i in range(len(shots))]
    single_path = os.path.join(args.out_dir, "single.wav")
    # The two halves of an edit: what was voiced before it, and what was added.
    run_texts = [" ".join(shots[:args.split_after]), " ".join(shots[args.split_after:])]
    run_paths = [os.path.join(args.out_dir, f"run_{i + 1:02d}.wav") for i in range(2)]

    if args.reuse:
        single, rate = read_wav(single_path)
        chunks = [read_wav(p)[0] for p in chunk_paths]
        print(f"[reuse] Loaded {len(chunks)} chunks and the single take from disk.")
    else:
        key = resolve_key(args.user_email)
        print(f"[1/2] single: one request, {len(' '.join(shots))} chars.")
        single, rate = tts(" ".join(shots), key, voice_id)
        write_wav(single_path, single, rate)
        print(f"[2/2] per shot: {len(shots)} requests, with neighbouring text as context.")
        chunks = []
        for i, text in enumerate(shots):
            chunk, _ = tts(
                text, key, voice_id,
                previous_text=" ".join(shots[:i])[-600:] if "previous_text" not in UNSUPPORTED else "",
                next_text=" ".join(shots[i + 1:])[:600] if "next_text" not in UNSUPPORTED else "",
            )
            chunks.append(chunk)
            write_wav(chunk_paths[i], chunk, rate)
        if UNSUPPORTED:
            print(f"      eleven_v3 refused: {', '.join(UNSUPPORTED)} — chunks carry no context.")

    if args.reuse and all(os.path.exists(p) for p in run_paths):
        runs = [read_wav(p)[0] for p in run_paths]
    else:
        print(f"[3/3] runs: shots 1-{args.split_after} and {args.split_after + 1}-{len(shots)} "
              "as two requests — one seam, the one an edit really creates.")
        runs = []
        for i, text in enumerate(run_texts):
            piece, _ = tts(text, resolve_key(args.user_email), voice_id)
            runs.append(piece)
            write_wav(run_paths[i], piece, rate)

    # The proposal itself: same chunks, every one pinned to one loudness target.
    leveled = []
    for chunk in chunks:
        measured = lufs(chunk, rate)
        gain = 10 ** ((TARGET_LUFS - measured) / 20) if measured == measured else 1.0
        leveled.append(chunk * gain)

    # The pause this voice leaves between sentences on its own — the length a
    # join has to imitate to pass as one more sentence boundary.
    _, single_steps = analyse(single, rate)
    natural_pause = float(np.median([s["pause_ms"] for s in single_steps])) if single_steps else 400.0
    print(f"[pause] This voice pauses {natural_pause:.0f} ms between sentences; joins will copy that.")

    joins = np.cumsum([len(c) for c in chunks])[:-1]
    runs_fixed, runs_fixed_joins = join_takes(runs, rate, natural_pause)
    chunks_fixed, chunks_fixed_joins = join_takes(chunks, rate, natural_pause)
    variants = {
        "single": (single, ()),
        "naive": (np.concatenate(chunks), joins),
        "leveled": (np.concatenate(leveled), joins),
        "per_shot_fixed": (chunks_fixed, chunks_fixed_joins),
        "runs": (np.concatenate(runs), [len(runs[0])]),
        "runs_fixed": (runs_fixed, runs_fixed_joins),
    }

    result = {"shots": shots, "unsupported_params": UNSUPPORTED, "variants": {}}
    for name, (samples, boundaries) in variants.items():
        path = os.path.join(args.out_dir, f"{name}.wav")
        write_wav(path, samples, rate)
        profiles, steps = analyse(samples, rate, boundaries)
        print(f"\n=== {name}.wav — {len(samples) / rate:.2f}s, "
              f"{lufs(samples, rate):.1f} LUFS, {len(profiles)} speech segments")
        control = describe("steps inside a shot (control)", [s for s in steps if not s["seam"]])
        seams = [s for s in steps if s["seam"]]
        seam_stats = describe("steps across a shot join", seams) if seams else {}
        for step in seams:
            flags = [
                metric for metric, _ in METRICS
                if control.get(metric) and step[metric] == step[metric]
                and step[metric] > control[metric]["p90"]
            ]
            note = "ABOVE the natural step: " + ", ".join(flags) if flags else "within natural speech"
            if step["mid_phrase_seam"]:
                note += " (join falls mid-phrase)"
            print(f"    at {step['at']:5.2f}s  loud {step['loudness_db']:5.2f}dB"
                  f"  pitch {step['pitch_st']:5.2f}st  pace {step['pace_pct']:6.1f}%"
                  f"  pause {step['pause_ms']:6.0f}ms  → {note}")
        result["variants"][name] = {"control": control, "seams": seam_stats,
                                    "steps": steps, "duration": len(samples) / rate}

    with open(os.path.join(args.out_dir, "seams.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=float)
    print(f"\nWav files and seams.json are in {args.out_dir}")


if __name__ == "__main__":
    main()
