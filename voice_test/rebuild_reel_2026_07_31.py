"""Re-assemble a finished job with the current composite, no paid calls.

Rebuilds the clip list the renderer would have passed and runs the real
`composite_storyboard_video`, so a change to the edit can be judged on a reel
that already exists.

    /opt/venv/bin/python /app/voice_test/rebuild_reel_2026_07_31.py <job_dir> <out.mp4>
"""
import glob
import json
import os
import sys

sys.path.insert(0, "/app")
import saasshorts  # noqa: E402


def main(job_dir, output_path, music=False):
    master = glob.glob(os.path.join(job_dir, "*_voice.mp3"))[0]
    slug = os.path.basename(master)[: -len("_voice.mp3")]
    subs = os.path.join(job_dir, f"{slug}_subs.ass")
    meta = json.load(open(os.path.join(job_dir, "gallery_metadata.json"), encoding="utf-8"))
    shots = sorted(meta["shots"], key=lambda s: int(s["shot_number"]))

    clips = []
    for shot in shots:
        n = int(shot["shot_number"])
        talking = os.path.join(job_dir, f"{slug}_avatar_{n:02d}.mp4")
        broll = os.path.join(job_dir, f"{slug}_avatar_broll_{n:02d}.mp4")
        path = talking if os.path.exists(talking) else broll
        if not os.path.exists(path):
            print(f"  shot {n}: no clip on disk, skipped")
            continue
        slice_audio = os.path.join(job_dir, f"{slug}_slice_{n:02d}.mp3")
        clips.append({
            "path": path,
            "duration": float(shot["end"]) - float(shot["start"]),
            "shot": shot,
            "start": float(shot["start"]),
            "end": float(shot["end"]),
            "audio_slice": slice_audio if path == talking else "",
            "speech_offset": (saasshorts._mp3_encoder_delay(slice_audio)
                              if path == talking else 0.0),
        })

    layout = saasshorts._reel_layout(clips)
    for segment in layout:
        kind = "как прислали" if segment["self_voiced"] else "мастер-дорожка"
        print(f"  {segment['index'] + 1:02d} {kind:14s} "
              f"слот {segment['master_start']:6.2f}-{segment['master_end']:6.2f} "
              f"-> в ролике {segment['reel_start']:6.2f} + {segment['duration']:.2f}с")
    print(f"  мастер {saasshorts._get_media_duration(master):.2f}с -> "
          f"ролик {sum(s['duration'] for s in layout):.2f}с")

    saasshorts.composite_storyboard_video(
        clips, master, subs, output_path,
        music_path=saasshorts._pick_background_music(slug) if music else None,
    )
    print(f"{output_path}: {saasshorts._get_media_duration(output_path):.3f}s")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], music="--music" in sys.argv)
