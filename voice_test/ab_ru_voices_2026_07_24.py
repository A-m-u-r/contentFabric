"""A/B of the account's Russian-capable voices on the exact text of job saas_463d3c38.

User approved ElevenLabs-only spend for tests (no fal.ai). Same recipe for every
candidate — eleven_v3, Creative (stability 0.0), audio tags kept — so the only
variable is the voice itself.
"""
import os
import sys

sys.path.insert(0, "/app")

from app import get_user_api_key
from saasshorts import generate_voiceover

USER_ID = "b0dc0ca4-1538-4bb7-b2c5-88061c752ee1"
OUT_DIR = "/app/voice_test/ab_2026_07_24"

TEXT = (
    "Так, стоп. Диеты после тридцати… [sighs] делают тебя только толще. "
    "Организм пугается дефицита… и начинает судорожно запасать жир."
)

CANDIDATES = [
    ("victoria_current", "D5RRIJYa9pFwxiSpbGbR"),   # утверждённый дефолт
    ("vika_grib", "gelrownZgbRhxH6LI78J"),          # привязан к аватару
    ("aigul_yusupova", "f5X5eGhdEHgblKUK6qzh"),     # cloned
]

key = get_user_api_key(USER_ID, "elevenlabs")
assert key, "no elevenlabs key in vault"

os.makedirs(OUT_DIR, exist_ok=True)
for name, voice_id in CANDIDATES:
    path = os.path.join(OUT_DIR, f"{name}.mp3")
    model = generate_voiceover(TEXT, key, path, voice_id=voice_id)
    print(f"{name}: {model} -> {path} ({os.path.getsize(path)} bytes)")
