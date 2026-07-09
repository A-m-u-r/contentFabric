import os
import uuid
import subprocess
import threading
import json
import shutil
import glob
import time
import asyncio
import datetime
import base64
import hashlib
import hmac
import io
import secrets
import sqlite3
import tempfile
import zipfile
from urllib.parse import urlparse
from dotenv import load_dotenv
from typing import Dict, Optional, List
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel
from s3_uploader import upload_job_artifacts, list_all_clips, upload_actor_to_s3, list_actor_gallery, upload_video_to_gallery, list_video_gallery

load_dotenv()

# Constants
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "output"
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
AUTH_DB_PATH = os.environ.get("OPENSHORTS_DB_PATH", os.path.join(OUTPUT_DIR, "openshorts.db"))
ENV_PATH = os.environ.get("OPENSHORTS_ENV_PATH", ".env")
KEY_VAULT_SECRET = os.environ.get("OPENSHORTS_KEY_VAULT_SECRET") or os.environ.get("SECRET_KEY") or "openshorts-dev-key-vault-secret"

# Configuration
# Default to 1 if not set, but user can set higher for powerful servers
MAX_CONCURRENT_JOBS = int(os.environ.get("MAX_CONCURRENT_JOBS", "5"))
MAX_FILE_SIZE_MB = 2048  # 2GB limit
JOB_RETENTION_SECONDS = 3600  # 1 hour retention
DISABLE_YOUTUBE_URL = os.environ.get("DISABLE_YOUTUBE_URL", "false").lower() in ("1", "true", "yes")

# Application State
job_queue = asyncio.Queue()
jobs: Dict[str, Dict] = {}
thumbnail_sessions: Dict[str, Dict] = {}
publish_jobs: Dict[str, Dict] = {}  # {publish_id: {status, result, error}}
# Semester to limit concurrency to MAX_CONCURRENT_JOBS
concurrency_semaphore = asyncio.Semaphore(MAX_CONCURRENT_JOBS)


class SubscriptionRequiredError(Exception):
    pass


class PlatformKeyUnavailableError(Exception):
    pass


API_KEY_PROVIDERS = {
    "gemini": ("GEMINI_API_KEY",),
    "fal": ("FAL_KEY", "FAL_API_KEY"),
    "elevenlabs": ("ELEVENLABS_API_KEY", "ELEVENLABS_KEY"),
    "upload_post": ("UPLOAD_POST_API_KEY", "UPLOAD_POST_KEY"),
}


def _utc_now() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


class ClosingSQLiteConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def _auth_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(AUTH_DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(AUTH_DB_PATH, factory=ClosingSQLiteConnection)
    conn.row_factory = sqlite3.Row
    return conn


def init_auth_db() -> None:
    with _auth_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                subscription_status TEXT NOT NULL DEFAULT 'free',
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS api_keys (
                user_id TEXT NOT NULL,
                provider TEXT NOT NULL,
                encrypted_value TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(user_id, provider),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS business_profiles (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                topic TEXT NOT NULL DEFAULT '',
                script_mode TEXT NOT NULL DEFAULT 'ai',
                script_format TEXT NOT NULL DEFAULT 'ugc',
                style TEXT NOT NULL DEFAULT 'ugc',
                language TEXT NOT NULL DEFAULT 'ru',
                actor_gender TEXT NOT NULL DEFAULT 'female',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
            """
        )


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _public_user(row) -> Optional[dict]:
    if not row:
        return None
    return {
        "id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "subscription_status": row["subscription_status"],
        "created_at": row["created_at"],
    }


def _hash_password(password: str, salt: Optional[bytes] = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return f"pbkdf2_sha256${base64.urlsafe_b64encode(salt).decode()}${base64.urlsafe_b64encode(digest).decode()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, salt_b64, digest_b64 = stored_hash.split("$", 2)
        if scheme != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode())
        expected = base64.urlsafe_b64decode(digest_b64.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _secret_bytes() -> bytes:
    return hashlib.sha256(KEY_VAULT_SECRET.encode("utf-8")).digest()


def _keystream(nonce: bytes, length: int) -> bytes:
    out = b""
    counter = 0
    secret = _secret_bytes()
    while len(out) < length:
        out += hashlib.sha256(secret + nonce + counter.to_bytes(4, "big")).digest()
        counter += 1
    return out[:length]


def _encrypt_secret(value: str) -> str:
    raw = value.encode("utf-8")
    nonce = secrets.token_bytes(16)
    stream = _keystream(nonce, len(raw))
    cipher = bytes(a ^ b for a, b in zip(raw, stream))
    mac = hmac.new(_secret_bytes(), nonce + cipher, hashlib.sha256).digest()
    return "v1:" + base64.urlsafe_b64encode(nonce + mac + cipher).decode("ascii")


def _decrypt_secret(value: str) -> str:
    if not value:
        return ""
    if not value.startswith("v1:"):
        return value
    payload = base64.urlsafe_b64decode(value[3:].encode("ascii"))
    nonce = payload[:16]
    mac = payload[16:48]
    cipher = payload[48:]
    expected = hmac.new(_secret_bytes(), nonce + cipher, hashlib.sha256).digest()
    if not hmac.compare_digest(mac, expected):
        raise ValueError("Key vault secret integrity check failed")
    stream = _keystream(nonce, len(cipher))
    return bytes(a ^ b for a, b in zip(cipher, stream)).decode("utf-8")


def create_user(email: str, password: str, name: Optional[str] = None) -> dict:
    email = _normalize_email(email)
    if not email or "@" not in email:
        raise ValueError("Valid email is required")
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    is_first_user = _user_count() == 0
    user_id = str(uuid.uuid4())
    with _auth_db() as conn:
        conn.execute(
            """
            INSERT INTO users (id, email, name, password_hash, subscription_status, created_at)
            VALUES (?, ?, ?, ?, 'free', ?)
            """,
            (user_id, email, (name or email.split("@")[0]).strip() or "User", _hash_password(password), _utc_now()),
        )
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if is_first_user:
        claim_legacy_assets_for_user(user_id)
    return _public_user(row)


def get_user_by_id(user_id: str) -> Optional[dict]:
    with _auth_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return _public_user(row)


def authenticate_user(email: str, password: str) -> Optional[dict]:
    with _auth_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (_normalize_email(email),)).fetchone()
    if not row or not _verify_password(password, row["password_hash"]):
        return None
    return _public_user(row)


def create_session(user_id: str, days: int = 30) -> str:
    token = "os_" + secrets.token_urlsafe(32)
    expires_at = (datetime.datetime.utcnow() + datetime.timedelta(days=days)).isoformat() + "Z"
    with _auth_db() as conn:
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (_token_hash(token), user_id, _utc_now(), expires_at),
        )
    return token


def get_user_by_token(token: str) -> Optional[dict]:
    if not token:
        return None
    with _auth_db() as conn:
        row = conn.execute(
            """
            SELECT users.* FROM sessions
            JOIN users ON users.id = sessions.user_id
            WHERE sessions.token_hash = ? AND sessions.expires_at > ?
            """,
            (_token_hash(token), _utc_now()),
        ).fetchone()
    return _public_user(row)


def get_user_from_authorization(authorization: Optional[str]) -> Optional[dict]:
    if not authorization:
        return None
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        return None
    return get_user_by_token(authorization[len(prefix):].strip())


def require_user_from_authorization(authorization: Optional[str]) -> dict:
    user = get_user_from_authorization(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def set_user_subscription_status(user_id: str, status: str) -> dict:
    if status not in ("free", "active", "expired"):
        raise ValueError("Invalid subscription status")
    with _auth_db() as conn:
        conn.execute("UPDATE users SET subscription_status = ? WHERE id = ?", (status, user_id))
    user = get_user_by_id(user_id)
    if not user:
        raise ValueError("User not found")
    return user


def upsert_user_api_key(user_id: str, provider: str, api_key: str) -> None:
    if provider not in API_KEY_PROVIDERS:
        raise ValueError("Unknown API key provider")
    if not api_key or not api_key.strip():
        raise ValueError("API key is required")
    with _auth_db() as conn:
        conn.execute(
            """
            INSERT INTO api_keys (user_id, provider, encrypted_value, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, provider)
            DO UPDATE SET encrypted_value = excluded.encrypted_value, updated_at = excluded.updated_at
            """,
            (user_id, provider, _encrypt_secret(api_key.strip()), _utc_now()),
        )


def get_user_api_key(user_id: str, provider: str) -> Optional[str]:
    with _auth_db() as conn:
        row = conn.execute(
            "SELECT encrypted_value FROM api_keys WHERE user_id = ? AND provider = ?",
            (user_id, provider),
        ).fetchone()
    if not row:
        return None
    return _decrypt_secret(row["encrypted_value"])


def list_user_api_key_status(user_id: str) -> dict:
    status = {
        provider: {"has_key": False, "updated_at": None}
        for provider in API_KEY_PROVIDERS
    }
    with _auth_db() as conn:
        rows = conn.execute(
            "SELECT provider, updated_at FROM api_keys WHERE user_id = ?",
            (user_id,),
        ).fetchall()
    for row in rows:
        if row["provider"] in status:
            status[row["provider"]] = {"has_key": True, "updated_at": row["updated_at"]}
    return status


def _public_business_profile(row) -> Optional[dict]:
    if not row:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "topic": row["topic"],
        "script_mode": row["script_mode"],
        "script_format": row["script_format"],
        "style": row["style"],
        "language": row["language"],
        "actor_gender": row["actor_gender"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def upsert_business_profile(user_id: str, profile: dict) -> dict:
    name = (profile.get("name") or "").strip()
    description = (profile.get("description") or "").strip()
    if not name:
        raise ValueError("Business name is required")
    if not description:
        raise ValueError("Business description is required")

    profile_id = (profile.get("id") or "").strip() or str(uuid.uuid4())
    now = _utc_now()
    with _auth_db() as conn:
        existing = conn.execute(
            "SELECT created_at FROM business_profiles WHERE id = ? AND user_id = ?",
            (profile_id, user_id),
        ).fetchone()
        created_at = existing["created_at"] if existing else now
        conn.execute(
            """
            INSERT INTO business_profiles (
                id, user_id, name, description, topic, script_mode, script_format,
                style, language, actor_gender, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                description = excluded.description,
                topic = excluded.topic,
                script_mode = excluded.script_mode,
                script_format = excluded.script_format,
                style = excluded.style,
                language = excluded.language,
                actor_gender = excluded.actor_gender,
                updated_at = excluded.updated_at
            """,
            (
                profile_id,
                user_id,
                name,
                description,
                (profile.get("topic") or "").strip(),
                profile.get("script_mode") or "ai",
                profile.get("script_format") or "ugc",
                profile.get("style") or "ugc",
                profile.get("language") or "ru",
                profile.get("actor_gender") or "female",
                created_at,
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM business_profiles WHERE id = ? AND user_id = ?",
            (profile_id, user_id),
        ).fetchone()
    return _public_business_profile(row)


def list_business_profiles(user_id: str) -> List[dict]:
    with _auth_db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM business_profiles
            WHERE user_id = ?
            ORDER BY updated_at DESC
            """,
            (user_id,),
        ).fetchall()
    return [_public_business_profile(row) for row in rows]


def _metadata_json_paths_for_legacy_claim() -> List[str]:
    paths = []
    paths.extend(glob.glob(os.path.join(OUTPUT_DIR, "saas_*", "gallery_metadata.json")))
    paths.extend(glob.glob(os.path.join(OUTPUT_DIR, "head_templates", "*", "metadata.json")))

    for path in glob.glob(os.path.join(OUTPUT_DIR, "**", "*.json"), recursive=True):
        normalized = path.replace("\\", "/")
        if normalized.endswith("/gallery_metadata.json") or normalized.endswith("/metadata.json"):
            continue
        paths.append(path)

    return paths


def claim_legacy_assets_for_user(user_id: str) -> dict:
    """Attach local legacy assets without owner_user_id to the given user."""
    counts = {"videos": 0, "head_templates": 0, "actors": 0}
    for path in _metadata_json_paths_for_legacy_claim():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue

        if data.get("owner_user_id"):
            continue

        kind = None
        normalized = path.replace("\\", "/")
        if normalized.endswith("/gallery_metadata.json"):
            kind = "videos"
        elif normalized.endswith("/metadata.json") and "/head_templates/" in normalized:
            kind = "head_templates"
        elif "url" in data and "storage" in data:
            kind = "actors"

        if not kind:
            continue

        data["owner_user_id"] = user_id
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        counts[kind] += 1

    return counts


def _user_count() -> int:
    with _auth_db() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()
    return int(row["n"]) if row else 0


def _platform_api_key(provider: str) -> Optional[str]:
    for env_name in API_KEY_PROVIDERS.get(provider, ()):
        value = os.environ.get(env_name)
        if value:
            return value
    return None


def resolve_effective_api_key(
    provider: str,
    user: Optional[dict],
    header_value: Optional[str],
    use_platform_keys: bool = False,
) -> Optional[str]:
    if use_platform_keys:
        if not user or user.get("subscription_status") != "active":
            raise SubscriptionRequiredError("Active subscription is required to use platform API keys")
        platform_key = _platform_api_key(provider)
        if not platform_key:
            raise PlatformKeyUnavailableError(f"Platform {provider} API key is not configured")
        return platform_key

    if user:
        saved_key = get_user_api_key(user["id"], provider)
        if saved_key:
            return saved_key

    if header_value:
        return header_value

    if not user:
        return _platform_api_key(provider)

    return None


def _relocate_root_job_artifacts(job_id: str, job_output_dir: str) -> bool:
    """
    Backward-compat rescue:
    If main.py accidentally wrote metadata/clips into OUTPUT_DIR root (e.g. output/<jobid>_...),
    move them into output/<job_id>/ so the API can find and serve them.
    """
    try:
        os.makedirs(job_output_dir, exist_ok=True)
        root = OUTPUT_DIR
        pattern = os.path.join(root, f"{job_id}_*_metadata.json")
        meta_candidates = sorted(glob.glob(pattern), key=lambda p: os.path.getmtime(p), reverse=True)
        if not meta_candidates:
            return False

        # Move the newest metadata and its associated clips.
        metadata_path = meta_candidates[0]
        base_name = os.path.basename(metadata_path).replace("_metadata.json", "")

        # Move metadata
        dest_metadata = os.path.join(job_output_dir, os.path.basename(metadata_path))
        if os.path.abspath(metadata_path) != os.path.abspath(dest_metadata):
            shutil.move(metadata_path, dest_metadata)

        # Move any clips that match the same base_name into the job folder
        clip_pattern = os.path.join(root, f"{base_name}_clip_*.mp4")
        for clip_path in glob.glob(clip_pattern):
            dest_clip = os.path.join(job_output_dir, os.path.basename(clip_path))
            if os.path.abspath(clip_path) != os.path.abspath(dest_clip):
                shutil.move(clip_path, dest_clip)

        # Also move any temp_ clips that might remain
        temp_clip_pattern = os.path.join(root, f"temp_{base_name}_clip_*.mp4")
        for clip_path in glob.glob(temp_clip_pattern):
            dest_clip = os.path.join(job_output_dir, os.path.basename(clip_path))
            if os.path.abspath(clip_path) != os.path.abspath(dest_clip):
                shutil.move(clip_path, dest_clip)

        return True
    except Exception:
        return False

async def cleanup_jobs():
    """Background task to remove old jobs and files."""
    import time
    print("🧹 Cleanup task started.")
    while True:
        try:
            await asyncio.sleep(300) # Check every 5 minutes
            now = time.time()
            
            # Simple directory cleanup based on modification time
            # Check OUTPUT_DIR
            for job_id in os.listdir(OUTPUT_DIR):
                job_path = os.path.join(OUTPUT_DIR, job_id)
                if os.path.isdir(job_path):
                    if job_id.startswith("saas_") and glob.glob(os.path.join(job_path, "*_final.mp4")):
                        continue
                    if now - os.path.getmtime(job_path) > JOB_RETENTION_SECONDS:
                        print(f"🧹 Purging old job: {job_id}")
                        shutil.rmtree(job_path, ignore_errors=True)
                        if job_id in jobs:
                            del jobs[job_id]

            # Cleanup SaaSShorts jobs from memory
            try:
                saas_expired = [
                    jid for jid, jdata in list(saas_jobs.items())
                    if jdata.get("status") in ("completed", "failed")
                    and jdata.get("output_dir")
                    and os.path.isdir(jdata["output_dir"])
                    and now - os.path.getmtime(jdata["output_dir"]) > JOB_RETENTION_SECONDS
                ]
                for jid in saas_expired:
                    del saas_jobs[jid]
            except NameError:
                pass

            # Cleanup Uploads
            for filename in os.listdir(UPLOAD_DIR):
                file_path = os.path.join(UPLOAD_DIR, filename)
                try:
                    if now - os.path.getmtime(file_path) > JOB_RETENTION_SECONDS:
                         os.remove(file_path)
                except Exception: pass

        except Exception as e:
            print(f"⚠️ Cleanup error: {e}")

async def process_queue():
    """Background worker to process jobs from the queue with concurrency limit."""
    print(f"🚀 Job Queue Worker started with {MAX_CONCURRENT_JOBS} concurrent slots.")
    while True:
        try:
            # Wait for a job
            job_id = await job_queue.get()
            
            # Acquire semaphore slot (waits if max jobs are running)
            await concurrency_semaphore.acquire()
            print(f"🔄 Acquired slot for job: {job_id}")

            # Process in background task to not block the loop (allowing other slots to fill)
            asyncio.create_task(run_job_wrapper(job_id))
            
        except Exception as e:
            print(f"❌ Queue dispatch error: {e}")
            await asyncio.sleep(1)

async def run_job_wrapper(job_id):
    """Wrapper to run job and release semaphore"""
    try:
        job = jobs.get(job_id)
        if job:
            await run_job(job_id, job)
    except Exception as e:
         print(f"❌ Job wrapper error {job_id}: {e}")
    finally:
        # Always release semaphore and mark queue task done
        concurrency_semaphore.release()
        job_queue.task_done()
        print(f"✅ Released slot for job: {job_id}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start worker and cleanup
    init_auth_db()
    worker_task = asyncio.create_task(process_queue())
    cleanup_task = asyncio.create_task(cleanup_jobs())
    yield
    # Cleanup (optional: cancel worker)

app = FastAPI(lifespan=lifespan)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files for serving videos
app.mount("/videos", StaticFiles(directory=OUTPUT_DIR), name="videos")

# Mount static files for serving thumbnails
THUMBNAILS_DIR = os.path.join(OUTPUT_DIR, "thumbnails")
os.makedirs(THUMBNAILS_DIR, exist_ok=True)
app.mount("/thumbnails", StaticFiles(directory=THUMBNAILS_DIR), name="thumbnails")


class AuthRegisterRequest(BaseModel):
    email: str
    password: str
    name: Optional[str] = None


class AuthLoginRequest(BaseModel):
    email: str
    password: str


class ApiKeySaveRequest(BaseModel):
    provider: str
    api_key: str


class BusinessProfileRequest(BaseModel):
    id: Optional[str] = None
    name: str
    description: str
    topic: str = ""
    script_mode: str = "ai"
    script_format: str = "ugc"
    style: str = "ugc"
    language: str = "ru"
    actor_gender: str = "female"


class AdminSubscriptionRequest(BaseModel):
    user_id: str
    status: str


BACKUP_FORMAT = "openshorts-backup"
BACKUP_VERSION = 1
BACKUP_ALLOWED_ROOTS = {"output", "uploads", "auth", ".env", "openshorts-backup.json"}


def _is_path_inside(path: str, parent: str) -> bool:
    try:
        return os.path.commonpath([os.path.abspath(path), os.path.abspath(parent)]) == os.path.abspath(parent)
    except ValueError:
        return False


def _checkpoint_auth_db() -> None:
    if not os.path.exists(AUTH_DB_PATH):
        return
    conn = _auth_db()
    try:
        conn.execute("PRAGMA wal_checkpoint(FULL)")
        conn.commit()
    except sqlite3.Error:
        pass
    finally:
        conn.close()


def _write_tree_to_zip(zf: zipfile.ZipFile, source_dir: str, archive_root: str) -> int:
    if not os.path.isdir(source_dir):
        return 0

    written = 0
    for root, dirs, files in os.walk(source_dir):
        dirs[:] = [d for d in dirs if d not in {"__pycache__", ".git"}]
        for filename in files:
            src = os.path.join(root, filename)
            rel = os.path.relpath(src, source_dir).replace(os.sep, "/")
            zf.write(src, f"{archive_root}/{rel}")
            written += 1
    return written


def _backup_env_contents() -> str:
    env_path = ENV_PATH
    content = ""
    if os.path.isfile(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            content = f.read()

    has_vault_secret = "OPENSHORTS_KEY_VAULT_SECRET=" in content or "SECRET_KEY=" in content
    if not has_vault_secret:
        separator = "" if not content or content.endswith("\n") else "\n"
        content = f"{content}{separator}OPENSHORTS_KEY_VAULT_SECRET={KEY_VAULT_SECRET}\n"
    return content


def create_backup_archive(user_id: str) -> bytes:
    _checkpoint_auth_db()

    buf = io.BytesIO()
    included = []
    file_count = 0

    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        output_count = _write_tree_to_zip(zf, OUTPUT_DIR, "output")
        if output_count:
            included.append("output")
            file_count += output_count

        upload_count = _write_tree_to_zip(zf, UPLOAD_DIR, "uploads")
        if upload_count:
            included.append("uploads")
            file_count += upload_count

        auth_db_abs = os.path.abspath(AUTH_DB_PATH)
        output_abs = os.path.abspath(OUTPUT_DIR)
        if os.path.isfile(auth_db_abs) and not _is_path_inside(auth_db_abs, output_abs):
            zf.write(auth_db_abs, "auth/openshorts.db")
            included.append("auth")
            file_count += 1

        zf.writestr(".env", _backup_env_contents())
        included.append(".env")
        file_count += 1

        manifest = {
            "format": BACKUP_FORMAT,
            "version": BACKUP_VERSION,
            "created_at": _utc_now(),
            "owner_user_id": user_id,
            "included_roots": sorted(set(included)),
            "file_count": file_count,
            "contains_sensitive_data": True,
            "note": "Archive contains local videos, avatars, encrypted API keys and the vault secret needed to decrypt them.",
        }
        zf.writestr("openshorts-backup.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    return buf.getvalue()


def _validate_backup_member_name(name: str) -> str:
    normalized = (name or "").replace("\\", "/")
    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    if not parts:
        raise ValueError("Backup archive contains an empty path")
    if normalized.startswith("/") or ".." in parts or ":" in parts[0]:
        raise ValueError(f"Unsafe backup path: {name}")

    top = parts[0]
    if top not in BACKUP_ALLOWED_ROOTS:
        raise ValueError(f"Unsupported backup path: {name}")
    if top in {".env", "openshorts-backup.json"} and len(parts) != 1:
        raise ValueError(f"Unsupported nested backup path: {name}")
    return "/".join(parts)


def _copy_file_atomic(src: str, dst: str) -> None:
    os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
    tmp_dst = f"{dst}.importing-{uuid.uuid4().hex}"
    shutil.copy2(src, tmp_dst)
    os.replace(tmp_dst, dst)


def _merge_tree(src_dir: str, dst_dir: str) -> int:
    if not os.path.isdir(src_dir):
        return 0

    copied = 0
    for root, dirs, files in os.walk(src_dir):
        rel_root = os.path.relpath(root, src_dir)
        target_root = dst_dir if rel_root == "." else os.path.join(dst_dir, rel_root)
        os.makedirs(target_root, exist_ok=True)
        for dirname in dirs:
            os.makedirs(os.path.join(target_root, dirname), exist_ok=True)
        for filename in files:
            _copy_file_atomic(os.path.join(root, filename), os.path.join(target_root, filename))
            copied += 1
    return copied


def restore_backup_archive(archive_bytes: bytes) -> dict:
    restored_roots = set()
    restored_files = 0

    try:
        zf = zipfile.ZipFile(io.BytesIO(archive_bytes), "r")
    except zipfile.BadZipFile as e:
        raise ValueError("Backup archive is not a valid ZIP file") from e

    with zf:
        names = zf.namelist()
        if "openshorts-backup.json" not in names:
            raise ValueError("Backup manifest is missing")

        try:
            manifest = json.loads(zf.read("openshorts-backup.json").decode("utf-8"))
        except Exception as e:
            raise ValueError("Backup manifest is invalid") from e
        if manifest.get("format") != BACKUP_FORMAT:
            raise ValueError("Unsupported backup format")

        for info in zf.infolist():
            _validate_backup_member_name(info.filename)

        with tempfile.TemporaryDirectory(prefix="openshorts-import-") as tmp_dir:
            for info in zf.infolist():
                safe_name = _validate_backup_member_name(info.filename)
                if info.is_dir() or safe_name == "openshorts-backup.json":
                    continue

                dst = os.path.join(tmp_dir, *safe_name.split("/"))
                os.makedirs(os.path.dirname(dst) or tmp_dir, exist_ok=True)
                with zf.open(info, "r") as src, open(dst, "wb") as out:
                    shutil.copyfileobj(src, out)

            output_count = _merge_tree(os.path.join(tmp_dir, "output"), OUTPUT_DIR)
            if output_count:
                restored_roots.add("output")
                restored_files += output_count

            upload_count = _merge_tree(os.path.join(tmp_dir, "uploads"), UPLOAD_DIR)
            if upload_count:
                restored_roots.add("uploads")
                restored_files += upload_count

            env_src = os.path.join(tmp_dir, ".env")
            if os.path.isfile(env_src):
                if os.path.exists(ENV_PATH):
                    backup_name = f"{ENV_PATH}.before-import-{datetime.datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
                    _copy_file_atomic(ENV_PATH, backup_name)
                _copy_file_atomic(env_src, ENV_PATH)
                restored_roots.add(".env")
                restored_files += 1

            auth_db_src = os.path.join(tmp_dir, "auth", "openshorts.db")
            if os.path.isfile(auth_db_src):
                _copy_file_atomic(auth_db_src, AUTH_DB_PATH)
                restored_roots.add("auth")
                restored_files += 1

    init_auth_db()
    return {
        "restored_roots": sorted(restored_roots),
        "restored_files": restored_files,
        "requires_restart": ".env" in restored_roots,
        "message": "Backup restored. Restart the backend if API keys do not decrypt until the vault secret is reloaded.",
    }


@app.post("/api/auth/register")
async def auth_register(req: AuthRegisterRequest):
    try:
        init_auth_db()
        user = create_user(req.email, req.password, req.name)
        token = create_session(user["id"])
        return {"token": token, "user": user, "api_keys": list_user_api_key_status(user["id"])}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Email is already registered")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/auth/login")
async def auth_login(req: AuthLoginRequest):
    init_auth_db()
    user = authenticate_user(req.email, req.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_session(user["id"])
    return {"token": token, "user": user, "api_keys": list_user_api_key_status(user["id"])}


@app.get("/api/auth/me")
async def auth_me(authorization: Optional[str] = Header(None, alias="Authorization")):
    user = require_user_from_authorization(authorization)
    return {"user": user, "api_keys": list_user_api_key_status(user["id"])}


@app.post("/api/user/api-keys")
async def user_save_api_key(
    req: ApiKeySaveRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    user = require_user_from_authorization(authorization)
    try:
        upsert_user_api_key(user["id"], req.provider, req.api_key)
        return {"api_keys": list_user_api_key_status(user["id"])}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/user/api-keys")
async def user_api_keys(authorization: Optional[str] = Header(None, alias="Authorization")):
    user = require_user_from_authorization(authorization)
    return {"api_keys": list_user_api_key_status(user["id"])}


@app.get("/api/user/business-profiles")
async def user_business_profiles(authorization: Optional[str] = Header(None, alias="Authorization")):
    user = require_user_from_authorization(authorization)
    return {"profiles": list_business_profiles(user["id"])}


@app.post("/api/user/business-profiles")
async def user_save_business_profile(
    req: BusinessProfileRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    user = require_user_from_authorization(authorization)
    try:
        profile = upsert_business_profile(user["id"], req.dict())
        return {"profile": profile, "profiles": list_business_profiles(user["id"])}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/user/claim-legacy-assets")
async def user_claim_legacy_assets(authorization: Optional[str] = Header(None, alias="Authorization")):
    user = require_user_from_authorization(authorization)
    return {"claimed": claim_legacy_assets_for_user(user["id"])}


@app.get("/api/backup/export")
async def export_backup(authorization: Optional[str] = Header(None, alias="Authorization")):
    user = require_user_from_authorization(authorization)
    archive = create_backup_archive(user["id"])
    stamp = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    filename = f"openshorts-backup-{stamp}.zip"
    return Response(
        content=archive,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/backup/import")
async def import_backup(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    require_user_from_authorization(authorization)
    archive = await file.read()
    try:
        return restore_backup_archive(archive)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/admin/subscription")
async def admin_subscription_update(
    req: AdminSubscriptionRequest,
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
):
    admin_token = os.environ.get("OPENSHORTS_ADMIN_TOKEN")
    if not admin_token or x_admin_token != admin_token:
        raise HTTPException(status_code=403, detail="Admin token required")
    try:
        user = set_user_subscription_status(req.user_id, req.status)
        return {"user": user}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _local_saas_video_id(job_dir_name: str) -> str:
    if job_dir_name.startswith("saas_"):
        return job_dir_name.replace("saas_", "", 1)[:8]
    return job_dir_name[:8]


def _local_video_url(job_dir_name: str, file_path: str) -> str:
    return f"/videos/{job_dir_name}/{os.path.basename(file_path)}"


def _strip_url_cache_bust(video_url: str) -> str:
    return urlparse(video_url or "").path or video_url or ""


def _video_version_index(version_id: str) -> Optional[int]:
    text = str(version_id or "").strip().lower()
    if len(text) < 2 or not text.startswith("v") or not text[1:].isdigit():
        return None
    return int(text[1:])


def _lipsync_version_label(model: str) -> str:
    labels = {
        "sync-3": "Sync 3",
        "lipsync-2-pro": "Lipsync 2 Pro",
        "lipsync-2": "Lipsync 2",
    }
    return labels.get(model or "", model or "Lip-sync")


def _with_default_saas_video_versions(meta: Optional[dict]) -> Optional[dict]:
    if not meta or meta.get("versions") or not meta.get("video_url"):
        return meta
    next_meta = dict(meta)
    next_meta["versions"] = [{
        "id": "v001",
        "label": "Original" if not next_meta.get("lipsync_model") else _lipsync_version_label(next_meta.get("lipsync_model")),
        "video_url": _strip_url_cache_bust(next_meta.get("video_url", "")),
        "created_at": next_meta.get("created_at") or _utc_now(),
        "current": True,
        "lipsync_model": next_meta.get("lipsync_model", ""),
        "lipsync_sync_mode": next_meta.get("lipsync_sync_mode", ""),
    }]
    return next_meta


def _build_saas_video_versions(
    previous_meta: dict,
    new_video_url: str,
    lipsync_model: str,
    sync_mode: str,
    lipsync_cost: Optional[float],
    created_at: Optional[str] = None,
) -> List[dict]:
    created_at = created_at or _utc_now()
    previous_meta = previous_meta or {}
    versions = []

    for item in previous_meta.get("versions") or []:
        if not isinstance(item, dict) or not item.get("video_url"):
            continue
        version = dict(item)
        version["video_url"] = _strip_url_cache_bust(version["video_url"])
        version["current"] = False
        versions.append(version)

    previous_current_url = _strip_url_cache_bust(previous_meta.get("video_url", ""))
    if previous_current_url and not any(v.get("video_url") == previous_current_url for v in versions):
        versions.append({
            "id": "v001",
            "label": "Original" if not previous_meta.get("lipsync_model") else _lipsync_version_label(previous_meta.get("lipsync_model")),
            "video_url": previous_current_url,
            "created_at": previous_meta.get("created_at") or created_at,
            "current": False,
            "lipsync_model": previous_meta.get("lipsync_model", ""),
            "lipsync_sync_mode": previous_meta.get("lipsync_sync_mode", ""),
        })

    indexes = [
        index
        for index in (_video_version_index(item.get("id")) for item in versions)
        if index is not None
    ]
    next_index = max(indexes or [len(versions)]) + 1
    new_version = {
        "id": f"v{next_index:03d}",
        "label": _lipsync_version_label(lipsync_model),
        "video_url": _strip_url_cache_bust(new_video_url),
        "created_at": created_at,
        "current": True,
        "lipsync_model": lipsync_model,
        "lipsync_sync_mode": sync_mode,
    }
    if lipsync_cost is not None:
        new_version["lipsync_cost_estimate"] = lipsync_cost
    versions.append(new_version)
    return versions


def _add_saas_lipsync_cost(previous_cost: dict, model: str, lipsync_cost: Optional[float], version_id: str) -> dict:
    cost = dict(previous_cost) if isinstance(previous_cost, dict) else {}
    if lipsync_cost is None:
        return cost

    safe_model = "".join(ch if ch.isalnum() else "_" for ch in (model or "lipsync").lower()).strip("_") or "lipsync"
    safe_version = "".join(ch if ch.isalnum() else "_" for ch in (version_id or "").lower()).strip("_")
    cost_key = f"lipsync_{safe_version}_{safe_model}" if safe_version else f"lipsync_{safe_model}"
    cost[cost_key] = lipsync_cost
    cost["total"] = round(
        sum(v for k, v in cost.items() if k != "total" and isinstance(v, (int, float))),
        2,
    )
    return cost


def _job_id_from_saas_video_url(video_url: str) -> Optional[str]:
    if not video_url:
        return None
    parsed = urlparse(video_url)
    if parsed.scheme or parsed.netloc:
        return None

    parts = parsed.path.strip("/").split("/")
    if len(parts) < 3 or parts[0] != "videos":
        return None

    job_dir = parts[1]
    if not job_dir.startswith("saas_"):
        return None
    job_id = job_dir.replace("saas_", "", 1)
    return job_id or None


def _read_local_gallery_meta(job_dir: str) -> Optional[dict]:
    meta_path = os.path.join(job_dir, "gallery_metadata.json")
    if not os.path.exists(meta_path):
        return None
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            return _with_default_saas_video_versions(json.load(f))
    except Exception:
        return None


def _infer_local_gallery_meta(job_dir: str) -> Optional[dict]:
    job_dir_name = os.path.basename(job_dir)
    video_files = sorted(
        glob.glob(os.path.join(job_dir, "*_final.mp4")),
        key=lambda p: os.path.getmtime(p),
        reverse=True,
    )
    if not video_files:
        return None

    video_path = video_files[0]
    actor_files = []
    for pattern in ("*_actor.png", "selected_actor.png", "__actor.png"):
        actor_files.extend(glob.glob(os.path.join(job_dir, pattern)))
    actor_path = actor_files[0] if actor_files else ""

    job_id = job_dir_name.replace("saas_", "", 1)
    job_result = globals().get("saas_jobs", {}).get(job_id, {}).get("result", {})
    script = job_result.get("script", {}) if isinstance(job_result, dict) else {}
    cost = job_result.get("cost_estimate", {}) if isinstance(job_result, dict) else {}

    return {
        "video_id": _local_saas_video_id(job_dir_name),
        "video_url": _local_video_url(job_dir_name, video_path),
        "actor_url": _local_video_url(job_dir_name, actor_path) if actor_path else "",
        "created_at": datetime.datetime.utcfromtimestamp(os.path.getmtime(video_path)).isoformat() + "Z",
        "title": script.get("title") or os.path.splitext(os.path.basename(video_path))[0],
        "hook_text": script.get("hook_text", ""),
        "caption": script.get("caption", ""),
        "hashtags": script.get("hashtags", []),
        "full_narration": script.get("full_narration", ""),
        "actor_description": script.get("actor_description", ""),
        "style": script.get("style", "ugc"),
        "language": script.get("language", "ru"),
        "duration": job_result.get("duration", 0) if isinstance(job_result, dict) else 0,
        "video_mode": "lowcost" if "hailuo" in " ".join(os.listdir(job_dir)).lower() else "standard",
        "product_name": script.get("_product_name", ""),
        "product_url": script.get("_product_url", ""),
        "segments": script.get("segments", []),
        "cost_estimate": cost,
        "source": "local",
    }


def write_local_saas_gallery_entry(job_id: str, result: dict, metadata: dict, owner_user_id: Optional[str] = None) -> Optional[dict]:
    try:
        job_dir_name = f"saas_{job_id}"
        job_dir = os.path.join(OUTPUT_DIR, job_dir_name)
        video_path = result.get("video_path", "")
        if not video_path or not os.path.exists(video_path):
            return None

        actor_path = result.get("actor_image", "")
        entry = dict(metadata)
        if owner_user_id:
            entry["owner_user_id"] = owner_user_id
        entry.update({
            "video_id": job_id[:8],
            "video_url": _local_video_url(job_dir_name, video_path),
            "actor_url": _local_video_url(job_dir_name, actor_path) if actor_path and os.path.exists(actor_path) else "",
            "created_at": datetime.datetime.utcnow().isoformat() + "Z",
            "source": "local",
        })

        with open(os.path.join(job_dir, "gallery_metadata.json"), "w", encoding="utf-8") as f:
            json.dump(entry, f, ensure_ascii=False, indent=2)
        return entry
    except Exception as e:
        print(f"⚠️ Local gallery metadata write failed: {e}")
        return None


def list_local_saas_gallery(limit: int = 50, owner_user_id: Optional[str] = None) -> List[dict]:
    videos = []
    for job_dir in glob.glob(os.path.join(OUTPUT_DIR, "saas_*")):
        if not os.path.isdir(job_dir):
            continue
        meta = _read_local_gallery_meta(job_dir) or _infer_local_gallery_meta(job_dir)
        if owner_user_id and meta.get("owner_user_id") != owner_user_id:
            continue
        if meta and meta.get("video_url"):
            videos.append(meta)

    videos.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return videos[:limit] if limit else videos


def list_combined_video_gallery(limit: int = 50, owner_user_id: Optional[str] = None) -> List[dict]:
    remote = [] if owner_user_id else (list_video_gallery(limit) or [])
    local = list_local_saas_gallery(limit, owner_user_id=owner_user_id) or []

    combined = []
    seen = set()
    for item in [*local, *remote]:
        key = item.get("video_id") or item.get("video_url")
        if not key or key in seen:
            continue
        seen.add(key)
        combined.append(item)

    combined.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return combined[:limit] if limit else combined


def _head_templates_dir() -> str:
    return os.path.join(OUTPUT_DIR, "head_templates")


def _safe_head_template_id(value: str) -> Optional[str]:
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        return None
    parts = parsed.path.strip("/").split("/")
    if len(parts) >= 3 and parts[0] == "videos" and parts[1] == "head_templates":
        return parts[2]
    if "/" in value or "\\" in value or ".." in value:
        return None
    return value


def _head_template_url(template_id: str, filename: str) -> str:
    return f"/videos/head_templates/{template_id}/{filename}"


def _read_head_template_metadata(template_dir: str) -> Optional[dict]:
    meta_path = os.path.join(template_dir, "metadata.json")
    if not os.path.exists(meta_path):
        return None
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def resolve_head_template_path(template_id_or_url: str, owner_user_id: Optional[str] = None) -> dict:
    template_id = _safe_head_template_id(template_id_or_url)
    if not template_id:
        raise FileNotFoundError("Invalid talking-head template id")

    template_dir = os.path.abspath(os.path.join(_head_templates_dir(), template_id))
    root_dir = os.path.abspath(_head_templates_dir())
    if not template_dir.startswith(root_dir):
        raise FileNotFoundError("Invalid talking-head template path")

    head_path = os.path.join(template_dir, "head.mp4")
    if not os.path.exists(head_path):
        raise FileNotFoundError("Talking-head template video not found")

    poster_path = os.path.join(template_dir, "actor.png")
    metadata = _read_head_template_metadata(template_dir) or {}
    if owner_user_id and metadata.get("owner_user_id") != owner_user_id:
        raise FileNotFoundError("Talking-head template not found for this user")
    return {
        "template_id": template_id,
        "head_path": head_path,
        "poster_path": poster_path if os.path.exists(poster_path) else "",
        "metadata": metadata,
    }


def list_local_head_templates(owner_user_id: Optional[str] = None) -> List[dict]:
    templates = []
    root = _head_templates_dir()
    if not os.path.isdir(root):
        return templates

    for template_dir in glob.glob(os.path.join(root, "*")):
        if not os.path.isdir(template_dir):
            continue
        metadata = _read_head_template_metadata(template_dir)
        if owner_user_id and (not metadata or metadata.get("owner_user_id") != owner_user_id):
            continue
        if metadata and metadata.get("video_url"):
            templates.append(metadata)

    templates.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return templates


def save_local_head_template(job_id: str, label: Optional[str] = None, owner_user_id: Optional[str] = None) -> dict:
    job_dir = os.path.join(OUTPUT_DIR, f"saas_{job_id}")
    if not os.path.isdir(job_dir):
        raise FileNotFoundError("AI Shorts job output not found")

    head_candidates = [
        path for path in glob.glob(os.path.join(job_dir, "*_head.mp4"))
        if "_head_lipsync_" not in os.path.basename(path) and os.path.getsize(path) > 0
    ]
    head_candidates.sort(key=lambda path: os.path.getmtime(path), reverse=True)
    head_path = head_candidates[0] if head_candidates else ""
    if not head_path:
        raise FileNotFoundError("Talking-head source video not found")

    metadata = _read_local_gallery_meta(job_dir) or {}
    existing_owner = metadata.get("owner_user_id")
    if owner_user_id and existing_owner and existing_owner != owner_user_id:
        raise FileNotFoundError("AI Shorts job output not found")
    owner_user_id = owner_user_id or metadata.get("owner_user_id")
    actor_candidates = []
    for pattern in ("*_actor.png", "selected_actor.png", "__actor.png"):
        actor_candidates.extend(glob.glob(os.path.join(job_dir, pattern)))
    actor_candidates = [path for path in actor_candidates if os.path.getsize(path) > 0]
    actor_candidates.sort(key=lambda path: os.path.getmtime(path), reverse=True)

    template_id = f"head_{uuid.uuid4().hex[:10]}"
    template_dir = os.path.join(_head_templates_dir(), template_id)
    os.makedirs(template_dir, exist_ok=True)

    target_head = os.path.join(template_dir, "head.mp4")
    shutil.copy2(head_path, target_head)

    target_actor = os.path.join(template_dir, "actor.png")
    actor_path = actor_candidates[0] if actor_candidates else ""
    if actor_path and os.path.exists(actor_path):
        shutil.copy2(actor_path, target_actor)

    entry = {
        "template_id": template_id,
        "label": label or metadata.get("title") or f"Talking head {template_id[-4:]}",
        "source_job_id": job_id,
        "video_url": _head_template_url(template_id, "head.mp4"),
        "poster_url": _head_template_url(template_id, "actor.png") if os.path.exists(target_actor) else "",
        "created_at": datetime.datetime.utcnow().isoformat() + "Z",
        "duration": metadata.get("duration", 0),
        "language": metadata.get("language", ""),
        "actor_description": metadata.get("actor_description", ""),
        "source_title": metadata.get("title", ""),
        "owner_user_id": owner_user_id or "",
    }
    with open(os.path.join(template_dir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(entry, f, ensure_ascii=False, indent=2)
    return entry

class ProcessRequest(BaseModel):
    url: str

def enqueue_output(out, job_id):
    """Reads output from a subprocess and appends it to jobs logs."""
    try:
        for line in iter(out.readline, b''):
            decoded_line = line.decode('utf-8').strip()
            if decoded_line:
                print(f"📝 [Job Output] {decoded_line}")
                if job_id in jobs:
                    jobs[job_id]['logs'].append(decoded_line)
    except Exception as e:
        print(f"Error reading output for job {job_id}: {e}")
    finally:
        out.close()

async def run_job(job_id, job_data):
    """Executes the subprocess for a specific job."""
    
    cmd = job_data['cmd']
    env = job_data['env']
    output_dir = job_data['output_dir']
    
    jobs[job_id]['status'] = 'processing'
    jobs[job_id]['logs'].append("Job started by worker.")
    print(f"🎬 [run_job] Executing command for {job_id}: {' '.join(cmd)}")
    
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, # Merge stderr to stdout
            env=env,
            cwd=os.getcwd()
        )
        
        # We need to capture logs in a thread because Popen isn't async
        t_log = threading.Thread(target=enqueue_output, args=(process.stdout, job_id))
        t_log.daemon = True
        t_log.start()
        
        # Async wait for process with incremental updates
        start_wait = time.time()
        while process.poll() is None:
            await asyncio.sleep(2)
            
            # Check for partial results every 2 seconds
            # Look for metadata file
            try:
                json_files = glob.glob(os.path.join(output_dir, "*_metadata.json"))
                if json_files:
                    target_json = json_files[0]
                    # Read metadata (it might be being written to, so simple try/except or just read)
                    # Use a lock or just robust read? json.load might fail if file is partial.
                    # Usually main.py writes it once at start (based on my review).
                    if os.path.getsize(target_json) > 0:
                        with open(target_json, 'r') as f:
                            data = json.load(f)
                            
                        base_name = os.path.basename(target_json).replace('_metadata.json', '')
                        clips = data.get('shorts', [])
                        cost_analysis = data.get('cost_analysis')
                        
                        # Check which clips actually exist on disk
                        ready_clips = []
                        for i, clip in enumerate(clips):
                             clip_filename = f"{base_name}_clip_{i+1}.mp4"
                             clip_path = os.path.join(output_dir, clip_filename)
                             if os.path.exists(clip_path) and os.path.getsize(clip_path) > 0:
                                 # Checking if file is growing? For now assume if it exists and main.py moves it there, it's done.
                                 # main.py writes to temp_... then moves to final name. So presence means ready!
                                 clip['video_url'] = f"/videos/{job_id}/{clip_filename}"
                                 ready_clips.append(clip)
                        
                        if ready_clips:
                             jobs[job_id]['result'] = {'clips': ready_clips, 'cost_analysis': cost_analysis}
            except Exception as e:
                # Ignore read errors during processing
                pass

        returncode = process.returncode
        
        if returncode == 0:
            jobs[job_id]['status'] = 'completed'
            jobs[job_id]['logs'].append("Process finished successfully.")
            
            # Start S3 upload in background (silent, non-blocking)
            loop = asyncio.get_event_loop()
            loop.run_in_executor(None, upload_job_artifacts, output_dir, job_id)
            
            # Find result JSON
            json_files = glob.glob(os.path.join(output_dir, "*_metadata.json"))
            if not json_files:
                # Backward-compat rescue if outputs were written to OUTPUT_DIR root
                if _relocate_root_job_artifacts(job_id, output_dir):
                    json_files = glob.glob(os.path.join(output_dir, "*_metadata.json"))
            if json_files:
                target_json = json_files[0] 
                with open(target_json, 'r') as f:
                    data = json.load(f)
                
                # Enhance result with video URLs
                base_name = os.path.basename(target_json).replace('_metadata.json', '')
                clips = data.get('shorts', [])
                cost_analysis = data.get('cost_analysis')

                for i, clip in enumerate(clips):
                     clip_filename = f"{base_name}_clip_{i+1}.mp4"
                     clip['video_url'] = f"/videos/{job_id}/{clip_filename}"
                
                jobs[job_id]['result'] = {'clips': clips, 'cost_analysis': cost_analysis}
            else:
                 jobs[job_id]['status'] = 'failed'
                 jobs[job_id]['logs'].append("No metadata file generated.")
        else:
            jobs[job_id]['status'] = 'failed'
            jobs[job_id]['logs'].append(f"Process failed with exit code {returncode}")
            
    except Exception as e:
        jobs[job_id]['status'] = 'failed'
        jobs[job_id]['logs'].append(f"Execution error: {str(e)}")

@app.get("/api/config")
async def get_config():
    return {"youtubeUrlEnabled": not DISABLE_YOUTUBE_URL}

@app.post("/api/process")
async def process_endpoint(
    request: Request,
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
    acknowledged: Optional[str] = Form(None)
):
    user = get_user_from_authorization(request.headers.get("Authorization"))
    use_platform_keys = request.headers.get("X-Use-Platform-Keys", "").lower() in ("1", "true", "yes")
    ack_flag = str(acknowledged).lower() in ("1", "true", "yes")

    # Handle JSON body manually for URL payload
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        body = await request.json()
        url = body.get("url")
        ack_flag = bool(body.get("acknowledged"))
        if body.get("use_platform_keys") is not None:
            use_platform_keys = bool(body.get("use_platform_keys"))

    try:
        api_key = resolve_effective_api_key(
            "gemini",
            user,
            request.headers.get("X-Gemini-Key"),
            use_platform_keys=use_platform_keys,
        )
    except SubscriptionRequiredError as e:
        raise HTTPException(status_code=402, detail=str(e))
    except PlatformKeyUnavailableError as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not api_key:
        raise HTTPException(status_code=400, detail="Missing Gemini API Key")

    if not url and not file:
        raise HTTPException(status_code=400, detail="Must provide URL or File")

    if not ack_flag:
        raise HTTPException(status_code=400, detail="You must confirm you own the content or have rights to process it.")

    if url and DISABLE_YOUTUBE_URL:
        raise HTTPException(status_code=403, detail="YouTube URL ingest is disabled on this deployment. Please upload a file you own.")

    # Capture attestation context for legal record (IP + timestamp + UA)
    client_ip = request.client.host if request.client else "unknown"
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        client_ip = fwd.split(",")[0].strip()
    user_agent = request.headers.get("user-agent", "")
    attestation = {
        "acknowledged": True,
        "ip": client_ip,
        "user_agent": user_agent,
        "timestamp": time.time(),
        "source": "url" if url else "file",
    }

    job_id = str(uuid.uuid4())
    job_output_dir = os.path.join(OUTPUT_DIR, job_id)
    os.makedirs(job_output_dir, exist_ok=True)

    # Prepare Command
    cmd = ["python", "-u", "main.py"] # -u for unbuffered
    env = os.environ.copy()
    env["GEMINI_API_KEY"] = api_key # Override with key from request

    if url:
        cmd.extend(["-u", url])
    else:
        # Save uploaded file with size limit check
        input_path = os.path.join(UPLOAD_DIR, f"{job_id}_{file.filename}")

        # Read file in chunks to check size
        size = 0
        limit_bytes = MAX_FILE_SIZE_MB * 1024 * 1024

        with open(input_path, "wb") as buffer:
            while content := await file.read(1024 * 1024): # Read 1MB chunks
                size += len(content)
                if size > limit_bytes:
                    os.remove(input_path)
                    shutil.rmtree(job_output_dir)
                    raise HTTPException(status_code=413, detail=f"File too large. Max size {MAX_FILE_SIZE_MB}MB")
                buffer.write(content)

        cmd.extend(["-i", input_path])

    cmd.extend(["-o", job_output_dir])

    print(f"[attestation] job={job_id} ip={attestation['ip']} source={attestation['source']} ack=true")

    # Enqueue Job
    jobs[job_id] = {
        'status': 'queued',
        'logs': [f"Job {job_id} queued."],
        'cmd': cmd,
        'env': env,
        'output_dir': job_output_dir,
        'attestation': attestation
    }

    await job_queue.put(job_id)

    return {"job_id": job_id, "status": "queued"}

@app.get("/api/status/{job_id}")
async def get_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    return {
        "status": job['status'],
        "logs": job['logs'],
        "result": job.get('result')
    }

from editor import VideoEditor
from subtitles import generate_srt, burn_subtitles, generate_srt_from_video
from hooks import add_hook_to_video
from translate import translate_video, get_supported_languages
from thumbnail import analyze_video_for_titles, refine_titles, generate_thumbnail, generate_youtube_description

class EditRequest(BaseModel):
    job_id: str
    clip_index: int
    api_key: Optional[str] = None
    input_filename: Optional[str] = None

@app.post("/api/edit")
async def edit_clip(
    req: EditRequest,
    x_gemini_key: Optional[str] = Header(None, alias="X-Gemini-Key")
):
    # Determine API Key
    final_api_key = req.api_key or x_gemini_key or os.environ.get("GEMINI_API_KEY")
    
    if not final_api_key:
        raise HTTPException(status_code=400, detail="Missing Gemini API Key (Header or Body)")

    if req.job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[req.job_id]
    if 'result' not in job or 'clips' not in job['result']:
        raise HTTPException(status_code=400, detail="Job result not available")
        
    try:
        # Resolve Input Path: Prefer explict input_filename from frontend (chaining edits)
        if req.input_filename:
            # Security: Ensure just a filename, no paths
            safe_name = os.path.basename(req.input_filename)
            input_path = os.path.join(OUTPUT_DIR, req.job_id, safe_name)
            filename = safe_name
        else:
            # Fallback to original clip
            clip = job['result']['clips'][req.clip_index]
            filename = clip['video_url'].split('/')[-1]
            input_path = os.path.join(OUTPUT_DIR, req.job_id, filename)
        
        if not os.path.exists(input_path):
             raise HTTPException(status_code=404, detail=f"Video file not found: {input_path}")

        # Define output path for edited video
        edited_filename = f"edited_{filename}"
        output_path = os.path.join(OUTPUT_DIR, req.job_id, edited_filename)
        
        # Run editing in a thread to avoid blocking main loop
        # Since VideoEditor uses blocking calls (subprocess, API wait)
        def run_edit():
            editor = VideoEditor(api_key=final_api_key)
            
            # SAFE FILE RENAMING STRATEGY (Avoid UnicodeEncodeError in Docker)
            # Create a safe ASCII filename in the same directory
            safe_filename = f"temp_input_{req.job_id}.mp4"
            safe_input_path = os.path.join(OUTPUT_DIR, req.job_id, safe_filename)
            
            # Copy original file to safe path
            # (Copy is safer than rename if something crashes, we keep original)
            shutil.copy(input_path, safe_input_path)
            
            try:
                # 1. Upload (using safe path)
                vid_file = editor.upload_video(safe_input_path)
                
                # 2. Get duration
                import cv2
                cap = cv2.VideoCapture(safe_input_path)
                fps = cap.get(cv2.CAP_PROP_FPS)
                frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                duration = frame_count / fps if fps else 0
                cap.release()
                
                # Load transcript from metadata
                transcript = None
                try:
                    meta_files = glob.glob(os.path.join(OUTPUT_DIR, req.job_id, "*_metadata.json"))
                    if meta_files:
                        with open(meta_files[0], 'r') as f:
                            data = json.load(f)
                            transcript = data.get('transcript')
                except Exception as e:
                    print(f"⚠️ Could not load transcript for editing context: {e}")

                # 3. Get Plan (Filter String)
                filter_data = editor.get_ffmpeg_filter(vid_file, duration, fps=fps, width=width, height=height, transcript=transcript)
                
                # 4. Apply
                # Use safe output name first
                safe_output_path = os.path.join(OUTPUT_DIR, req.job_id, f"temp_output_{req.job_id}.mp4")
                editor.apply_edits(safe_input_path, safe_output_path, filter_data)
                
                # Move result to final destination (rename works even if dest name has unicode if filesystem supports it, 
                # but python might still struggle if locale is broken? No, os.rename usually handles it better than subprocess args)
                # Actually, output_path is defined above: f"edited_{filename}"
                # If filename has unicode, output_path has unicode.
                # Let's hope shutil.move / os.rename works.
                if os.path.exists(safe_output_path):
                    shutil.move(safe_output_path, output_path)
                
                return filter_data
            finally:
                # Cleanup temp safe input
                if os.path.exists(safe_input_path):
                    os.remove(safe_input_path)

        # Run in thread pool
        loop = asyncio.get_event_loop()
        plan = await loop.run_in_executor(None, run_edit)
        
        # Update clip URL in the job result? 
        # Or return new URL and let frontend handle it?
        # Updating job result allows persistence if page refreshes.
        
        new_video_url = f"/videos/{req.job_id}/{edited_filename}"
        
        # Start a new "edited" clip entry or just update the current one?
        # Let's update the current one's video_url but keep backup?
        # Or return the new URL to the frontend to display.
        
        return {
            "success": True, 
            "new_video_url": new_video_url,
            "edit_plan": plan
        }

    except Exception as e:
        print(f"❌ Edit Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class SubtitleRequest(BaseModel):
    job_id: str
    clip_index: int
    position: str = "bottom" # top, middle, bottom
    font_size: int = 16
    font_name: str = "Verdana"
    font_color: str = "#FFFFFF"
    border_color: str = "#000000"
    border_width: int = 2
    bg_color: str = "#000000"
    bg_opacity: float = 0.0
    input_filename: Optional[str] = None


@app.get("/api/clip/{job_id}/{clip_index}/transcript")
async def get_clip_transcript(job_id: str, clip_index: int):
    """Return word-level captions for a specific clip, formatted for Remotion."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    output_dir = os.path.join(OUTPUT_DIR, job_id)
    json_files = glob.glob(os.path.join(output_dir, "*_metadata.json"))

    if not json_files:
        raise HTTPException(status_code=404, detail="Metadata not found")

    with open(json_files[0], 'r') as f:
        data = json.load(f)

    transcript = data.get('transcript')
    if not transcript:
        raise HTTPException(status_code=400, detail="Transcript not found in metadata")

    clips = data.get('shorts', [])
    if clip_index >= len(clips):
        raise HTTPException(status_code=404, detail="Clip not found")

    clip_data = clips[clip_index]
    clip_start = clip_data.get('start', 0)
    clip_end = clip_data.get('end', 0)

    # Extract words within clip range and convert to CaptionWord format
    captions = []
    for segment in transcript.get('segments', []):
        for word_info in segment.get('words', []):
            if word_info['end'] > clip_start and word_info['start'] < clip_end:
                captions.append({
                    "text": word_info.get('word', '').strip(),
                    "startMs": int((max(0, word_info['start'] - clip_start)) * 1000),
                    "endMs": int((max(0, word_info['end'] - clip_start)) * 1000),
                })

    duration_sec = clip_end - clip_start

    return {
        "captions": captions,
        "durationSec": duration_sec,
        "language": transcript.get('language', 'en'),
    }


# --- Remotion Render Proxy ---
RENDER_SERVICE_URL = os.getenv("RENDER_SERVICE_URL", "http://renderer:3100")

@app.post("/api/render")
async def proxy_render(request: Request):
    """Proxy render requests to the Node.js Remotion render service."""
    import httpx
    body = await request.json()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{RENDER_SERVICE_URL}/render", json=body)
            return resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Render service unavailable: {e}")

@app.get("/api/render/{render_id}")
async def proxy_render_status(render_id: str):
    """Proxy render status polling to the Node.js Remotion render service."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{RENDER_SERVICE_URL}/render/{render_id}")
            return resp.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Render service unavailable: {e}")


class EffectsGenerateRequest(BaseModel):
    job_id: str
    clip_index: int
    input_filename: Optional[str] = None

@app.post("/api/effects/generate")
async def generate_effects_config(
    req: EffectsGenerateRequest,
    x_gemini_key: Optional[str] = Header(None, alias="X-Gemini-Key")
):
    """Generate structured EffectsConfig JSON for Remotion rendering via Gemini AI."""
    final_api_key = x_gemini_key or os.environ.get("GEMINI_API_KEY")

    if not final_api_key:
        raise HTTPException(status_code=400, detail="Missing Gemini API Key (Header)")

    if req.job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[req.job_id]
    if 'result' not in job or 'clips' not in job['result']:
        raise HTTPException(status_code=400, detail="Job result not available")

    try:
        # Resolve input path
        if req.input_filename:
            safe_name = os.path.basename(req.input_filename)
            input_path = os.path.join(OUTPUT_DIR, req.job_id, safe_name)
        else:
            clip = job['result']['clips'][req.clip_index]
            filename = clip['video_url'].split('/')[-1]
            input_path = os.path.join(OUTPUT_DIR, req.job_id, filename)

        if not os.path.exists(input_path):
            raise HTTPException(status_code=404, detail=f"Video file not found: {input_path}")

        def run_effects_generation():
            editor = VideoEditor(api_key=final_api_key)

            # Create safe ASCII filename to avoid encoding issues
            safe_filename = f"temp_effects_{req.job_id}.mp4"
            safe_input_path = os.path.join(OUTPUT_DIR, req.job_id, safe_filename)
            shutil.copy(input_path, safe_input_path)

            try:
                # Upload video to Gemini
                vid_file = editor.upload_video(safe_input_path)

                # Get video metadata via ffprobe
                probe_cmd = [
                    'ffprobe', '-v', 'error',
                    '-select_streams', 'v:0',
                    '-show_entries', 'stream=width,height,r_frame_rate,duration',
                    '-show_entries', 'format=duration',
                    '-of', 'json',
                    safe_input_path
                ]
                probe_result = subprocess.check_output(probe_cmd).decode().strip()
                probe_data = json.loads(probe_result)

                stream = probe_data.get('streams', [{}])[0]
                width = int(stream.get('width', 1080))
                height = int(stream.get('height', 1920))

                # Parse fps from r_frame_rate (e.g. "30/1")
                r_frame_rate = stream.get('r_frame_rate', '30/1')
                num, den = r_frame_rate.split('/')
                fps = round(int(num) / int(den), 2)

                # Get duration from stream or format
                duration = float(stream.get('duration', 0))
                if duration == 0:
                    duration = float(probe_data.get('format', {}).get('duration', 0))

                # Load transcript from metadata
                transcript = None
                try:
                    meta_files = glob.glob(os.path.join(OUTPUT_DIR, req.job_id, "*_metadata.json"))
                    if meta_files:
                        with open(meta_files[0], 'r') as f:
                            data = json.load(f)
                            transcript = data.get('transcript')
                except Exception as e:
                    print(f"⚠️ Could not load transcript for effects config: {e}")

                # Generate effects config
                effects_config = editor.get_effects_config(
                    vid_file, duration, fps=fps, width=width, height=height, transcript=transcript
                )

                return effects_config
            finally:
                if os.path.exists(safe_input_path):
                    os.remove(safe_input_path)

        loop = asyncio.get_event_loop()
        effects_config = await loop.run_in_executor(None, run_effects_generation)

        if effects_config is None:
            raise HTTPException(status_code=500, detail="Failed to generate effects config from Gemini")

        return {"effects": effects_config}

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Effects Generation Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/subtitle")
async def add_subtitles(req: SubtitleRequest):
    if req.job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Reload job data from disk just in case metadata was updated
    job = jobs[req.job_id]
    
    # We need to access metadata.json to get the transcript
    output_dir = os.path.join(OUTPUT_DIR, req.job_id)
    json_files = glob.glob(os.path.join(output_dir, "*_metadata.json"))
    
    if not json_files:
        raise HTTPException(status_code=404, detail="Metadata not found")
        
    with open(json_files[0], 'r') as f:
        data = json.load(f)
        
    transcript = data.get('transcript')
    if not transcript:
        raise HTTPException(status_code=400, detail="Transcript not found in metadata. Please process a new video.")
        
    clips = data.get('shorts', [])
    if req.clip_index >= len(clips):
        raise HTTPException(status_code=404, detail="Clip not found")
        
    clip_data = clips[req.clip_index]
    
    # Video Path
    if req.input_filename:
        # Use chained file
        filename = os.path.basename(req.input_filename)
    else:
        # Fallback to standard naming
        filename = clip_data.get('video_url', '').split('/')[-1]
        if not filename:
             base_name = os.path.basename(json_files[0]).replace('_metadata.json', '')
             filename = f"{base_name}_clip_{req.clip_index+1}.mp4"
         
    input_path = os.path.join(output_dir, filename)
    if not os.path.exists(input_path):
        # Try looking for edited version if url implied it?
        # Just fail if not found.
        raise HTTPException(status_code=404, detail=f"Video file not found: {input_path}")
        
    # Define outputs
    srt_filename = f"subs_{req.clip_index}_{int(time.time())}.srt"
    srt_path = os.path.join(output_dir, srt_filename)
    
    # Output video
    # We create a new file "subtitled_..."
    output_filename = f"subtitled_{filename}"
    output_path = os.path.join(output_dir, output_filename)
    
    try:
        # 1. Generate SRT
        # Check if this is a dubbed video - if so, transcribe it fresh
        is_dubbed = filename.startswith("translated_")

        if is_dubbed:
            print(f"🎙️ Dubbed video detected, transcribing audio for subtitles...")
            def run_transcribe_srt():
                return generate_srt_from_video(input_path, srt_path)

            loop = asyncio.get_event_loop()
            success = await loop.run_in_executor(None, run_transcribe_srt)
        else:
            success = generate_srt(transcript, clip_data['start'], clip_data['end'], srt_path)

        if not success:
             raise HTTPException(status_code=400, detail="No words found for this clip range.")

        # 2. Burn Subtitles
        # Run in thread pool
        def run_burn():
             burn_subtitles(input_path, srt_path, output_path,
                           alignment=req.position, fontsize=req.font_size,
                           font_name=req.font_name, font_color=req.font_color,
                           border_color=req.border_color, border_width=req.border_width,
                           bg_color=req.bg_color, bg_opacity=req.bg_opacity)
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, run_burn)
        
    except Exception as e:
        print(f"❌ Subtitle Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
        
    # 3. Update Result and Metadata
    # Update InMemory Jobs
    if req.clip_index < len(job['result']['clips']):
         job['result']['clips'][req.clip_index]['video_url'] = f"/videos/{req.job_id}/{output_filename}"
    
    # Update Metadata on Disk (Persistence)
    try:
        if req.clip_index < len(clips):
            clips[req.clip_index]['video_url'] = f"/videos/{req.job_id}/{output_filename}"
            # Update the main data structure
            data['shorts'] = clips
            
            # Write back
            with open(json_files[0], 'w') as f:
                json.dump(data, f, indent=4)
                print(f"✅ Metadata updated with subtitled video for clip {req.clip_index}")
    except Exception as e:
        print(f"⚠️ Failed to update metadata.json: {e}")
        # Non-critical, but good for persistence

    return {
        "success": True,
        "new_video_url": f"/videos/{req.job_id}/{output_filename}"
    }

class HookRequest(BaseModel):
    job_id: str
    clip_index: int
    text: str
    input_filename: Optional[str] = None
    position: Optional[str] = "top" # top, center, bottom
    size: Optional[str] = "M" # S, M, L

@app.post("/api/hook")
async def add_hook(req: HookRequest):
    if req.job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[req.job_id]
    output_dir = os.path.join(OUTPUT_DIR, req.job_id)
    json_files = glob.glob(os.path.join(output_dir, "*_metadata.json"))
    
    if not json_files:
        raise HTTPException(status_code=404, detail="Metadata not found")
        
    with open(json_files[0], 'r') as f:
        data = json.load(f)
        
    clips = data.get('shorts', [])
    if req.clip_index >= len(clips):
        raise HTTPException(status_code=404, detail="Clip not found")
        
    clip_data = clips[req.clip_index]
    
    # Video Path
    if req.input_filename:
        filename = os.path.basename(req.input_filename)
    else:
        filename = clip_data.get('video_url', '').split('/')[-1]
        if not filename:
             base_name = os.path.basename(json_files[0]).replace('_metadata.json', '')
             filename = f"{base_name}_clip_{req.clip_index+1}.mp4"
         
    input_path = os.path.join(output_dir, filename)
    if not os.path.exists(input_path):
        raise HTTPException(status_code=404, detail=f"Video file not found: {input_path}")
        
    # Output video
    output_filename = f"hook_{filename}"
    output_path = os.path.join(output_dir, output_filename)
    
    # Map Size to Scale
    size_map = {"S": 0.8, "M": 1.0, "L": 1.3}
    font_scale = size_map.get(req.size, 1.0)
    
    try:
        # Run in thread pool
        def run_hook():
             add_hook_to_video(input_path, req.text, output_path, position=req.position, font_scale=font_scale)
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, run_hook)
        
    except Exception as e:
        print(f"❌ Hook Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
        
    # Update Persistence (Same logic as subtitles)
    # Update InMemory Jobs
    if req.clip_index < len(job['result']['clips']):
         job['result']['clips'][req.clip_index]['video_url'] = f"/videos/{req.job_id}/{output_filename}"
    
    # Update Metadata on Disk
    try:
        if req.clip_index < len(clips):
            clips[req.clip_index]['video_url'] = f"/videos/{req.job_id}/{output_filename}"
            data['shorts'] = clips
            with open(json_files[0], 'w') as f:
                json.dump(data, f, indent=4)
                print(f"✅ Metadata updated with hook video for clip {req.clip_index}")
    except Exception as e:
        print(f"⚠️ Failed to update metadata.json: {e}")

    return {
        "success": True,
        "new_video_url": f"/videos/{req.job_id}/{output_filename}"
    }

class TranslateRequest(BaseModel):
    job_id: str
    clip_index: int
    target_language: str
    source_language: Optional[str] = None
    input_filename: Optional[str] = None

@app.get("/api/translate/languages")
async def get_languages():
    """Return supported languages for translation."""
    return {"languages": get_supported_languages()}

@app.post("/api/translate")
async def translate_clip(
    req: TranslateRequest,
    x_elevenlabs_key: Optional[str] = Header(None, alias="X-ElevenLabs-Key")
):
    """Translate a video clip to a different language using ElevenLabs dubbing."""
    if not x_elevenlabs_key:
        raise HTTPException(status_code=400, detail="Missing X-ElevenLabs-Key header")

    if req.job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[req.job_id]
    output_dir = os.path.join(OUTPUT_DIR, req.job_id)
    json_files = glob.glob(os.path.join(output_dir, "*_metadata.json"))

    if not json_files:
        raise HTTPException(status_code=404, detail="Metadata not found")

    with open(json_files[0], 'r') as f:
        data = json.load(f)

    clips = data.get('shorts', [])
    if req.clip_index >= len(clips):
        raise HTTPException(status_code=404, detail="Clip not found")

    clip_data = clips[req.clip_index]

    # Video Path
    if req.input_filename:
        filename = os.path.basename(req.input_filename)
    else:
        filename = clip_data.get('video_url', '').split('/')[-1]
        if not filename:
             base_name = os.path.basename(json_files[0]).replace('_metadata.json', '')
             filename = f"{base_name}_clip_{req.clip_index+1}.mp4"

    input_path = os.path.join(output_dir, filename)
    if not os.path.exists(input_path):
        raise HTTPException(status_code=404, detail=f"Video file not found: {input_path}")

    # Output video with language suffix
    base, ext = os.path.splitext(filename)
    output_filename = f"translated_{req.target_language}_{base}{ext}"
    output_path = os.path.join(output_dir, output_filename)

    try:
        # Run translation in thread pool (blocking API calls)
        def run_translate():
            return translate_video(
                video_path=input_path,
                output_path=output_path,
                target_language=req.target_language,
                api_key=x_elevenlabs_key,
                source_language=req.source_language,
            )

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, run_translate)

    except Exception as e:
        print(f"❌ Translation Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    # Update InMemory Jobs
    if req.clip_index < len(job['result']['clips']):
         job['result']['clips'][req.clip_index]['video_url'] = f"/videos/{req.job_id}/{output_filename}"

    # Update Metadata on Disk
    try:
        if req.clip_index < len(clips):
            clips[req.clip_index]['video_url'] = f"/videos/{req.job_id}/{output_filename}"
            data['shorts'] = clips
            with open(json_files[0], 'w') as f:
                json.dump(data, f, indent=4)
                print(f"✅ Metadata updated with translated video for clip {req.clip_index}")
    except Exception as e:
        print(f"⚠️ Failed to update metadata.json: {e}")

    return {
        "success": True,
        "new_video_url": f"/videos/{req.job_id}/{output_filename}"
    }

class SocialPostRequest(BaseModel):
    job_id: str
    clip_index: int
    api_key: Optional[str] = None
    user_id: str
    platforms: List[str] # ["tiktok", "instagram", "youtube"]
    # Optional overrides if frontend wants to edit them
    title: Optional[str] = None
    description: Optional[str] = None
    scheduled_date: Optional[str] = None # ISO-8601 string
    timezone: Optional[str] = "UTC"
    use_platform_keys: bool = False

import httpx

@app.post("/api/social/post")
async def post_to_socials(
    req: SocialPostRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    user = get_user_from_authorization(authorization)
    header_key = req.api_key if req.api_key not in ("__saved__", "__platform__") else None
    try:
        upload_key = resolve_effective_api_key("upload_post", user, header_key, req.use_platform_keys)
    except SubscriptionRequiredError as e:
        raise HTTPException(status_code=402, detail=str(e))
    except PlatformKeyUnavailableError as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not upload_key:
        raise HTTPException(status_code=400, detail="Missing Upload-Post API Key")

    if req.job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[req.job_id]
    if 'result' not in job or 'clips' not in job['result']:
        raise HTTPException(status_code=400, detail="Job result not available")
        
    try:
        clip = job['result']['clips'][req.clip_index]
        # Video URL is relative /videos/..., we need absolute file path
        # clip['video_url'] is like "/videos/{job_id}/{filename}"
        # We constructed it as: f"/videos/{job_id}/{clip_filename}"
        # And file is at f"{OUTPUT_DIR}/{job_id}/{clip_filename}"
        
        filename = clip['video_url'].split('/')[-1]
        file_path = os.path.join(OUTPUT_DIR, req.job_id, filename)
        
        if not os.path.exists(file_path):
             raise HTTPException(status_code=404, detail=f"Video file not found: {file_path}")

        # Construct parameters for Upload-Post API
        # Fallbacks
        final_title = req.title or clip.get('title', 'Viral Short')
        final_description = req.description or clip.get('video_description_for_instagram') or clip.get('video_description_for_tiktok') or "Check this out!"
        
        # Prepare form data
        url = "https://api.upload-post.com/api/upload"
        headers = {"Authorization": f"Apikey {upload_key}"}
        
        # Prepare data as dict (httpx handles lists for multiple values)
        data_payload = {
            "user": req.user_id,
            "title": final_title,
            "platform[]": req.platforms, # Pass list directly
            "async_upload": "true"  # Enable async upload
        }

        # Add scheduling if present
        if req.scheduled_date:
            data_payload["scheduled_date"] = req.scheduled_date
            if req.timezone:
                data_payload["timezone"] = req.timezone
        
        # Add Platform specifics
        if "tiktok" in req.platforms:
             data_payload["tiktok_title"] = final_description
             
        if "instagram" in req.platforms:
             data_payload["instagram_title"] = final_description
             data_payload["media_type"] = "REELS"

        if "youtube" in req.platforms:
             yt_title = req.title or clip.get('video_title_for_youtube_short', final_title)
             data_payload["youtube_title"] = yt_title
             data_payload["youtube_description"] = final_description
             data_payload["privacyStatus"] = "public"

        # Send File
        # httpx AsyncClient requires async file reading or bytes. 
        # Since we have MAX_FILE_SIZE_MB, reading into memory is safe-ish.
        with open(file_path, "rb") as f:
            file_content = f.read()
            
        files = {
            "video": (filename, file_content, "video/mp4")
        }

        # Switch to synchronous Client to avoid "sync request with AsyncClient" error with multipart/files
        with httpx.Client(timeout=120.0) as client:
            print(f"📡 Sending to Upload-Post for platforms: {req.platforms}")
            response = client.post(url, headers=headers, data=data_payload, files=files)
            
        if response.status_code not in [200, 201, 202]: # Added 201
             print(f"❌ Upload-Post Error: {response.text}")
             raise HTTPException(status_code=response.status_code, detail=f"Vendor API Error: {response.text}")

        return response.json()

    except Exception as e:
        print(f"❌ Social Post Exception: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/social/user")
async def get_social_user(
    api_key: Optional[str] = Header(None, alias="X-Upload-Post-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    use_platform_keys: bool = False,
):
    """Proxy to fetch user ID from Upload-Post"""
    user = get_user_from_authorization(authorization)
    try:
        api_key = resolve_effective_api_key("upload_post", user, api_key, use_platform_keys)
    except SubscriptionRequiredError as e:
        raise HTTPException(status_code=402, detail=str(e))
    except PlatformKeyUnavailableError as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not api_key:
         raise HTTPException(status_code=400, detail="Missing X-Upload-Post-Key header")
         
    url = "https://api.upload-post.com/api/uploadposts/users"
    print(f"🔍 Fetching User ID from: {url}")
    headers = {"Authorization": f"Apikey {api_key}"}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(url, headers=headers)
            if resp.status_code != 200:
                print(f"❌ Upload-Post User Fetch Error: {resp.text}")
                raise HTTPException(status_code=resp.status_code, detail=f"Failed to fetch user: {resp.text}")
            
            data = resp.json()
            print(f"🔍 Upload-Post User Response: {data}")
            
            user_id = None
            # The structure is {'success': True, 'profiles': [{'username': '...'}, ...]}
            profiles_list = []
            if isinstance(data, dict):
                 raw_profiles = data.get('profiles', [])
                 if isinstance(raw_profiles, list):
                     for p in raw_profiles:
                         username = p.get('username')
                         if username:
                             # Determine connected platforms
                             socials = p.get('social_accounts', {})
                             connected = []
                             # Check typical platforms
                             for platform in ['tiktok', 'instagram', 'youtube']:
                                 account_info = socials.get(platform)
                                 # If it's a dict and typically has data, or just not empty string
                                 if isinstance(account_info, dict):
                                     connected.append(platform)
                             
                             profiles_list.append({
                                 "username": username,
                                 "connected": connected
                             })
            
            if not profiles_list:
                # Fallback if no profiles found
                return {"profiles": [], "error": "No profiles found"}
                
            return {"profiles": profiles_list}
            
            
        except Exception as e:
             raise HTTPException(status_code=500, detail=str(e))

# --- Thumbnail Studio Endpoints ---

@app.post("/api/thumbnail/upload")
async def thumbnail_upload(
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
):
    """Upload video and start background Whisper transcription immediately."""
    if not url and not file:
        raise HTTPException(status_code=400, detail="Must provide URL or File")

    session_id = str(uuid.uuid4())
    transcript_event = asyncio.Event()

    # Save file if uploaded directly
    video_path = None
    if file:
        video_path = os.path.join(UPLOAD_DIR, f"thumb_{session_id}_{file.filename}")
        with open(video_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

    # Initialize session
    thumbnail_sessions[session_id] = {
        "video_path": video_path,
        "transcript_event": transcript_event,
        "transcript_ready": False,
        "transcript": None,
        "transcript_segments": [],
        "video_duration": 0,
        "language": "en",
        "context": "",
        "titles": [],
        "conversation": [],
        "_url": url,  # Store URL for deferred download
    }

    async def run_background_whisper():
        try:
            vpath = video_path
            # Download YouTube video if URL was provided
            if not vpath and url:
                from main import download_youtube_video
                loop = asyncio.get_event_loop()
                vpath, _ = await loop.run_in_executor(None, download_youtube_video, url, UPLOAD_DIR)
                thumbnail_sessions[session_id]["video_path"] = vpath

            from main import transcribe_video
            loop = asyncio.get_event_loop()
            transcript = await loop.run_in_executor(None, transcribe_video, vpath)
            segments = transcript.get("segments", [])
            duration = segments[-1]["end"] if segments else 0

            thumbnail_sessions[session_id].update({
                "transcript_ready": True,
                "transcript": transcript,
                "transcript_segments": segments,
                "video_duration": duration,
                "language": transcript.get("language", "en"),
            })
            print(f"✅ [Thumbnail] Background Whisper complete for session {session_id}")
        except Exception as e:
            print(f"❌ [Thumbnail] Background Whisper failed: {e}")
            thumbnail_sessions[session_id]["transcript_error"] = str(e)
        finally:
            transcript_event.set()

    asyncio.create_task(run_background_whisper())

    return {"session_id": session_id}


@app.post("/api/thumbnail/analyze")
async def thumbnail_analyze(
    request: Request,
    file: Optional[UploadFile] = File(None),
    url: Optional[str] = Form(None),
    session_id: Optional[str] = Form(None),
    x_gemini_key: Optional[str] = Header(None, alias="X-Gemini-Key")
):
    """Analyze a video and suggest viral YouTube titles."""
    api_key = x_gemini_key
    if not api_key:
        raise HTTPException(status_code=400, detail="Missing X-Gemini-Key header")

    pre_transcript = None

    # Check for pre-existing session with background Whisper
    if session_id and session_id in thumbnail_sessions:
        session = thumbnail_sessions[session_id]

        # Wait for background Whisper to complete
        transcript_event = session.get("transcript_event")
        if transcript_event:
            print(f"⏳ [Thumbnail] Waiting for background Whisper to finish...")
            await transcript_event.wait()

        if session.get("transcript_error"):
            raise HTTPException(status_code=500, detail=f"Transcription failed: {session['transcript_error']}")

        video_path = session["video_path"]
        if not video_path or not os.path.exists(video_path):
            raise HTTPException(status_code=404, detail="Video file not found in session")

        if session.get("transcript_ready"):
            pre_transcript = session["transcript"]
    else:
        # No pre-existing session — need file or URL
        if not url and not file:
            raise HTTPException(status_code=400, detail="Must provide URL, File, or session_id")

        session_id = str(uuid.uuid4())

        if url:
            from main import download_youtube_video
            video_path, _ = download_youtube_video(url, UPLOAD_DIR)
        else:
            video_path = os.path.join(UPLOAD_DIR, f"thumb_{session_id}_{file.filename}")
            with open(video_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)

    try:
        # Run analysis in thread pool (skips Whisper if pre_transcript is available)
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, analyze_video_for_titles, api_key, video_path, pre_transcript)

        # Store/update session context
        if session_id not in thumbnail_sessions:
            thumbnail_sessions[session_id] = {}

        thumbnail_sessions[session_id].update({
            "context": result.get("transcript_summary", ""),
            "titles": result.get("titles", []),
            "language": result.get("language", "en"),
            "conversation": thumbnail_sessions[session_id].get("conversation", []),
            "video_path": video_path,
            "transcript_segments": result.get("segments", []),
            "video_duration": result.get("video_duration", 0)
        })

        return {
            "session_id": session_id,
            "titles": result.get("titles", []),
            "context": result.get("transcript_summary", ""),
            "language": result.get("language", "en"),
            "recommended": result.get("recommended", [])
        }

    except Exception as e:
        print(f"❌ Thumbnail Analyze Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ThumbnailTitlesRequest(BaseModel):
    session_id: Optional[str] = None
    message: Optional[str] = None
    title: Optional[str] = None

@app.post("/api/thumbnail/titles")
async def thumbnail_titles(
    req: ThumbnailTitlesRequest,
    x_gemini_key: Optional[str] = Header(None, alias="X-Gemini-Key")
):
    """Refine title suggestions or accept a manual title."""
    api_key = x_gemini_key
    if not api_key:
        raise HTTPException(status_code=400, detail="Missing X-Gemini-Key header")

    # Manual title mode - just create a session with the user's title
    if req.title:
        session_id = req.session_id or str(uuid.uuid4())
        if session_id not in thumbnail_sessions:
            thumbnail_sessions[session_id] = {
                "context": "",
                "titles": [req.title],
                "language": "en",
                "conversation": []
            }
        return {"session_id": session_id, "titles": [req.title]}

    # Refinement mode
    if not req.session_id or req.session_id not in thumbnail_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    if not req.message:
        raise HTTPException(status_code=400, detail="Must provide message or title")

    session = thumbnail_sessions[req.session_id]

    # Add user message to conversation history
    session["conversation"].append({"role": "user", "content": req.message})

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            refine_titles,
            api_key,
            session["context"],
            req.message,
            session["conversation"]
        )

        new_titles = result.get("titles", [])
        session["titles"] = new_titles
        session["conversation"].append({"role": "assistant", "content": json.dumps(new_titles)})

        return {"titles": new_titles}

    except Exception as e:
        print(f"❌ Thumbnail Titles Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/thumbnail/generate")
async def thumbnail_generate(
    request: Request,
    session_id: str = Form(...),
    title: str = Form(...),
    extra_prompt: str = Form(""),
    count: int = Form(3),
    face: Optional[UploadFile] = File(None),
    background: Optional[UploadFile] = File(None),
    x_gemini_key: Optional[str] = Header(None, alias="X-Gemini-Key")
):
    """Generate YouTube thumbnails with Gemini image generation."""
    api_key = x_gemini_key
    if not api_key:
        raise HTTPException(status_code=400, detail="Missing X-Gemini-Key header")

    # Clamp count
    count = min(max(1, count), 6)

    # Save optional uploaded images
    face_path = None
    bg_path = None
    thumb_upload_dir = os.path.join(UPLOAD_DIR, f"thumb_{session_id}")
    os.makedirs(thumb_upload_dir, exist_ok=True)

    try:
        if face and face.filename:
            face_path = os.path.join(thumb_upload_dir, f"face_{face.filename}")
            with open(face_path, "wb") as f:
                f.write(await face.read())

        if background and background.filename:
            bg_path = os.path.join(thumb_upload_dir, f"bg_{background.filename}")
            with open(bg_path, "wb") as f:
                f.write(await background.read())

        # Get video context from session (transcript summary from analysis step)
        video_context = ""
        if session_id in thumbnail_sessions:
            video_context = thumbnail_sessions[session_id].get("context", "")

        # Run generation in thread pool
        loop = asyncio.get_event_loop()
        thumbnails = await loop.run_in_executor(
            None,
            generate_thumbnail,
            api_key,
            title,
            session_id,
            face_path,
            bg_path,
            extra_prompt,
            count,
            video_context
        )

        if not thumbnails:
            raise HTTPException(status_code=500, detail="Thumbnail generation failed. Please check your Gemini API key has access to image generation (gemini-3.1-flash-image-preview model).")

        return {"thumbnails": thumbnails}

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Thumbnail Generate Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ThumbnailDescribeRequest(BaseModel):
    session_id: str
    title: str

@app.post("/api/thumbnail/describe")
async def thumbnail_describe(
    req: ThumbnailDescribeRequest,
    x_gemini_key: Optional[str] = Header(None, alias="X-Gemini-Key")
):
    """Generate a YouTube description with chapters from the transcript."""
    api_key = x_gemini_key
    if not api_key:
        raise HTTPException(status_code=400, detail="Missing X-Gemini-Key header")

    if req.session_id not in thumbnail_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = thumbnail_sessions[req.session_id]
    segments = session.get("transcript_segments", [])
    if not segments:
        raise HTTPException(status_code=400, detail="No transcript segments available. Please analyze a video first.")

    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            generate_youtube_description,
            api_key,
            req.title,
            segments,
            session.get("language", "en"),
            session.get("video_duration", 0)
        )
        return {"description": result.get("description", "")}

    except Exception as e:
        print(f"❌ Thumbnail Describe Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/thumbnail/publish")
async def thumbnail_publish(
    background_tasks: BackgroundTasks,
    session_id: str = Form(...),
    title: str = Form(...),
    description: str = Form(...),
    thumbnail_url: str = Form(...),
    api_key: str = Form(...),
    user_id: str = Form(...),
):
    """Kick off a background upload to YouTube via Upload-Post and return immediately."""
    if session_id not in thumbnail_sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = thumbnail_sessions[session_id]
    video_path = session.get("video_path")
    if not video_path or not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail="Original video file not found")

    # Resolve thumbnail path from URL
    thumb_relative = thumbnail_url.lstrip("/")
    if thumb_relative.startswith("thumbnails/"):
        thumb_path = os.path.join(OUTPUT_DIR, thumb_relative)
    else:
        thumb_path = os.path.join(THUMBNAILS_DIR, thumb_relative)

    if not os.path.exists(thumb_path):
        raise HTTPException(status_code=404, detail=f"Thumbnail file not found: {thumb_path}")

    # Generate a unique ID for this publish job so the frontend can poll
    publish_id = str(uuid.uuid4())
    publish_jobs[publish_id] = {"status": "uploading", "result": None, "error": None}

    def do_upload():
        """Runs in a thread via BackgroundTasks — does the actual multipart upload."""
        try:
            upload_url = "https://api.upload-post.com/api/upload"
            headers = {"Authorization": f"Apikey {api_key}"}
            data_payload = {
                "user": user_id,
                "platform[]": ["youtube"],
                "title": title,          # required base field (fallback)
                "async_upload": "true",
                "youtube_title": title,
                "youtube_description": description,
                "privacyStatus": "public",
            }
            video_filename = os.path.basename(video_path)
            thumb_filename = os.path.basename(thumb_path)

            print(f"📡 [Thumbnail] Publishing to YouTube via Upload-Post... (publish_id={publish_id})")
            with open(video_path, "rb") as vf, open(thumb_path, "rb") as tf:
                files = {
                    "video": (video_filename, vf.read(), "video/mp4"),
                    "thumbnail": (thumb_filename, tf.read(), "image/jpeg"),
                }

            # Use a long timeout — video uploads can take several minutes
            with httpx.Client(timeout=600.0) as client:
                response = client.post(upload_url, headers=headers, data=data_payload, files=files)

            if response.status_code not in [200, 201, 202]:
                err = f"Upload-Post API Error ({response.status_code}): {response.text}"
                print(f"❌ {err}")
                publish_jobs[publish_id]["status"] = "failed"
                publish_jobs[publish_id]["error"] = err
            else:
                print(f"✅ [Thumbnail] Published successfully (publish_id={publish_id})")
                publish_jobs[publish_id]["status"] = "done"
                publish_jobs[publish_id]["result"] = response.json()

        except Exception as e:
            err = str(e)
            print(f"❌ Thumbnail Publish Background Error: {err}")
            publish_jobs[publish_id]["status"] = "failed"
            publish_jobs[publish_id]["error"] = err

    background_tasks.add_task(do_upload)
    return {"publish_id": publish_id, "status": "uploading"}


@app.get("/api/thumbnail/publish/status/{publish_id}")
async def thumbnail_publish_status(publish_id: str):
    """Poll the status of a background publish job."""
    if publish_id not in publish_jobs:
        raise HTTPException(status_code=404, detail="Publish job not found")
    return publish_jobs[publish_id]


# @app.get("/api/gallery/clips")
# async def get_gallery_clips(limit: int = 20, offset: int = 0, refresh: bool = False):
#     """
#     Fetch clips from S3 for the gallery with pagination.
#
#     Args:
#         limit: Number of clips to return (default 20, max 100)
#         offset: Starting position for pagination
#         refresh: Force refresh cache
#     """
#     try:
#         # Clamp limit to reasonable values
#         limit = min(max(1, limit), 100)
#
#         # Get clips (uses cache internally)
#         all_clips = list_all_clips(limit=limit + offset, force_refresh=refresh)
#
#         # Apply offset for pagination
#         clips = all_clips[offset:offset + limit]
#
#         return {
#             "clips": clips,
#             "total": len(all_clips),
#             "limit": limit,
#             "offset": offset,
#             "has_more": len(all_clips) > offset + limit
#         }
#     except Exception as e:
#         print(f"❌ Gallery Error: {e}")
#         raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════
# SaaSShorts: AI UGC Video Generator for SaaS Products
# ═══════════════════════════════════════════════════════════════════════

from saasshorts import (
    scrape_website,
    research_saas_online,
    analyze_saas,
    generate_scripts,
    build_custom_script,
    GeminiTemporaryError,
    generate_full_video,
    apply_lipsync_to_saas_job,
    resolve_saas_lipsync_assets,
    generate_actor_images,
    get_elevenlabs_voices,
    DEFAULT_VOICES,
)

# State for SaaSShorts jobs (separate from video processing jobs)
saas_jobs: Dict[str, Dict] = {}


class SaaSAnalyzeRequest(BaseModel):
    url: Optional[str] = None
    description: Optional[str] = None  # Manual product/business description
    topic: Optional[str] = None
    script_mode: str = "ai"  # "ai" or "custom"
    script_format: str = "ugc"  # "ugc" or "storyboard_v3"
    custom_script: Optional[str] = None
    num_scripts: int = 3
    style: str = "ugc"
    language: str = "en"
    actor_gender: str = "female"
    use_platform_keys: bool = False


@app.post("/api/saasshorts/analyze")
async def saasshorts_analyze(
    req: SaaSAnalyzeRequest,
    x_gemini_key: Optional[str] = Header(None, alias="X-Gemini-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """Analyze a URL or manual description and generate video scripts."""
    is_custom = req.script_mode == "custom"
    user = get_user_from_authorization(authorization)
    try:
        gemini_key = resolve_effective_api_key("gemini", user, x_gemini_key, req.use_platform_keys)
    except SubscriptionRequiredError as e:
        raise HTTPException(status_code=402, detail=str(e))
    except PlatformKeyUnavailableError as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not is_custom and not gemini_key:
        raise HTTPException(status_code=400, detail="Missing Gemini API Key")

    if is_custom and not (req.custom_script or "").strip():
        raise HTTPException(status_code=400, detail="Provide a custom script")

    if not is_custom and not req.url and not req.description:
        raise HTTPException(status_code=400, detail="Provide a URL or a product description")

    try:
        loop = asyncio.get_event_loop()

        def run_analysis():
            web_research = None

            if is_custom:
                context = (req.description or req.topic or "Custom video").strip()
                analysis = {
                    "product_name": (req.topic or context).split("\n")[0].strip()[:60] or "Custom Script",
                    "description": req.description or req.topic or "",
                    "value_proposition": req.description or req.topic or "",
                    "target_audience": "custom script audience",
                    "key_features": [req.description] if req.description else [],
                    "pain_points": [],
                    "tone": "custom user-provided narration",
                    "topic": req.topic or "",
                }
                scripts = [
                    build_custom_script(
                        req.custom_script,
                        analysis,
                        req.style,
                        req.language,
                        req.actor_gender,
                        topic=req.topic,
                        script_format=req.script_format,
                    )
                ]
            elif req.url and req.url.strip():
                # URL provided: full scrape + research pipeline
                scraped = scrape_website(req.url)
                web_research = research_saas_online(req.url, gemini_key)
                analysis = analyze_saas(scraped, gemini_key, web_research=web_research)
                if req.topic:
                    analysis["topic"] = req.topic
                scripts = generate_scripts(
                    analysis,
                    gemini_key,
                    req.num_scripts,
                    req.style,
                    req.language,
                    req.actor_gender,
                    topic=req.topic,
                    script_format=req.script_format,
                )
            else:
                # Manual description: build analysis from description
                analysis = {
                    "product_name": req.description.split(",")[0].strip()[:60] if req.description else "Product",
                    "description": req.description,
                    "value_proposition": req.description,
                    "target_audience": "general audience",
                    "key_features": [req.description],
                    "pain_points": [],
                    "tone": "casual and authentic",
                    "topic": req.topic or "",
                }
                scripts = generate_scripts(
                    analysis,
                    gemini_key,
                    req.num_scripts,
                    req.style,
                    req.language,
                    req.actor_gender,
                    topic=req.topic,
                    script_format=req.script_format,
                )
            return {
                "analysis": analysis,
                "scripts": scripts,
                "web_research": web_research,
            }

        result = await loop.run_in_executor(None, run_analysis)
        return result

    except GeminiTemporaryError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SaaSActorRequest(BaseModel):
    actor_description: str
    num_options: int = 3
    product_description: Optional[str] = None
    use_platform_keys: bool = False


ACTOR_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
STORYBOARD_FRAME_EXTENSIONS = ACTOR_IMAGE_EXTENSIONS


def _output_file_url(file_path: str) -> str:
    rel_path = os.path.relpath(file_path, OUTPUT_DIR).replace(os.sep, "/")
    return f"/videos/{rel_path}"


def _write_local_actor_metadata(
    file_path: str,
    url: str,
    description: str = "",
    storage: str = "local",
    owner_user_id: Optional[str] = None,
) -> None:
    meta_path = os.path.splitext(file_path)[0] + ".json"
    meta = {
        "url": url,
        "key": os.path.relpath(file_path, OUTPUT_DIR).replace(os.sep, "/"),
        "description": description,
        "created_at": datetime.datetime.utcnow().isoformat() + "Z",
        "storage": storage,
        "owner_user_id": owner_user_id or "",
    }
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def _read_local_actor_metadata(file_path: str) -> dict:
    meta_path = os.path.splitext(file_path)[0] + ".json"
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    return {
        "url": _output_file_url(file_path),
        "key": os.path.relpath(file_path, OUTPUT_DIR).replace(os.sep, "/"),
        "description": "",
        "created_at": datetime.datetime.utcfromtimestamp(os.path.getmtime(file_path)).isoformat() + "Z",
        "storage": "local",
    }


def list_local_actor_gallery(owner_user_id: Optional[str] = None) -> List[dict]:
    """List actor images saved on local disk, used when S3 is not configured."""
    image_paths = []
    actor_dirs = [os.path.join(OUTPUT_DIR, "actor_uploads")]
    actor_dirs.extend(glob.glob(os.path.join(OUTPUT_DIR, "saas_actors_*")))

    for actor_dir in actor_dirs:
        if not os.path.isdir(actor_dir):
            continue
        for ext in ACTOR_IMAGE_EXTENSIONS:
            image_paths.extend(glob.glob(os.path.join(actor_dir, f"*{ext}")))
            image_paths.extend(glob.glob(os.path.join(actor_dir, f"*{ext.upper()}")))

    images = []
    seen_paths = set()
    for file_path in image_paths:
        abs_path = os.path.abspath(file_path)
        if abs_path in seen_paths:
            continue
        seen_paths.add(abs_path)
        if os.path.getsize(file_path) < 1000:
            continue
        entry = _read_local_actor_metadata(file_path)
        entry.setdefault("url", _output_file_url(file_path))
        entry.setdefault("key", os.path.relpath(file_path, OUTPUT_DIR).replace(os.sep, "/"))
        entry.setdefault("description", "")
        entry.setdefault("storage", "local")
        if owner_user_id and entry.get("owner_user_id") != owner_user_id:
            continue
        images.append(entry)

    images.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return images


@app.post("/api/saasshorts/actor-upload")
async def saasshorts_actor_upload(
    file: UploadFile = File(...),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """Upload a custom actor image and save it to the reusable actor gallery when possible."""
    user = get_user_from_authorization(authorization)
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    try:
        content = await file.read()

        # Validate minimum size
        if len(content) < 1000:
            raise HTTPException(status_code=400, detail="File too small to be a valid image")

        upload_id = uuid.uuid4().hex[:8]
        upload_dir = os.path.join(OUTPUT_DIR, "actor_uploads")
        os.makedirs(upload_dir, exist_ok=True)
        filename = f"custom_{upload_id}.png"
        file_path = os.path.join(upload_dir, filename)

        with open(file_path, "wb") as f:
            f.write(content)

        local_url = f"/videos/actor_uploads/{filename}"
        saved_url = upload_actor_to_s3(file_path, description="Uploaded actor")
        final_url = saved_url or local_url
        storage = "s3" if saved_url else "local"
        _write_local_actor_metadata(
            file_path,
            final_url,
            description="Uploaded actor",
            storage=storage,
            owner_user_id=user.get("id") if user else None,
        )

        return {
            "url": final_url,
            "local_url": local_url,
            "saved": True,
            "storage": storage,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/saasshorts/storyboard-frame-upload")
async def saasshorts_storyboard_frame_upload(
    file: UploadFile = File(...),
    shot_number: int = Form(0),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """Upload a storyboard reference frame for Kling V3 image-to-video shots."""
    user = get_user_from_authorization(authorization)
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    try:
        content = await file.read()
        if len(content) < 1000:
            raise HTTPException(status_code=400, detail="File too small to be a valid image")

        original_ext = os.path.splitext(file.filename or "")[1].lower()
        content_ext = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/webp": ".webp",
        }.get(file.content_type, "")
        ext = original_ext if original_ext in STORYBOARD_FRAME_EXTENSIONS else content_ext or ".png"
        upload_id = uuid.uuid4().hex[:8]
        upload_dir = os.path.join(OUTPUT_DIR, "storyboard_frames")
        os.makedirs(upload_dir, exist_ok=True)
        filename = f"shot_{max(0, int(shot_number or 0)):02d}_{upload_id}{ext}"
        file_path = os.path.join(upload_dir, filename)

        with open(file_path, "wb") as f:
            f.write(content)

        local_url = _output_file_url(file_path)
        meta = {
            "url": local_url,
            "local_url": local_url,
            "image_path": file_path,
            "key": os.path.relpath(file_path, OUTPUT_DIR).replace(os.sep, "/"),
            "shot_number": shot_number,
            "created_at": _utc_now(),
            "storage": "local",
            "owner_user_id": user.get("id") if user else "",
        }
        with open(os.path.splitext(file_path)[0] + ".json", "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        return {
            **meta,
            "image_url": local_url,
            "saved": True,
            "note": "Local frame saved. The generator uploads it to fal.ai before Kling V3 image-to-video.",
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/saasshorts/actor-options")
async def saasshorts_actor_options(
    req: SaaSActorRequest,
    x_fal_key: Optional[str] = Header(None, alias="X-Fal-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """Generate multiple actor image options for the user to choose from."""
    user = get_user_from_authorization(authorization)
    try:
        fal_key = resolve_effective_api_key("fal", user, x_fal_key, getattr(req, "use_platform_keys", False))
    except SubscriptionRequiredError as e:
        raise HTTPException(status_code=402, detail=str(e))
    except PlatformKeyUnavailableError as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not fal_key:
        raise HTTPException(status_code=400, detail="Missing fal.ai API Key")

    try:
        job_id = str(uuid.uuid4())
        out_dir = os.path.join(OUTPUT_DIR, f"saas_actors_{job_id}")
        os.makedirs(out_dir, exist_ok=True)

        loop = asyncio.get_running_loop()
        import functools
        paths = await loop.run_in_executor(
            None,
            functools.partial(
                generate_actor_images,
                req.actor_description, fal_key, out_dir, "actor", req.num_options,
                product_description=req.product_description,
            ),
        )

        # Upload each actor image to public S3 with description
        desc = req.actor_description
        if req.product_description:
            desc += f" (holding {req.product_description})"
        urls = []
        for p in paths:
            s3_url = upload_actor_to_s3(p, description=desc)
            if s3_url:
                urls.append(s3_url)
            else:
                # Fallback to local URL if S3 fails
                local_url = f"/videos/saas_actors_{job_id}/{os.path.basename(p)}"
                _write_local_actor_metadata(
                    p,
                    local_url,
                    description=desc,
                    storage="local",
                    owner_user_id=user.get("id") if user else None,
                )
                urls.append(local_url)

        return {"images": urls}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/saasshorts/gallery")
async def saasshorts_video_gallery(
    limit: int = 50,
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """List all UGC videos from the public gallery."""
    try:
        user = get_user_from_authorization(authorization)
        owner_user_id = user.get("id") if user else None
        loop = asyncio.get_running_loop()
        import functools
        videos = await loop.run_in_executor(
            None,
            functools.partial(list_combined_video_gallery, limit, owner_user_id=owner_user_id),
        )
        return {"videos": videos, "total": len(videos)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SaaSPostRequest(BaseModel):
    job_id: str
    api_key: Optional[str] = None
    user_id: str
    platforms: List[str]
    title: Optional[str] = None
    description: Optional[str] = None
    scheduled_date: Optional[str] = None
    timezone: Optional[str] = "UTC"
    use_platform_keys: bool = False


@app.post("/api/saasshorts/post")
async def saasshorts_post_to_socials(
    req: SaaSPostRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """Post an AI Shorts video to social media via Upload-Post."""
    user = get_user_from_authorization(authorization)
    header_key = req.api_key if req.api_key not in ("__saved__", "__platform__") else None
    try:
        upload_key = resolve_effective_api_key("upload_post", user, header_key, req.use_platform_keys)
    except SubscriptionRequiredError as e:
        raise HTTPException(status_code=402, detail=str(e))
    except PlatformKeyUnavailableError as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not upload_key:
        raise HTTPException(status_code=400, detail="Missing Upload-Post API Key")

    if req.job_id not in saas_jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = saas_jobs[req.job_id]
    if user and job.get("owner_user_id") and job.get("owner_user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Job not found")
    result = job.get("result")
    if not result or not result.get("video_url"):
        raise HTTPException(status_code=400, detail="No video available for this job")

    try:
        # Resolve video file path
        video_url = result["video_url"]  # e.g. /videos/saas_xxx/slug_final.mp4
        rel_path = video_url.replace("/videos/", "")
        file_path = os.path.join(OUTPUT_DIR, rel_path)

        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail=f"Video file not found")

        script = result.get("script", {})
        final_title = req.title or script.get("title", "AI Short")
        final_description = req.description or script.get("caption", "")
        if not final_description:
            final_description = script.get("full_narration", "Check this out!")

        url = "https://api.upload-post.com/api/upload"
        headers = {"Authorization": f"Apikey {upload_key}"}

        data_payload = {
            "user": req.user_id,
            "title": final_title,
            "platform[]": req.platforms,
            "async_upload": "true",
        }

        if req.scheduled_date:
            data_payload["scheduled_date"] = req.scheduled_date
            if req.timezone:
                data_payload["timezone"] = req.timezone

        if "tiktok" in req.platforms:
            data_payload["tiktok_title"] = final_description
        if "instagram" in req.platforms:
            data_payload["instagram_title"] = final_description
            data_payload["media_type"] = "REELS"
        if "youtube" in req.platforms:
            data_payload["youtube_title"] = final_title
            data_payload["youtube_description"] = final_description
            data_payload["privacyStatus"] = "public"

        filename = os.path.basename(file_path)
        with open(file_path, "rb") as f:
            file_content = f.read()

        files = {"video": (filename, file_content, "video/mp4")}

        with httpx.Client(timeout=120.0) as client:
            print(f"📡 [AI Shorts] Sending to Upload-Post: {req.platforms}")
            response = client.post(url, headers=headers, data=data_payload, files=files)

        if response.status_code not in [200, 201, 202]:
            raise HTTPException(status_code=response.status_code, detail=f"Upload-Post Error: {response.text}")

        return response.json()

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ [AI Shorts] Post Exception: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/gallery", response_class=HTMLResponse)
async def gallery_html_page():
    """SEO gallery page with all generated UGC videos."""
    import html as html_mod
    loop = asyncio.get_running_loop()
    videos = await loop.run_in_executor(None, list_combined_video_gallery, 100)

    cards_html = ""
    ld_items = []
    for i, v in enumerate(videos):
        title = html_mod.escape(v.get("title", "Untitled"))
        video_url = v.get("video_url", "")
        actor_url = v.get("actor_url", "")
        video_id = v.get("video_id", "")
        duration = v.get("duration", 0)
        mode = v.get("video_mode", "")
        product = html_mod.escape(v.get("product_name", ""))
        caption = html_mod.escape(v.get("caption", "")[:120])

        if mode == "lowcost":
            mode_badge = '<span style="background:#22c55e;color:#000;padding:2px 8px;border-radius:9999px;font-size:10px;font-weight:700">LOW COST</span>'
        elif mode == "premium":
            mode_badge = '<span style="background:#8b5cf6;color:#fff;padding:2px 8px;border-radius:9999px;font-size:10px;font-weight:700">PREMIUM</span>'
        else:
            mode_badge = '<span style="background:#3b82f6;color:#fff;padding:2px 8px;border-radius:9999px;font-size:10px;font-weight:700">STANDARD</span>'

        cards_html += f'''
        <a href="/video/{video_id}" style="text-decoration:none;color:inherit">
          <div style="background:#18181b;border-radius:16px;overflow:hidden;border:1px solid #27272a;transition:transform 0.2s" onmouseover="this.style.transform='scale(1.02)'" onmouseout="this.style.transform='scale(1)'">
            <div style="position:relative;aspect-ratio:9/16;background:#000">
              <video src="{video_url}" poster="{actor_url}" muted playsinline preload="metadata"
                     onmouseenter="this.play()" onmouseleave="this.pause();this.currentTime=0"
                     style="width:100%;height:100%;object-fit:cover"></video>
              <div style="position:absolute;top:8px;right:8px">{mode_badge}</div>
            </div>
            <div style="padding:12px">
              <h2 style="font-size:14px;font-weight:600;margin:0 0 4px 0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{title}</h2>
              <p style="font-size:11px;color:#71717a;margin:0">{duration:.0f}s · {product}</p>
            </div>
          </div>
        </a>'''

        ld_items.append(f'{{"@type":"ListItem","position":{i+1},"url":"https://openshorts.app/video/{video_id}","name":"{title}"}}')

    ld_json = f'{{"@context":"https://schema.org","@type":"CollectionPage","name":"AI UGC Video Gallery","mainEntity":{{"@type":"ItemList","numberOfItems":{len(videos)},"itemListElement":[{",".join(ld_items)}]}}}}'

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI UGC Video Gallery | OpenShorts</title>
<meta name="description" content="Browse {len(videos)} AI-generated UGC marketing videos. Create viral TikTok and Instagram Reels for your product or business.">
<meta name="robots" content="index, follow">
<meta property="og:title" content="AI UGC Video Gallery | OpenShorts">
<meta property="og:type" content="website">
<meta property="og:description" content="Browse AI-generated UGC marketing videos for products and businesses.">
<script type="application/ld+json">{ld_json}</script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#0a0a0c;color:#e4e4e7;font-family:-apple-system,BlinkMacSystemFont,sans-serif}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:20px;padding:20px;max-width:1400px;margin:0 auto}}
nav{{padding:20px 40px;border-bottom:1px solid #27272a;display:flex;align-items:center;justify-content:space-between}}
h1{{font-size:28px;font-weight:700;padding:40px 20px 0;text-align:center}}
.subtitle{{text-align:center;color:#71717a;font-size:14px;padding:8px 20px 20px}}
.cta{{display:inline-block;background:#8b5cf6;color:#fff;padding:10px 24px;border-radius:12px;text-decoration:none;font-weight:600;font-size:14px}}
</style>
</head>
<body>
<nav><strong style="font-size:18px">OpenShorts</strong><a href="/" class="cta">Create Your Video</a></nav>
<h1>AI-Generated UGC Videos</h1>
<p class="subtitle">{len(videos)} videos generated · Low Cost, Standard & Premium modes</p>
<div class="grid">{cards_html}</div>
<div style="text-align:center;padding:40px"><a href="/" class="cta">Create Your Own UGC Video</a></div>
</body></html>'''


@app.get("/video/{video_id}", response_class=HTMLResponse)
async def video_html_page(video_id: str):
    """SEO individual video page with og:video meta tags."""
    import html as html_mod
    loop = asyncio.get_running_loop()
    videos = await loop.run_in_executor(None, list_combined_video_gallery, 200)
    meta = next((v for v in videos if v.get("video_id") == video_id), None)
    if not meta:
        raise HTTPException(status_code=404, detail="Video not found")

    title = html_mod.escape(meta.get("title", "Untitled"))
    caption = html_mod.escape(meta.get("caption", ""))
    narration = html_mod.escape(meta.get("full_narration", ""))
    video_url = meta.get("video_url", "")
    actor_url = meta.get("actor_url", "")
    duration = meta.get("duration", 0)
    mode = meta.get("video_mode", "")
    product = html_mod.escape(meta.get("product_name", ""))
    product_url = html_mod.escape(meta.get("product_url", ""))
    language = meta.get("language", "en")
    hashtags = " ".join(meta.get("hashtags", []))
    cost = meta.get("cost_estimate", {}).get("total", 0)
    created = meta.get("created_at", "")
    actor_desc = html_mod.escape(meta.get("actor_description", ""))

    ld_json = f'{{"@context":"https://schema.org","@type":"VideoObject","name":"{title}","description":"{caption}","thumbnailUrl":"{actor_url}","contentUrl":"{video_url}","uploadDate":"{created}","duration":"PT{int(duration)}S","width":1080,"height":1920,"inLanguage":"{language}"}}'

    mode_label = "Low Cost" if mode == "lowcost" else ("Premium" if mode == "premium" else "Standard")

    return f'''<!DOCTYPE html>
<html lang="{language}">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} - AI UGC Video | OpenShorts</title>
<meta name="description" content="{caption} {hashtags}">
<meta property="og:type" content="video.other">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{caption}">
<meta property="og:video" content="{video_url}">
<meta property="og:video:type" content="video/mp4">
<meta property="og:video:width" content="1080">
<meta property="og:video:height" content="1920">
<meta property="og:image" content="{actor_url}">
<meta name="twitter:card" content="player">
<meta name="twitter:title" content="{title}">
<meta name="twitter:image" content="{actor_url}">
<script type="application/ld+json">{ld_json}</script>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#0a0a0c;color:#e4e4e7;font-family:-apple-system,BlinkMacSystemFont,sans-serif}}
nav{{padding:20px 40px;border-bottom:1px solid #27272a;display:flex;align-items:center;gap:16px}}
nav a{{color:#a1a1aa;text-decoration:none;font-size:14px}}
.container{{max-width:1000px;margin:0 auto;padding:40px 20px;display:grid;grid-template-columns:1fr 1fr;gap:40px}}
@media(max-width:768px){{.container{{grid-template-columns:1fr}}}}
video{{width:100%;border-radius:16px;background:#000}}
h1{{font-size:22px;font-weight:700;margin-bottom:8px}}
.meta{{color:#71717a;font-size:13px;margin-bottom:20px}}
.section{{margin-bottom:20px}}
.section h2{{font-size:13px;color:#71717a;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px}}
.section p{{font-size:14px;line-height:1.6}}
.badge{{display:inline-block;padding:3px 10px;border-radius:9999px;font-size:11px;font-weight:700}}
.cta{{display:inline-block;background:#8b5cf6;color:#fff;padding:10px 24px;border-radius:12px;text-decoration:none;font-weight:600;font-size:14px;margin-top:20px}}
</style>
</head>
<body>
<nav><strong>OpenShorts</strong><a href="/gallery">Gallery</a><span style="color:#3f3f46">›</span><span style="color:#e4e4e7;font-size:14px">{title}</span></nav>
<div class="container">
<div><video src="{video_url}" poster="{actor_url}" controls autoplay playsinline style="aspect-ratio:9/16;object-fit:cover"></video></div>
<div>
<h1>{title}</h1>
<p class="meta">{duration:.0f}s · {mode_label} · ${cost:.2f} · {product}</p>
<div class="section"><h2>Caption</h2><p>{caption}</p><p style="color:#8b5cf6;margin-top:4px">{hashtags}</p></div>
<div class="section"><h2>Script</h2><p>{narration}</p></div>
<div class="section"><h2>Actor</h2><p>{actor_desc}</p></div>
{f'<div class="section"><h2>Product</h2><p><a href="{product_url}" style="color:#8b5cf6" target="_blank">{product}</a></p></div>' if product_url else ''}
<a href="/gallery">← Back to Gallery</a>
<br><a href="/" class="cta">Create Your Own</a>
</div>
</div>
</body></html>'''


@app.get("/api/saasshorts/actor-gallery")
async def saasshorts_actor_gallery(authorization: Optional[str] = Header(None, alias="Authorization")):
    """List reusable actor images from S3 and local fallback storage."""
    try:
        user = get_user_from_authorization(authorization)
        owner_user_id = user.get("id") if user else None
        loop = asyncio.get_running_loop()
        remote_images = [] if owner_user_id else await loop.run_in_executor(None, list_actor_gallery)
        import functools
        local_images = await loop.run_in_executor(
            None,
            functools.partial(list_local_actor_gallery, owner_user_id=owner_user_id),
        )

        by_url = {}
        for entry in (local_images or []) + (remote_images or []):
            url = entry.get("url")
            if not url:
                continue
            by_url[url] = entry

        images = list(by_url.values())
        images.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return {"images": images}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SaaSGenerateRequest(BaseModel):
    script: dict
    voice_id: Optional[str] = None
    tts_provider: str = "auto"  # "auto", "elevenlabs", or "fal_minimax"
    minimax_voice_id: Optional[str] = None
    actor_gender: Optional[str] = None
    language: Optional[str] = None
    actor_description: Optional[str] = None
    selected_actor_url: Optional[str] = None  # Pre-selected actor image URL
    retry_job_id: Optional[str] = None
    video_mode: str = "standard"  # "lowcost", "standard", or "premium"
    broll_mode: str = "mockup"  # "off", "mockup", or "ai"
    punch_in_cuts: bool = True  # jump-cut talking head with alternating punch-in zoom
    storyboard_generation_mode: str = "per_shot"  # "per_shot", "multi_shot", or "sliced_avatar"
    reusable_head_template_id: Optional[str] = None
    reusable_lipsync_model: str = "sync-3"
    use_platform_keys: bool = False


class SaaSLipSyncRequest(BaseModel):
    job_id: Optional[str] = None
    video_url: Optional[str] = None
    model: str = "sync-3"  # "sync-3", "lipsync-2-pro", or "lipsync-2"
    sync_mode: str = "cut_off"
    use_platform_keys: bool = False


class SaaSHeadTemplateSaveRequest(BaseModel):
    job_id: Optional[str] = None
    video_url: Optional[str] = None
    label: Optional[str] = None


@app.get("/api/saasshorts/head-templates")
async def saasshorts_head_templates(authorization: Optional[str] = Header(None, alias="Authorization")):
    """List reusable talking-head templates saved locally."""
    try:
        user = get_user_from_authorization(authorization)
        owner_user_id = user.get("id") if user else None
        loop = asyncio.get_running_loop()
        import functools
        templates = await loop.run_in_executor(
            None,
            functools.partial(list_local_head_templates, owner_user_id=owner_user_id),
        )
        return {"templates": templates, "total": len(templates)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/saasshorts/head-templates")
async def saasshorts_save_head_template(
    req: SaaSHeadTemplateSaveRequest,
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """Save the cached talking-head video from an AI Shorts job as a reusable template."""
    job_id = req.job_id or _job_id_from_saas_video_url(req.video_url or "")
    if not job_id:
        raise HTTPException(status_code=400, detail="Provide job_id or a local AI Shorts video_url")
    try:
        user = get_user_from_authorization(authorization)
        template = save_local_head_template(
            job_id,
            label=req.label,
            owner_user_id=user.get("id") if user else None,
        )
        return {"template": template}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/saasshorts/generate")
async def saasshorts_generate(
    req: SaaSGenerateRequest,
    x_fal_key: Optional[str] = Header(None, alias="X-Fal-Key"),
    x_elevenlabs_key: Optional[str] = Header(None, alias="X-ElevenLabs-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """Generate a UGC video from a script. Returns a job_id for polling."""
    user = get_user_from_authorization(authorization)
    try:
        fal_key = resolve_effective_api_key("fal", user, x_fal_key, req.use_platform_keys)
        elevenlabs_key = resolve_effective_api_key("elevenlabs", user, x_elevenlabs_key, req.use_platform_keys)
    except SubscriptionRequiredError as e:
        raise HTTPException(status_code=402, detail=str(e))
    except PlatformKeyUnavailableError as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not fal_key:
        raise HTTPException(status_code=400, detail="Missing fal.ai API Key (X-Fal-Key header)")
    if req.tts_provider == "elevenlabs" and not elevenlabs_key:
        raise HTTPException(status_code=400, detail="Missing ElevenLabs API Key (X-ElevenLabs-Key header)")

    # Support retry: reuse output_dir so cached assets (image, voice, head, broll) are kept
    reused = False
    if req.retry_job_id:
        # Check memory first, then disk
        old_dir = os.path.join(OUTPUT_DIR, f"saas_{req.retry_job_id}")
        if req.retry_job_id in saas_jobs:
            old_dir = saas_jobs[req.retry_job_id]["output_dir"]

        if os.path.isdir(old_dir):
            job_id = req.retry_job_id
            job_output_dir = old_dir
            reused = True
            # Clear the 0-byte final video so pipeline re-generates it
            for f in os.listdir(old_dir):
                fp = os.path.join(old_dir, f)
                if f.endswith("_final.mp4") and os.path.getsize(fp) == 0:
                    os.remove(fp)
            saas_jobs[job_id] = {
                "status": "processing",
                "logs": [f"Retrying job {job_id[:8]}... reusing cached assets from disk."],
                "result": None,
                "output_dir": job_output_dir,
                "owner_user_id": user.get("id") if user else None,
            }

    if not reused:
        job_id = str(uuid.uuid4())
        job_output_dir = os.path.join(OUTPUT_DIR, f"saas_{job_id}")
        os.makedirs(job_output_dir, exist_ok=True)
        saas_jobs[job_id] = {
            "status": "processing",
            "logs": ["AI Shorts job started."],
            "result": None,
            "output_dir": job_output_dir,
            "owner_user_id": user.get("id") if user else None,
        }

    # If user selected a pre-generated actor, resolve it to a local path
    selected_actor_path = None
    if req.selected_actor_url:
        if req.selected_actor_url.startswith("http"):
            # Download from S3 public URL to job output dir
            import httpx
            try:
                actor_local = os.path.join(job_output_dir, "selected_actor.png")
                with httpx.Client(timeout=30.0) as client:
                    resp = client.get(req.selected_actor_url)
                    if resp.status_code == 200:
                        with open(actor_local, "wb") as f:
                            f.write(resp.content)
                        selected_actor_path = actor_local
            except Exception:
                pass
        else:
            src = os.path.join(OUTPUT_DIR, req.selected_actor_url.replace("/videos/", ""))
            if os.path.exists(src):
                selected_actor_path = src

    reusable_head = None
    if req.reusable_head_template_id:
        try:
            reusable_head = resolve_head_template_path(
                req.reusable_head_template_id,
                owner_user_id=user.get("id") if user else None,
            )
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))

    resolved_language = req.language or req.script.get("language") or "en"

    config = {
        "fal_key": fal_key,
        "elevenlabs_key": elevenlabs_key,
        "voice_id": req.voice_id or "21m00Tcm4TlvDq8ikWAM",
        "tts_provider": req.tts_provider or "auto",
        "minimax_voice_id": req.minimax_voice_id,
        "actor_gender": req.actor_gender or "female",
        "language": resolved_language,
        "actor_description": req.actor_description,
        "selected_actor_path": selected_actor_path,
        "video_mode": req.video_mode,
        "broll_mode": req.broll_mode or "mockup",
        "punch_in_cuts": req.punch_in_cuts,
        "storyboard_generation_mode": req.storyboard_generation_mode or "per_shot",
        "reusable_head_template_id": reusable_head.get("template_id") if reusable_head else None,
        "reusable_head_path": reusable_head.get("head_path") if reusable_head else None,
        "reusable_head_poster_path": reusable_head.get("poster_path") if reusable_head else None,
        "reusable_lipsync_model": req.reusable_lipsync_model or "sync-3",
    }

    async def run_generation():
        await concurrency_semaphore.acquire()
        try:
            loop = asyncio.get_running_loop()

            def log_msg(msg):
                print(f"[AI Shorts Job {job_id[:8]}] {msg}")
                if job_id in saas_jobs:
                    saas_jobs[job_id]["logs"].append(msg)

            def run():
                return generate_full_video(req.script, config, job_output_dir, log_msg)

            result = await loop.run_in_executor(None, run)

            if job_id in saas_jobs:
                video_filename = result["video_filename"]
                owner_user_id = user.get("id") if user else None
                saas_jobs[job_id]["status"] = "completed"
                saas_jobs[job_id]["result"] = {
                    "video_url": f"/videos/saas_{job_id}/{video_filename}",
                    "video_filename": video_filename,
                    "duration": result.get("duration", 0),
                    "cost_estimate": result.get("cost_estimate", {}),
                    "tts_provider": result.get("tts_provider", req.tts_provider),
                    "broll_mode": result.get("broll_mode", req.broll_mode),
                    "head_source": result.get("head_source", "generated"),
                    "head_template_id": result.get("head_template_id"),
                    "lipsync_model": result.get("lipsync_model"),
                    "quality_status": result.get("quality_status", "unknown"),
                    "quality_warnings": result.get("quality_warnings", []),
                    "talking_head_quality": result.get("talking_head_quality", {}),
                    "language": resolved_language,
                    "script": req.script,
                    "script_format": req.script.get("format") or req.script.get("script_format") or "ugc",
                    "shots": result.get("storyboard_shots") or req.script.get("shots", []),
                    "storyboard_generation_mode": result.get("storyboard_generation_mode"),
                    "business_name": req.script.get("_business_name", ""),
                    "business_description": req.script.get("_business_description", ""),
                    "video_topic": req.script.get("_video_topic", ""),
                }
                saas_jobs[job_id]["logs"].append("Video generation completed!")

                # Upload to public gallery (non-blocking)
                try:
                    gallery_meta = {
                        "title": req.script.get("title", "Untitled"),
                        "hook_text": req.script.get("hook_text", ""),
                        "caption": req.script.get("caption", ""),
                        "hashtags": req.script.get("hashtags", []),
                        "full_narration": req.script.get("full_narration", ""),
                        "actor_description": req.script.get("actor_description", ""),
                        "style": req.script.get("style", "ugc"),
                        "language": resolved_language,
                        "duration": result.get("duration", 0),
                        "video_mode": req.video_mode,
                        "tts_provider": result.get("tts_provider", req.tts_provider),
                        "broll_mode": result.get("broll_mode", req.broll_mode),
                        "head_source": result.get("head_source", "generated"),
                        "head_template_id": result.get("head_template_id"),
                        "lipsync_model": result.get("lipsync_model"),
                        "quality_status": result.get("quality_status", "unknown"),
                        "quality_warnings": result.get("quality_warnings", []),
                        "talking_head_quality": result.get("talking_head_quality", {}),
                        "product_name": req.script.get("_product_name", ""),
                        "product_url": req.script.get("_product_url", ""),
                        "business_name": req.script.get("_business_name", ""),
                        "business_description": req.script.get("_business_description", ""),
                        "video_topic": req.script.get("_video_topic", ""),
                        "segments": req.script.get("segments", []),
                        "script_format": req.script.get("format") or req.script.get("script_format") or "ugc",
                        "shots": result.get("storyboard_shots") or req.script.get("shots", []),
                        "storyboard_generation_mode": result.get("storyboard_generation_mode"),
                        "cost_estimate": result.get("cost_estimate", {}),
                        "owner_user_id": owner_user_id or "",
                    }
                    local_gallery_result = write_local_saas_gallery_entry(
                        job_id,
                        result,
                        gallery_meta,
                        owner_user_id=owner_user_id,
                    )
                    if local_gallery_result:
                        saas_jobs[job_id]["result"]["gallery_video_id"] = local_gallery_result["video_id"]
                        log_msg("Saved to local UGC gallery.")

                    gallery_result = None
                    if not owner_user_id:
                        gallery_result = upload_video_to_gallery(
                            video_path=result["video_path"],
                            actor_image_path=result.get("actor_image", ""),
                            metadata=gallery_meta,
                            video_id=job_id[:8],
                        )
                    if gallery_result:
                        saas_jobs[job_id]["result"]["gallery_video_id"] = gallery_result["video_id"]
                        log_msg("📤 Uploaded to public gallery.")
                    if not gallery_result and local_gallery_result:
                        log_msg("Public S3 gallery not configured; using local UGC gallery.")
                except Exception as gallery_err:
                    log_msg(f"⚠️ Gallery upload skipped: {gallery_err}")

        except Exception as e:
            print(f"[AI Shorts] ❌ Job {job_id} failed: {e}")
            if job_id in saas_jobs:
                saas_jobs[job_id]["status"] = "failed"
                saas_jobs[job_id]["logs"].append(f"Error: {str(e)}")
        finally:
            concurrency_semaphore.release()

    asyncio.create_task(run_generation())

    return {"job_id": job_id, "status": "processing"}


@app.post("/api/saasshorts/lipsync")
async def saasshorts_lipsync(
    req: SaaSLipSyncRequest,
    x_fal_key: Optional[str] = Header(None, alias="X-Fal-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """Run standalone lip-sync on an existing AI Shorts job and update its final video."""
    user = get_user_from_authorization(authorization)
    try:
        fal_key = resolve_effective_api_key("fal", user, x_fal_key, req.use_platform_keys)
    except SubscriptionRequiredError as e:
        raise HTTPException(status_code=402, detail=str(e))
    except PlatformKeyUnavailableError as e:
        raise HTTPException(status_code=500, detail=str(e))
    if not fal_key:
        raise HTTPException(status_code=400, detail="Missing fal.ai API Key (X-Fal-Key header)")

    job_id = req.job_id or _job_id_from_saas_video_url(req.video_url or "")
    if not job_id:
        raise HTTPException(status_code=400, detail="Provide job_id or a local gallery video_url")

    existing_job = saas_jobs.get(job_id)
    if existing_job and existing_job.get("status") == "processing":
        raise HTTPException(status_code=409, detail="This AI Shorts job is already processing")

    job_output_dir = (
        existing_job.get("output_dir")
        if existing_job
        else os.path.join(OUTPUT_DIR, f"saas_{job_id}")
    )
    if not job_output_dir or not os.path.isdir(job_output_dir):
        raise HTTPException(status_code=404, detail="AI Shorts job output not found")

    previous_result = dict(existing_job.get("result") or {}) if existing_job else {}
    previous_meta = _read_local_gallery_meta(job_output_dir) or {}
    if user and previous_meta.get("owner_user_id") and previous_meta.get("owner_user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="AI Shorts job output not found")
    previous_cost = previous_result.get("cost_estimate") or previous_meta.get("cost_estimate") or {}

    saas_jobs[job_id] = {
        "status": "processing",
        "logs": [f"Lip-sync post-process started ({req.model}, {req.sync_mode})."],
        "result": previous_result or None,
        "output_dir": job_output_dir,
        "owner_user_id": user.get("id") if user else previous_meta.get("owner_user_id"),
    }

    async def run_lipsync():
        await concurrency_semaphore.acquire()
        try:
            loop = asyncio.get_running_loop()

            def log_msg(msg):
                print(f"[AI Shorts LipSync {job_id[:8]}] {msg}")
                if job_id in saas_jobs:
                    saas_jobs[job_id]["logs"].append(msg)

            def run():
                return apply_lipsync_to_saas_job(
                    job_output_dir,
                    fal_key,
                    model=req.model,
                    sync_mode=req.sync_mode,
                    log=log_msg,
                )

            result = await loop.run_in_executor(None, run)

            lip_cost = result.get("lipsync_cost_estimate")

            meta = dict(previous_meta)
            completed_at = _utc_now()
            script = previous_result.get("script") or {
                "title": meta.get("title", ""),
                "caption": meta.get("caption", ""),
                "hashtags": meta.get("hashtags", []),
                "full_narration": meta.get("full_narration", ""),
            }

            video_filename = result["video_filename"]
            new_video_url = f"/videos/saas_{job_id}/{video_filename}"
            versions = _build_saas_video_versions(
                meta,
                new_video_url,
                req.model,
                req.sync_mode,
                lip_cost,
                created_at=completed_at,
            )
            current_version_id = versions[-1].get("id", "") if versions else ""
            cost = _add_saas_lipsync_cost(previous_cost, req.model, lip_cost, current_version_id)
            completed_result = {
                **previous_result,
                "video_url": new_video_url,
                "video_filename": video_filename,
                "duration": result.get("duration", previous_result.get("duration", 0)),
                "cost_estimate": cost,
                "script": script,
                "lipsync_model": req.model,
                "lipsync_sync_mode": req.sync_mode,
                "versions": versions,
            }

            if job_id in saas_jobs:
                saas_jobs[job_id]["status"] = "completed"
                saas_jobs[job_id]["result"] = completed_result
                saas_jobs[job_id]["logs"].append("Lip-sync post-process completed!")

            gallery_meta = {
                **meta,
                "title": script.get("title") or meta.get("title", ""),
                "hook_text": meta.get("hook_text", ""),
                "caption": script.get("caption") or meta.get("caption", ""),
                "hashtags": script.get("hashtags") or meta.get("hashtags", []),
                "full_narration": script.get("full_narration") or meta.get("full_narration", ""),
                "actor_description": meta.get("actor_description", ""),
                "style": meta.get("style", "ugc"),
                "language": meta.get("language", "ru"),
                "duration": completed_result["duration"],
                "video_mode": meta.get("video_mode", previous_result.get("video_mode", "")),
                "tts_provider": meta.get("tts_provider", previous_result.get("tts_provider", "")),
                "broll_mode": meta.get("broll_mode", previous_result.get("broll_mode", "")),
                "segments": meta.get("segments", []),
                "cost_estimate": cost,
                "lipsync_model": req.model,
                "lipsync_sync_mode": req.sync_mode,
                "versions": versions,
            }
            write_local_saas_gallery_entry(
                job_id,
                result,
                gallery_meta,
                owner_user_id=user.get("id") if user else previous_meta.get("owner_user_id"),
            )

        except Exception as e:
            print(f"[AI Shorts] Lip-sync job {job_id} failed: {e}")
            if job_id in saas_jobs:
                saas_jobs[job_id]["status"] = "failed"
                saas_jobs[job_id]["logs"].append(f"Error: {str(e)}")
        finally:
            concurrency_semaphore.release()

    asyncio.create_task(run_lipsync())

    return {"job_id": job_id, "status": "processing"}


@app.get("/api/saasshorts/status/{job_id}")
async def saasshorts_status(
    job_id: str,
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """Poll AI Shorts job status."""
    if job_id not in saas_jobs:
        raise HTTPException(status_code=404, detail="AI Shorts job not found")

    job = saas_jobs[job_id]
    user = get_user_from_authorization(authorization)
    if user and job.get("owner_user_id") and job.get("owner_user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="AI Shorts job not found")
    return {
        "status": job["status"],
        "logs": job["logs"],
        "result": job.get("result"),
    }


@app.get("/api/saasshorts/voices")
async def saasshorts_voices(
    x_elevenlabs_key: Optional[str] = Header(None, alias="X-ElevenLabs-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
    use_platform_keys: bool = False,
):
    """List available ElevenLabs voices."""
    user = get_user_from_authorization(authorization)
    try:
        elevenlabs_key = resolve_effective_api_key("elevenlabs", user, x_elevenlabs_key, use_platform_keys)
    except (SubscriptionRequiredError, PlatformKeyUnavailableError):
        elevenlabs_key = None

    if elevenlabs_key:
        try:
            loop = asyncio.get_event_loop()
            voices = await loop.run_in_executor(
                None, get_elevenlabs_voices, elevenlabs_key
            )
            if voices:
                return {"voices": voices, "source": "elevenlabs"}
        except Exception:
            pass

    # Fallback to default voices
    return {
        "voices": [
            {"voice_id": vid, "name": name, "category": "default"}
            for name, vid in DEFAULT_VOICES.items()
        ],
        "source": "defaults",
    }
