"""Helpers for targeted PII encryption and encrypted archival of deleted media files."""

import base64
import hashlib
import json
import os
import uuid
import zipfile
from datetime import datetime

from cryptography.fernet import Fernet, InvalidToken

import settings as cfg

_ENC_PREFIX = "enc::"


def _resolve_fernet_key():
    """Resolve the Fernet key from env/config or derive a stable fallback."""
    configured_key = cfg.DATA_ENCRYPTION_KEY
    if configured_key:
        try:
            # Validate the supplied key format.
            Fernet(configured_key.encode("utf-8"))
            return configured_key.encode("utf-8")
        except Exception:
            pass

    # Fallback for compatibility: derive stable key from SECRET_KEY.
    digest = hashlib.sha256(cfg.SECRET_KEY.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _fernet():
    return Fernet(_resolve_fernet_key())


def encrypt_text(value):
    """Encrypt a text value. Keeps empty values unchanged."""
    if value is None:
        return None
    text = str(value)
    if text == "" or text.startswith(_ENC_PREFIX):
        return text
    token = _fernet().encrypt(text.encode("utf-8")).decode("utf-8")
    return f"{_ENC_PREFIX}{token}"


def decrypt_text(value):
    """Decrypt an encrypted text value. Returns original value if not encrypted."""
    if value is None:
        return None
    text = str(value)
    if not text.startswith(_ENC_PREFIX):
        return text

    token = text[len(_ENC_PREFIX):]
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError, TypeError):
        # Keep data readable even if key rotation or malformed data occurred.
        return text


def encrypt_document_fields(document, fields):
    """Encrypt selected fields of a document in-place and return it."""
    for field in fields:
        if field in document:
            document[field] = encrypt_text(document.get(field))
    return document


def decrypt_document_fields(document, fields):
    """Decrypt selected fields of a document in-place and return it."""
    for field in fields:
        if field in document:
            document[field] = decrypt_text(document.get(field))
    return document


def _candidate_media_paths(filename):
    """Return all possible filesystem paths for a stored media filename."""
    name_part, _ = os.path.splitext(filename)
    return [
        (os.path.join(cfg.UPLOAD_FOLDER, filename), "originals"),
        (os.path.join(cfg.UPLOAD_FOLDER, f"{name_part}.webp"), "originals"),
        (os.path.join(cfg.UPLOAD_FOLDER, f"{name_part}.jpg"), "originals"),
        (os.path.join(cfg.THUMBNAIL_FOLDER, f"{name_part}_thumb.webp"), "thumbnails"),
        (os.path.join(cfg.THUMBNAIL_FOLDER, f"{name_part}_thumb.jpg"), "thumbnails"),
        (os.path.join(cfg.PREVIEW_FOLDER, f"{name_part}_preview.webp"), "previews"),
        (os.path.join(cfg.PREVIEW_FOLDER, f"{name_part}_preview.jpg"), "previews"),
    ]


def encrypt_soft_deleted_media_pack(item_docs, *, actor="system"):
    """
    Archive media files referenced by item docs, encrypt the archive, and delete originals.

    Uses ZIP_STORED (no compression) to keep CPU usage low.
    """
    files_to_archive = []
    seen_paths = set()

    for item in item_docs:
        item_id = str(item.get("_id", "unknown"))
        for image_name in item.get("Images", []) or []:
            for abs_path, bucket in _candidate_media_paths(str(image_name)):
                if abs_path in seen_paths:
                    continue
                if not os.path.isfile(abs_path):
                    continue
                seen_paths.add(abs_path)
                files_to_archive.append((item_id, str(image_name), abs_path, bucket))

    if not files_to_archive:
        return {
            "archive_created": False,
            "archived_files": 0,
            "deleted_files": 0,
            "archive_path": None,
        }

    os.makedirs(cfg.DELETED_ARCHIVE_FOLDER, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    archive_id = f"softdelete-{timestamp}-{uuid.uuid4().hex[:8]}"
    zip_path = os.path.join(cfg.DELETED_ARCHIVE_FOLDER, f"{archive_id}.zip")
    encrypted_path = os.path.join(cfg.DELETED_ARCHIVE_FOLDER, f"{archive_id}.zip.enc")

    manifest = {
        "archive_id": archive_id,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "actor": actor,
        "files": [],
    }

    with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_STORED) as zf:
        for idx, (item_id, original_name, abs_path, bucket) in enumerate(files_to_archive, start=1):
            safe_name = os.path.basename(abs_path)
            arcname = f"{bucket}/{item_id}/{idx:04d}-{safe_name}"
            zf.write(abs_path, arcname)
            manifest["files"].append(
                {
                    "item_id": item_id,
                    "source_name": original_name,
                    "stored_as": arcname,
                    "size_bytes": os.path.getsize(abs_path),
                }
            )

        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    with open(zip_path, "rb") as source_file:
        encrypted_payload = _fernet().encrypt(source_file.read())

    with open(encrypted_path, "wb") as encrypted_file:
        encrypted_file.write(encrypted_payload)

    deleted_files = 0
    for _, _, abs_path, _ in files_to_archive:
        try:
            os.remove(abs_path)
            deleted_files += 1
        except OSError:
            pass

    try:
        os.remove(zip_path)
    except OSError:
        pass

    return {
        "archive_created": True,
        "archived_files": len(files_to_archive),
        "deleted_files": deleted_files,
        "archive_path": encrypted_path,
    }
