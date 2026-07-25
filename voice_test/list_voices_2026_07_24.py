"""List the account's ElevenLabs voices so we can pick RU candidates for an A/B.

Read-only call (no generation, no cost). Prints name/id/labels only — never the key.
"""
import sys

sys.path.insert(0, "/app")

import httpx

from app import get_user_api_key

USER_ID = "b0dc0ca4-1538-4bb7-b2c5-88061c752ee1"

key = get_user_api_key(USER_ID, "elevenlabs")
assert key, "no elevenlabs key in vault"

resp = httpx.get(
    "https://api.elevenlabs.io/v1/voices",
    headers={"xi-api-key": key},
    timeout=60.0,
)
resp.raise_for_status()

for voice in resp.json().get("voices", []):
    labels = voice.get("labels") or {}
    print(
        voice.get("voice_id"),
        "|", voice.get("name"),
        "|", voice.get("category"),
        "|", labels.get("gender"), labels.get("age"), labels.get("accent"),
        "|", labels.get("description"), labels.get("use_case"),
    )
