"""Authenticated encrypted SQLite snapshots and non-overwriting recovery.

Snapshots contain the canonical database only, not credentials or feed caches.
Recovery always writes a NEW staging file; it never swaps an active database.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
from datetime import datetime, timezone
from contextlib import closing

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"LOTBOOKBACKUP\x00\x01"
LEGACY_MAGIC = b"CLEARBACKUP\x00\x01"
MAX_DATABASE_BYTES = 64 * 1024 * 1024


def _archive_magic(archive: bytes) -> bytes | None:
    for magic in (MAGIC, LEGACY_MAGIC):
        if archive.startswith(magic):
            return magic
    return None


def _key(passphrase: str, salt: bytes) -> bytes:
    if not 12 <= len(passphrase) <= 128:
        raise ValueError("Use a backup passphrase between 12 and 128 characters.")
    return Scrypt(salt=salt, length=32, n=32768, r=8, p=1).derive(passphrase.encode("utf-8"))


def _check_database(path: Path) -> None:
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as database:
        if database.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise ValueError("Database integrity verification failed.")
        if database.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ValueError("Database foreign-key verification failed.")


def encrypted_snapshot(database_path: Path, passphrase: str) -> bytes:
    salt, nonce = os.urandom(16), os.urandom(12)
    key = _key(passphrase, salt)
    if not database_path.is_file():
        raise ValueError("The canonical database is unavailable.")
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="lotbook-backup-") as directory:
        snapshot = Path(directory) / "snapshot.db"
        def progress(_status: int, _remaining: int, total: int) -> None:
            if time.monotonic() - started > 15:
                raise ValueError("Backup timed out; retry when database activity is lower.")
            if total * page_size > MAX_DATABASE_BYTES:
                raise ValueError("Database exceeds this release's 64 MiB backup limit.")
        with closing(sqlite3.connect(database_path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)) as source:
            page_size = source.execute("PRAGMA page_size").fetchone()[0]
            with closing(sqlite3.connect(snapshot)) as target:
                source.backup(target, pages=256, progress=progress, sleep=0.05)
        if snapshot.stat().st_size > MAX_DATABASE_BYTES:
            raise ValueError("Database exceeds this release's 64 MiB backup limit.")
        _check_database(snapshot)
        data = snapshot.read_bytes()
    manifest = json.dumps({"format": 1, "created_at": datetime.now(timezone.utc).isoformat(), "scope": "canonical-sqlite-database", "sha256": hashlib.sha256(data).hexdigest()}, separators=(",", ":")).encode("utf-8")
    plaintext = len(manifest).to_bytes(4, "big") + manifest + data
    return MAGIC + salt + nonce + AESGCM(key).encrypt(nonce, plaintext, MAGIC)


def restore_to_new_file(archive: bytes, passphrase: str, destination: Path) -> dict:
    """Verify before atomically creating a recovery candidate, never overwrite."""
    if destination.exists():
        raise ValueError("Recovery destination already exists; choose a new staging file.")
    magic = _archive_magic(archive)
    if magic is None or not len(magic) + 44 < len(archive) <= MAX_DATABASE_BYTES + 16384:
        raise ValueError("Invalid or oversized Lotbook backup.")
    offset = len(magic)
    salt, nonce = archive[offset:offset + 16], archive[offset + 16:offset + 28]
    try:
        plaintext = AESGCM(_key(passphrase, salt)).decrypt(nonce, archive[offset + 28:], magic)
    except InvalidTag as failure:
        raise ValueError("Backup authentication failed: incorrect passphrase or damaged archive.") from failure
    manifest_size = int.from_bytes(plaintext[:4], "big")
    if not 0 < manifest_size <= 16384:
        raise ValueError("Invalid backup manifest.")
    manifest = json.loads(plaintext[4:4 + manifest_size])
    data = plaintext[4 + manifest_size:]
    if not isinstance(manifest, dict) or manifest.get("format") != 1 or manifest.get("scope") != "canonical-sqlite-database" or not data.startswith(b"SQLite format 3\x00") or hashlib.sha256(data).hexdigest() != manifest.get("sha256"):
        raise ValueError("Backup database digest or format is invalid.")
    destination = destination.resolve()
    descriptor, temporary_name = tempfile.mkstemp(prefix=".lotbook-recovery-", suffix=".db", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        _check_database(temporary)
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return manifest
