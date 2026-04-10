'''
   Copyright 2025-2026 AIIrondev

   Licensed under the Inventarsystem EULA (Endbenutzer-Lizenzvertrag).
   See Legal/LICENSE for the full license text.
   Unauthorized commercial use, SaaS hosting, or removal of branding is prohibited.
   For commercial licensing inquiries: https://github.com/AIIrondev
'''
"""
Backup-DB.py

Usage:
    python Backup-DB.py \
        --uri mongodb://user:pass@host:port/ \
        --db my_database \
        --out /path/to/backup_folder
"""
import os
import csv
import sys
import argparse
from datetime import datetime
from pymongo import MongoClient


def parse_args():
    parser = argparse.ArgumentParser(
        description="Backup a MongoDB database to CSV files (one per collection)."
    )
    parser.add_argument(
        "--uri", "-u",
        required=True,
        help="MongoDB URI, e.g. mongodb://user:pass@host:port/"
    )
    parser.add_argument(
        "--db", "-d",
        required=True,
        help="Name of the database to back up"
    )
    parser.add_argument(
        "--out", "-o",
        default=f"mongo_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        help="Output directory (will be created if it doesn't exist)"
    )
    return parser.parse_args()


def flatten_dict(d, parent_key="", sep="."):
    """
    Flatten nested dicts into a single level, concatenating keys with sep.
    Lists are left as-is (converted to string later).
    """
    items = {}
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.update(flatten_dict(v, new_key, sep=sep))
        else:
            items[new_key] = v
    return items


def export_collection(db, coll_name, out_dir):
    coll = db[coll_name]
    cursor = coll.find()
    docs = list(cursor)
    if not docs:
        print(f"[{coll_name}] No documents found, skipping.")
        return

    # Flatten and collect all keys
    all_keys = set()
    flat_docs = []
    for doc in docs:
        # Convert ObjectId and other non-serializable types
        doc = {k: str(v) for k, v in doc.items()}
        flat = flatten_dict(doc)
        flat_docs.append(flat)
        all_keys.update(flat.keys())

    out_file = os.path.join(out_dir, f"{coll_name}.csv")
    with open(out_file, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=sorted(all_keys))
        writer.writeheader()
        for flat in flat_docs:
            writer.writerow(flat)

    print(f"[{coll_name}] Exported {len(flat_docs)} docs → {out_file}")


def main():
    args = parse_args()

    # Create output directory
    try:
        os.makedirs(args.out, exist_ok=True)
        print(f"Backing up database '{args.db}' → '{args.out}'")
    except PermissionError:
        print(f"Error: Permission denied when creating directory {args.out}")
        print("Try running with sudo or to a different output directory")
        return 1

    # Verify write permissions
    test_file = os.path.join(args.out, ".write_test")
    try:
        with open(test_file, 'w') as f:
            f.write("test")
        os.remove(test_file)
    except (IOError, PermissionError) as e:
        print(f"Error: Cannot write to output directory {args.out}")
        print(f"Reason: {str(e)}")
        print("Try running with sudo or to a different output directory")
        return 1

    try:
        # Connect to MongoDB
        client = MongoClient(args.uri)
        # Test connection
        client.server_info()
        db = client[args.db]

        # Export each collection
        for coll_name in db.list_collection_names():
            export_collection(db, coll_name, args.out)

        print("Backup complete.")
        return 0
    except Exception as e:
        print(f"Error: {str(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())