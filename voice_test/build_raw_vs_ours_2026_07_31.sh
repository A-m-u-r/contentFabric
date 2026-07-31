#!/bin/sh
# Two views of the same five takes, so the difference can be judged by eye:
#   *_as_delivered.mp4  - the mp4 fal.ai returned, its own audio, untouched
#   *_our_cut.mp4       - the same take as it plays in the finished reel
set -e
OUT=/app/voice_test/kling_raw_2026_07_31
JOB=/app/output/saas_d6b674c6-6d61-4b87-9d6e-9e4d48cb347f
FINAL=$JOB/_30_storyboard_final.mp4

# slot bounds of the talking shots, from the archived storyboard
set -- "01 0.00 1.72" "03 2.26 3.90" "05 5.90 8.48" "07 9.80 11.46" "09 13.94 16.16"
for row in "$@"; do
  n=$(echo "$row" | cut -d' ' -f1)
  start=$(echo "$row" | cut -d' ' -f2)
  end=$(echo "$row" | cut -d' ' -f3)
  ffmpeg -v error -y -ss "$start" -to "$end" -i "$FINAL" \
    -c:v libx264 -preset fast -crf 20 -c:a aac -b:a 192k \
    "$OUT/take_${n}_our_cut.mp4"
done

# Both reels, same order, no b-roll and no subtitles in the delivered one.
: > /tmp/delivered.txt
: > /tmp/ours.txt
for n in 01 03 05 07 09; do
  ffmpeg -v error -y -i "$OUT/take_${n}_as_delivered.mp4" \
    -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,setsar=1" \
    -c:v libx264 -preset fast -crf 20 -c:a aac -b:a 192k "/tmp/d_$n.mp4"
  ffmpeg -v error -y -i "$OUT/take_${n}_our_cut.mp4" \
    -vf "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,setsar=1" \
    -c:v libx264 -preset fast -crf 20 -c:a aac -b:a 192k "/tmp/o_$n.mp4"
  echo "file '/tmp/d_$n.mp4'" >> /tmp/delivered.txt
  echo "file '/tmp/o_$n.mp4'" >> /tmp/ours.txt
done
ffmpeg -v error -y -f concat -safe 0 -i /tmp/delivered.txt -c copy \
  "$OUT/all_takes_as_delivered.mp4"
ffmpeg -v error -y -f concat -safe 0 -i /tmp/ours.txt -c copy \
  "$OUT/all_takes_our_cut.mp4"
echo done
