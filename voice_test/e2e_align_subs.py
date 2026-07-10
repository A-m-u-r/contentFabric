"""E2E proof of script-aligned subtitles on real TTS audio.

Victoria says the phrase Whisper previously misheard («слабая» -> «слабое»);
subtitles must come out as the exact script text.
"""
import sys

sys.path.insert(0, "/app")

from app import get_user_api_key
from saasshorts import (
    _align_asr_words_to_script,
    generate_voiceover,
    transcribe_audio_for_subs,
)

USER_ID = "b0dc0ca4-1538-4bb7-b2c5-88061c752ee1"

key = get_user_api_key(USER_ID, "elevenlabs")
assert key, "no elevenlabs key in vault"

text = "Стоп, стоп, стоп! Ты срываешься вечером не потому, что слабая. Совсем нет."
out = "/app/voice_test/align_e2e_victoria.mp3"
generate_voiceover(text, key, out, voice_id="D5RRIJYa9pFwxiSpbGbR")

words = transcribe_audio_for_subs(out, language="ru")
print("ASR :", " ".join(w["word"] for w in words))
aligned = _align_asr_words_to_script(words, text)
print("SUBS:", " ".join(w["word"] for w in aligned))
for w in aligned:
    print(f"  {w['start']:6.2f}-{w['end']:6.2f}  {w['word']}")
