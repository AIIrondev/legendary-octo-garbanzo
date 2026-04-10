#!/usr/bin/env python3
"""
Backup-Invoices.py

Exports all invoice records stored in ausleihungen.InvoiceData to dedicated
archive files (JSONL + CSV + metadata).

Usage:
    python Backup-Invoices.py \
        --uri mongodb://localhost:27017/ \
        --db Inventarsystem \
        --out /var/backups/invoice-archive/invoices-2026-04-06_12-00-00
"""

import argparse
import csv
import json
import os
import sys
from datetime import datetime

from bson import ObjectId
from pymongo import MongoClient


def parse_args():
    parser = argparse.ArgumentParser(
        description="Export invoice records from ausleihungen to JSONL and CSV."
    )
    parser.add_argument("--uri", "-u", required=True, help="MongoDB URI")
    parser.add_argument("--db", "-d", required=True, help="MongoDB database name")
    parser.add_argument(
        "--out",
        "-o",
        required=True,
        help=(
            "Output file base path without extension, e.g. "
            "/var/backups/invoice-archive/invoices-2026-04-06_12-00-00"
        ),
    )
    return parser.parse_args()


def to_jsonable(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_jsonable(v) for v in value]
    return value


def flatten_dict(data, parent_key="", sep="."):
    items = {}
    for key, value in data.items():
        new_key = f"{parent_key}{sep}{key}" if parent_key else str(key)
        if isinstance(value, dict):
            items.update(flatten_dict(value, new_key, sep=sep))
        elif isinstance(value, list):
            items[new_key] = json.dumps(value, ensure_ascii=False)
        else:
            items[new_key] = value
    return items


def normalize_invoice_record(doc):
    invoice_data = doc.get("InvoiceData") or {}
    record = {
        "borrow_id": str(doc.get("_id", "")),
        "borrow_status": doc.get("Status", ""),
        "borrow_user": doc.get("User", ""),
        "borrow_item": doc.get("Item", ""),
        "borrow_start": doc.get("Start"),
        "borrow_end": doc.get("End"),
        "invoice_number": invoice_data.get("invoice_number", ""),
        "invoice_amount": invoice_data.get("amount"),
        "invoice_amount_text": invoice_data.get("amount_text", ""),
        "invoice_damage_reason": invoice_data.get("damage_reason", ""),
        "invoice_created_at": invoice_data.get("created_at"),
        "invoice_created_by": invoice_data.get("created_by", ""),
        "invoice_borrower": invoice_data.get("borrower", ""),
        "invoice_item_id": invoice_data.get("item_id", ""),
        "invoice_item_name": invoice_data.get("item_name", ""),
        "invoice_item_code": invoice_data.get("item_code", ""),
        "invoice_mark_destroyed": invoice_data.get("mark_destroyed", False),
        "invoice_status_before": invoice_data.get("status_before_invoice", ""),
        "invoice_raw": invoice_data,
    }
    return to_jsonable(record)


def write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as handle:
        for row in records:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path, records):
    if not records:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["info"])
            writer.writerow(["no invoice records found"])
        return

    flat_records = [flatten_dict(row) for row in records]
    fieldnames = sorted({key for row in flat_records for key in row.keys()})

    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in flat_records:
            writer.writerow(row)


def write_metadata(path, db_name, out_base, count):
    payload = {
        "db": db_name,
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "record_count": count,
        "files": {
            "jsonl": out_base + ".jsonl",
            "csv": out_base + ".csv",
        },
        "schema_note": "Source is ausleihungen.InvoiceData",
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def main():
    args = parse_args()
    out_base = args.out
    out_dir = os.path.dirname(out_base) or "."

    try:
        os.makedirs(out_dir, exist_ok=True)
    except Exception as exc:
        print(f"Error: cannot create output directory {out_dir}: {exc}")
        return 1

    client = None
    try:
        client = MongoClient(args.uri)
        client.server_info()
        db = client[args.db]
        ausleihungen = db["ausleihungen"]

        cursor = ausleihungen.find({"InvoiceData": {"$exists": True, "$ne": None}})
        records = [normalize_invoice_record(doc) for doc in cursor]

        jsonl_path = out_base + ".jsonl"
        csv_path = out_base + ".csv"
        meta_path = out_base + ".meta.json"

        write_jsonl(jsonl_path, records)
        write_csv(csv_path, records)
        write_metadata(meta_path, args.db, out_base, len(records))

        print(f"Invoice backup complete: {len(records)} records")
        print(f"JSONL: {jsonl_path}")
        print(f"CSV:   {csv_path}")
        print(f"META:  {meta_path}")
        return 0
    except Exception as exc:
        print(f"Error: {exc}")
        return 1
    finally:
        if client:
            client.close()


if __name__ == "__main__":
    sys.exit(main())
