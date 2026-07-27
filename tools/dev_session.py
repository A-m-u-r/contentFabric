#!/usr/bin/env python3
"""Локальный dev-скрипт: выдать себе session-токен без ввода пароля.

Зачем: чтобы агент/разработчик мог открыть дашборд под существующим аккаунтом
и проверить UI живьём, не вводя пароль в форму.

Почему это не бэкдор:
  * это НЕ HTTP-endpoint — поверхность атаки приложения не меняется;
  * скрипту нужен прямой доступ к файлу SQLite. У кого он есть, тот и так
    читает все таблицы, включая vault с API-ключами. То есть новых прав
    скрипт не даёт — он лишь пользуется штатной таблицей `sessions`;
  * токен ограничен по сроку (--days, по умолчанию 1 день) и отзывается
    (--revoke) одной командой.

Примеры:
    python tools/dev_session.py --list
    python tools/dev_session.py --email me@example.com
    python tools/dev_session.py --revoke os_xxxxx

Внутри docker:
    docker compose exec backend python tools/dev_session.py --list
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import os
import secrets
import sqlite3
import sys

DEFAULT_DB = os.environ.get(
    "OPENSHORTS_DB_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output", "openshorts.db"),
)


def _token_hash(token: str) -> str:
    # Должно совпадать с app._token_hash.
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _utc_now() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


def _connect(db_path: str) -> sqlite3.Connection:
    if not os.path.exists(db_path):
        sys.exit(f"БД не найдена: {db_path}\nУкажи путь через --db или OPENSHORTS_DB_PATH.")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def cmd_list(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT id, email, name, subscription_status FROM users ORDER BY created_at"
    ).fetchall()
    if not rows:
        sys.exit("В базе нет пользователей — сначала зарегистрируйся в UI.")
    print(f"{'email':<34} {'подписка':<10} id")
    for row in rows:
        print(f"{row['email']:<34} {row['subscription_status']:<10} {row['id']}")


def cmd_mint(conn: sqlite3.Connection, email: str | None, days: int) -> None:
    if email:
        row = conn.execute(
            "SELECT id, email FROM users WHERE lower(email) = ?", (email.strip().lower(),)
        ).fetchone()
        if not row:
            sys.exit(f"Пользователь {email} не найден. Посмотри список: --list")
    else:
        rows = conn.execute("SELECT id, email FROM users").fetchall()
        if len(rows) != 1:
            sys.exit("В базе не один пользователь — укажи --email. Список: --list")
        row = rows[0]

    token = "os_" + secrets.token_urlsafe(32)
    expires_at = (datetime.datetime.utcnow() + datetime.timedelta(days=days)).isoformat() + "Z"
    with conn:
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (_token_hash(token), row["id"], _utc_now(), expires_at),
        )

    print(f"Аккаунт : {row['email']}")
    print(f"Истекает: {expires_at} (через {days} дн.)")
    print(f"Токен   : {token}")
    print()
    print("Вставить в браузере (DevTools → Console) на странице приложения:")
    print(f"  localStorage.setItem('openshorts_auth_token', '{token}'); location.reload()")
    print()
    print(f"Отозвать: python tools/dev_session.py --revoke {token}")


def cmd_revoke(conn: sqlite3.Connection, token: str) -> None:
    with conn:
        cur = conn.execute("DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),))
    print(f"Отозвано сессий: {cur.rowcount}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Выдать локальный dev session-токен.")
    parser.add_argument("--db", default=DEFAULT_DB, help="путь к openshorts.db")
    parser.add_argument("--email", help="аккаунт, под который выдать токен")
    parser.add_argument("--days", type=int, default=1, help="срок жизни токена в днях (по умолчанию 1)")
    parser.add_argument("--list", action="store_true", help="показать пользователей")
    parser.add_argument("--revoke", metavar="TOKEN", help="отозвать выданный токен")
    args = parser.parse_args()

    # Страховка от запуска на боевом сервере.
    if os.environ.get("OPENSHORTS_PRODUCTION") == "1":
        sys.exit("OPENSHORTS_PRODUCTION=1 — скрипт предназначен только для локальной разработки.")

    conn = _connect(args.db)
    try:
        if args.list:
            cmd_list(conn)
        elif args.revoke:
            cmd_revoke(conn, args.revoke)
        else:
            cmd_mint(conn, args.email, args.days)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
