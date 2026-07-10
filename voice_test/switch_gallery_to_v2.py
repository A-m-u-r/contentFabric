"""Point gallery entries at the rebuilt *_v2 finals (original URL kept for revert)."""
import json
import os
import sys

sys.path.insert(0, "/app")

OUT = "/app/output"

for d in sorted(os.listdir(OUT)):
    job = os.path.join(OUT, d)
    meta_path = os.path.join(job, "gallery_metadata.json")
    if not d.startswith("saas_") or not os.path.isfile(meta_path):
        continue
    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    url = meta.get("video_url") or ""
    base, ext = os.path.splitext(url)
    v2_url = f"{base}_v2{ext}"
    v2_file = os.path.join(OUT, v2_url.replace("/videos/", ""))
    if not os.path.isfile(v2_file):
        print(f"skip {d}: no v2 file")
        continue
    if meta.get("video_url", "").endswith("_v2.mp4"):
        print(f"already v2: {d}")
        continue
    meta["video_url_original"] = url
    meta["video_url"] = v2_url
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"switched {d} -> {os.path.basename(v2_url)}")

from app import list_local_saas_gallery  # noqa: E402

print("\ngallery for owner:")
for v in list_local_saas_gallery("b0dc0ca4-1538-4bb7-b2c5-88061c752ee1"):
    print(" ", v.get("title", "?")[:30], "->", v.get("video_url"))
