"""
Tamper-evident audit logging helpers.

The audit chain stores each entry with a hash of the previous entry.
Any mutation in history breaks the chain verification.
"""

import datetime
import hashlib
import json
import random
import time

from pymongo.errors import DuplicateKeyError


def _stable_json(value):
    """Serialize dictionaries in a stable way for deterministic hashing."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _entry_hash(prev_hash, payload):
    """Build the chained entry hash from previous hash + canonical payload."""
    base = f"{prev_hash}|{_stable_json(payload)}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def append_audit_event(db, event_type, actor, payload, request_ip=None, source="web", max_retries=5):
    """
    Append an audit event to a tamper-evident chain.

    Args:
        db: MongoDB database handle.
        event_type (str): Event category.
        actor (str): User/system who performed the action.
        payload (dict): Event details.
        request_ip (str, optional): Request origin.
        source (str): Source subsystem.

    Returns:
        dict: Inserted audit entry.
    """
    logs = db["audit_log"]
    attempts = 0

    while attempts <= max_retries:
        previous = logs.find_one(sort=[("chain_index", -1)])
        prev_hash = previous.get("entry_hash", "") if previous else ""
        chain_index = int(previous.get("chain_index", 0)) + 1 if previous else 1

        timestamp = datetime.datetime.utcnow()
        entry_payload = {
            "event_type": event_type,
            "actor": actor or "system",
            "source": source,
            "ip": request_ip or "",
            "payload": payload or {},
            "timestamp": timestamp.isoformat() + "Z",
        }

        entry_hash = _entry_hash(prev_hash, entry_payload)

        entry = {
            **entry_payload,
            "created_at": timestamp,
            "prev_hash": prev_hash,
            "entry_hash": entry_hash,
            "chain_index": chain_index,
        }

        try:
            logs.insert_one(entry)
            return entry
        except DuplicateKeyError:
            attempts += 1
            if attempts > max_retries:
                raise
            # Exponential backoff with jitter to avoid retry storms.
            delay = min(0.25, (0.005 * (2 ** attempts)) + random.random() * 0.01)
            time.sleep(delay)


def ensure_audit_indexes(db):
    """Create indexes required for fast and safe audit operations."""
    logs = db["audit_log"]
    logs.create_index("chain_index", unique=True, name="audit_chain_index_unique")
    logs.create_index("created_at", name="audit_created_at_idx")
    logs.create_index("event_type", name="audit_event_type_idx")


def verify_audit_chain(db):
    """Verify hash chain integrity across all stored audit entries."""
    logs = db["audit_log"]
    entries = list(logs.find({}, {"_id": 1, "event_type": 1, "actor": 1, "source": 1, "ip": 1, "payload": 1, "timestamp": 1, "prev_hash": 1, "entry_hash": 1, "chain_index": 1}).sort("chain_index", 1))

    previous_hash = ""
    previous_index = 0
    mismatches = []

    for entry in entries:
        chain_index = int(entry.get("chain_index", 0))
        prev_hash = entry.get("prev_hash", "")
        entry_hash = entry.get("entry_hash", "")

        payload = {
            "event_type": entry.get("event_type", ""),
            "actor": entry.get("actor", ""),
            "source": entry.get("source", ""),
            "ip": entry.get("ip", ""),
            "payload": entry.get("payload", {}),
            "timestamp": entry.get("timestamp", ""),
        }

        expected_hash = _entry_hash(previous_hash, payload)

        if chain_index != previous_index + 1:
            mismatches.append({
                "chain_index": chain_index,
                "error": "chain_index_gap",
                "expected": previous_index + 1,
                "found": chain_index,
            })

        if prev_hash != previous_hash:
            mismatches.append({
                "chain_index": chain_index,
                "error": "prev_hash_mismatch",
                "expected": previous_hash,
                "found": prev_hash,
            })

        if entry_hash != expected_hash:
            mismatches.append({
                "chain_index": chain_index,
                "error": "entry_hash_mismatch",
                "expected": expected_hash,
                "found": entry_hash,
            })

        previous_hash = entry_hash
        previous_index = chain_index

    return {
        "ok": len(mismatches) == 0,
        "count": len(entries),
        "last_chain_index": previous_index,
        "last_hash": previous_hash,
        "mismatches": mismatches,
    }
