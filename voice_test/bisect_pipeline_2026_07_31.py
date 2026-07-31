"""Rebuild the same reel step by step, so the step that ruins it can be named.

A: the five takes as fal.ai delivered them, their own audio      (already built)
B: same takes, our master voiceover under them                   - nothing else
C: + our push-in
D: + our subtitles                                               (= *_our_cut)
E: the finished reel, with b-roll, subtitles and music           (as shipped)
F: the finished reel rebuilt with no subtitles and no music

    /opt/venv/bin/python /app/voice_test/bisect_pipeline_2026_07_31.py <job_dir> <out_dir>
"""
import glob
import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, "/app")
import saasshorts  # noqa: E402

HEAD = 1105 / 44100.0


def run(cmd):
    subprocess.run(cmd, check=True, capture_output=True)


def norm_chain():
    return ("scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920:(iw-ow)/2:(ih-oh)/2,fps=30,setsar=1")


def build_takes(job_dir, out_dir, slug, shots, push_in):
    """One file per talking shot: our slot, our master audio, optional push-in."""
    master = os.path.join(job_dir, f"{slug}_voice.mp3")
    parts = []
    talking_index = 0
    for shot in shots:
        n = int(shot["shot_number"])
        clip = os.path.join(job_dir, f"{slug}_avatar_{n:02d}.mp4")
        if not os.path.exists(clip):
            continue
        start, end = float(shot["start"]), float(shot["end"])
        window = end - start
        chain = norm_chain()
        if push_in:
            push = saasshorts._talking_push_in(talking_index, window)
            if push:
                chain += f",{push}"
        talking_index += 1
        piece = os.path.join(out_dir, f"_part_{n:02d}_{'push' if push_in else 'flat'}.mp4")
        run([
            "ffmpeg", "-v", "error", "-y",
            "-ss", f"{HEAD:.3f}", "-t", f"{window:.3f}", "-i", clip,
            "-ss", f"{start:.3f}", "-t", f"{window:.3f}", "-i", master,
            "-filter_complex", f"[0:v]{chain}[v]",
            "-map", "[v]", "-map", "1:a",
            "-c:v", "libx264", "-preset", "fast", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k", piece,
        ])
        parts.append(piece)
    return parts


def concat(parts, output):
    listing = output + ".txt"
    with open(listing, "w", encoding="utf-8") as f:
        for part in parts:
            f.write(f"file '{part}'\n")
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0",
         "-i", listing, "-c", "copy", output])
    os.remove(listing)
    for part in parts:
        os.remove(part)


def rebuild_without_subs(job_dir, out_dir, slug, shots):
    """The real composite, same clips, but no captions and no music bed."""
    empty_ass = os.path.join(out_dir, "_empty.ass")
    with open(empty_ass, "w", encoding="utf-8") as f:
        f.write("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n"
                "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, "
                "SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
                "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
                "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
                "Style: Subtitle,DejaVu Sans,72,&H00FFFFFF,&H000000FF,&H00000000,"
                "&H90000000,0,0,0,0,100,100,0,0,1,3,2,2,96,96,520,1\n\n"
                "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, "
                "MarginV, Effect, Text\n")
    clips = []
    for shot in shots:
        n = int(shot["shot_number"])
        talking = os.path.join(job_dir, f"{slug}_avatar_{n:02d}.mp4")
        broll = os.path.join(job_dir, f"{slug}_avatar_broll_{n:02d}.mp4")
        path = talking if os.path.exists(talking) else broll
        if not os.path.exists(path):
            continue
        clips.append({
            "path": path,
            "duration": float(shot["end"]) - float(shot["start"]),
            "shot": shot,
            "speech_offset": 0.0 if path == broll else HEAD,
        })
    output = os.path.join(out_dir, "variant_F_final_no_subs_no_music.mp4")
    saasshorts.composite_storyboard_video(
        clips, os.path.join(job_dir, f"{slug}_voice.mp3"), empty_ass, output,
    )
    os.remove(empty_ass)
    return output


def main(job_dir, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    master = glob.glob(os.path.join(job_dir, "*_voice.mp3"))[0]
    slug = os.path.basename(master)[: -len("_voice.mp3")]
    meta = json.load(open(os.path.join(job_dir, "gallery_metadata.json"), encoding="utf-8"))
    shots = sorted(meta["shots"], key=lambda s: int(s["shot_number"]))

    concat(build_takes(job_dir, out_dir, slug, shots, push_in=False),
           os.path.join(out_dir, "variant_B_takes_our_audio.mp4"))
    print("B done", flush=True)
    concat(build_takes(job_dir, out_dir, slug, shots, push_in=True),
           os.path.join(out_dir, "variant_C_takes_our_audio_push_in.mp4"))
    print("C done", flush=True)
    shutil.copy(os.path.join(job_dir, f"{slug}_storyboard_final.mp4"),
                os.path.join(out_dir, "variant_E_final_as_shipped.mp4"))
    print("E copied", flush=True)
    print(rebuild_without_subs(job_dir, out_dir, slug, shots), flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
