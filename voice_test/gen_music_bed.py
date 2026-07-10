"""Generate one background bed track via ElevenLabs sound-generation.

User-approved cost policy: only ElevenLabs generations are allowed for tests.
The track lands in assets/music/ where _pick_background_music finds it.
"""
import sys

sys.path.insert(0, "/app")

import httpx

from app import get_user_api_key

USER_ID = "b0dc0ca4-1538-4bb7-b2c5-88061c752ee1"

key = get_user_api_key(USER_ID, "elevenlabs")
assert key, "no elevenlabs key in vault"

out = "/app/assets/music/lofi_bed_01.mp3"
resp = httpx.post(
    "https://api.elevenlabs.io/v1/sound-generation",
    headers={"xi-api-key": key, "Content-Type": "application/json"},
    json={
        "text": (
            "Warm minimal lo-fi hip hop instrumental background beat, "
            "soft piano chords, mellow and calm, no vocals, seamless loop"
        ),
        "duration_seconds": 20.0,
        "prompt_influence": 0.3,
    },
    timeout=180,
)
print("status:", resp.status_code)
if resp.status_code == 200:
    with open(out, "wb") as f:
        f.write(resp.content)
    print("saved:", out, len(resp.content), "bytes")
else:
    print("body:", resp.text[:500])
