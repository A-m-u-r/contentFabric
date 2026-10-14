"""Short, capped ElevenLabs v3/v4 listening test through fal.ai.

Dry-run by default. --run requires a fal key and never sends more than the
selected trials. Existing audio and submitted result URLs are reused.
"""

import argparse
import json
import os
from pathlib import Path
import sys

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ANNA_VOICE_ID = "IO0VLmDxIb8N5msewtV4"
TEXT_A = (
    "[curious] Твой план работает только в идеальный день? Тогда он уже не работает. "
    "[sarcastic] Выспалась, всё приготовила, нашла свободный час - удобно."
)
TEXT_B = (
    "[whispers] Сладкое вечером - не начало срыва. Начало было ещё днём. "
    "[curious] Обед отложила, кофе выпила вместо еды."
)
RATES_PER_1000 = {"eleven_v3": 0.10, "eleven_v4": 0.08}
OUTPUT = ROOT / "output" / "voice_ab_2026-09-29"


def trials() -> list[dict]:
    specs = [
        ("A1", "eleven_v3", TEXT_A, None, None),
        ("A2", "eleven_v4", TEXT_A, None, None),
        ("A3", "eleven_v4", TEXT_A, 0.35, 0.75),
        ("A4", "eleven_v4", TEXT_A, 0.70, 0.75),
        ("A5", "eleven_v4", TEXT_A, 0.50, 0.55),
        ("A6", "eleven_v4", TEXT_A, 0.50, 0.90),
        ("B1", "eleven_v3", TEXT_B, None, None),
        ("B2", "eleven_v4", TEXT_B, None, None),
        ("B3", "eleven_v4", TEXT_B.replace("[whispers]", "[whispering]"), None, None),
        ("B4", "eleven_v4", TEXT_B.replace("[whispers] ", ""), None, None),
    ]
    return [
        {"code": code, "model": model, "text": text, "voice": ANNA_VOICE_ID,
         "stability": stability, "similarity_boost": similarity}
        for code, model, text, stability, similarity in specs
    ]


def model_id(trial: dict) -> str:
    return ("fal-ai/elevenlabs/tts/eleven-v3" if trial["model"] == "eleven_v3"
            else "elevenlabs/tts/eleven-v4")


def fal_input(trial: dict) -> dict:
    payload = {
        "text": trial["text"],
        "voice": trial["voice"],
        "language_code": "ru",
        "output_format": "mp3_44100_128",
        "seed": 20260929,
    }
    for field in ("stability", "similarity_boost"):
        if trial[field] is not None:
            payload[field] = trial[field]
    return payload


def estimated_cost(selected: list[dict]) -> float:
    return sum(len(trial["text"]) * RATES_PER_1000[trial["model"]] / 1000 for trial in selected)


def resolve_key(user_email: str = "") -> str:
    key = os.environ.get("FAL_KEY") or os.environ.get("FAL_API_KEY")
    if key:
        return key
    from app import _auth_db, get_user_api_key

    with _auth_db() as conn:
        users = conn.execute("SELECT id, email FROM users").fetchall()
    matches = [get_user_api_key(user["id"], "fal") for user in users
               if not user_email or user["email"] == user_email]
    keys = [value for value in matches if value]
    if len(keys) != 1:
        raise RuntimeError("Нужен один сохранённый fal-ключ в аккаунте или FAL_KEY в окружении.")
    return keys[0]


def run_trial(trial: dict, key: str, output_dir: Path = OUTPUT) -> Path:
    from saasshorts import _fal_run

    output_dir.mkdir(parents=True, exist_ok=True)
    audio_path = output_dir / f"{trial['code']}.mp3"
    result_path = output_dir / f"{trial['code']}.json"
    if audio_path.is_file() and audio_path.stat().st_size > 1000:
        print(f"{trial['code']}: готовый файл, запрос не нужен")
        return audio_path

    saved = json.loads(result_path.read_text(encoding="utf-8")) if result_path.is_file() else {}
    audio_url = saved.get("audio_url")
    if not audio_url:
        result = _fal_run(model_id(trial), fal_input(trial), key)
        audio = result.get("audio") or {}
        audio_url = audio.get("url") if isinstance(audio, dict) else audio
        if not audio_url:
            raise RuntimeError(f"{trial['code']}: fal.ai не вернул адрес аудио")
        saved = {
            "code": trial["code"], "model": trial["model"], "voice": trial["voice"],
            "text": trial["text"], "stability": trial["stability"],
            "similarity_boost": trial["similarity_boost"], "audio_url": audio_url,
            "fal_request_id": (result.get("_fal_request") or {}).get("request_id"),
        }
        result_path.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")

    with httpx.Client(timeout=90.0, follow_redirects=True) as client:
        response = client.get(audio_url)
        response.raise_for_status()
    if len(response.content) <= 1000:
        raise RuntimeError(f"{trial['code']}: ответ слишком мал для MP3")
    temporary = audio_path.with_suffix(".mp3.part")
    temporary.write_bytes(response.content)
    os.replace(temporary, audio_path)
    print(f"{trial['code']}: {audio_path}")
    return audio_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Отправить платные запросы")
    parser.add_argument("--codes", nargs="+", default=None, help="Например: A1 A2 B1 B2")
    parser.add_argument("--user-email", default="", help="Выбрать сохранённый fal-ключ пользователя")
    parser.add_argument("--max-usd", type=float, default=0.20)
    args = parser.parse_args()

    available = {trial["code"]: trial for trial in trials()}
    codes = args.codes or list(available)
    unknown = [code for code in codes if code not in available]
    if unknown:
        parser.error(f"Неизвестные пресеты: {', '.join(unknown)}")
    selected = [available[code] for code in dict.fromkeys(codes)]
    cost = estimated_cost(selected)
    if cost > args.max_usd:
        parser.error(f"Смета ${cost:.3f} превышает лимит ${args.max_usd:.3f}")
    for trial in selected:
        print(f"{trial['code']} {trial['model']} {len(trial['text'])} символов")
    print(f"Верхняя оценка по тарифам fal.ai: ${cost:.3f}")
    if not args.run:
        print("Только смета; добавь --run для отправки запросов.")
        return

    key = resolve_key(args.user_email)
    for trial in selected:
        run_trial(trial, key)


if __name__ == "__main__":
    main()
