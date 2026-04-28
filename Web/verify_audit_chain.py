#!/usr/bin/env python3
"""CLI utility to verify the tamper-evident audit chain."""

import json
import sys

import settings as cfg
from settings import MongoClient
import audit_log as al


def main():
    client = None
    try:
        client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
        db = client[cfg.MONGODB_DB]
        al.ensure_audit_indexes(db)
        result = al.verify_audit_chain(db)
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0 if result.get("ok") else 2
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 1
    finally:
        if client:
            client.close()


if __name__ == "__main__":
    sys.exit(main())
