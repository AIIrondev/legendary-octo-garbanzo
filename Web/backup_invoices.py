#!/usr/bin/env python3
import argparse
import csv
import datetime
import json
import os
import sys

try:
    from bson import json_util
except ImportError:
    json_util = None

try:
    from pymongo import MongoClient
except ImportError:
    print('Error: pymongo is required to run invoice backups.', file=sys.stderr)
    sys.exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.normpath(os.path.join(SCRIPT_DIR, '..', 'config.json'))

DEFAULT_ARCHIVE_DIR = '/var/backups/invoice-archive'
DEFAULT_KEEP_DAYS = 3650


def load_config():
    config = {}
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception:
        pass
    return config


def resolve_mongo_settings(args):
    config = load_config()
    mongodb = config.get('mongodb', {}) if isinstance(config, dict) else {}

    host = os.getenv('INVENTAR_MONGODB_HOST') or args.mongo_host or mongodb.get('host') or 'localhost'
    port = os.getenv('INVENTAR_MONGODB_PORT') or args.mongo_port or mongodb.get('port') or 27017
    db_name = os.getenv('INVENTAR_MONGODB_DB') or args.db_name or mongodb.get('db') or 'Inventarsystem'
    uri = args.mongo_uri

    if isinstance(port, str) and port.strip().isdigit():
        port = int(port.strip())

    return host, int(port), db_name, uri


def format_csv_value(value):
    if value is None:
        return ''
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def normalize_doc_for_json(doc):
    if json_util is not None:
        return json.loads(json_util.dumps(doc, default=json_util.default))
    return doc


def build_csv_row(document):
    invoice_data = document.get('InvoiceData') or {}
    corrections = document.get('InvoiceCorrections') or []
    return {
        'invoice_number': invoice_data.get('invoice_number', ''),
        'borrow_id': str(document.get('_id', '')),
        'status_before_invoice': invoice_data.get('status_before_invoice', '') or document.get('Status', ''),
        'borrower': document.get('User', '') or invoice_data.get('borrower', ''),
        'item': document.get('Item', ''),
        'amount': invoice_data.get('amount', ''),
        'currency': invoice_data.get('currency', 'EUR'),
        'created_at': format_csv_value(invoice_data.get('created_at')),
        'paid': invoice_data.get('paid', False),
        'paid_at': format_csv_value(invoice_data.get('paid_at')),
        'invoice_reason': invoice_data.get('damage_reason', ''),
        'corrections_count': len(corrections) if isinstance(corrections, list) else 0,
        'corrections': json.dumps(corrections, ensure_ascii=False) if corrections else '',
    }


def write_jsonl(path, cursor):
    with open(path, 'w', encoding='utf-8') as f:
        for document in cursor:
            if json_util is not None:
                line = json_util.dumps(document, default=json_util.default)
            else:
                line = json.dumps(document, default=str, ensure_ascii=False)
            f.write(line + '\n')


def write_csv(path, cursor):
    fieldnames = [
        'invoice_number',
        'borrow_id',
        'status_before_invoice',
        'borrower',
        'item',
        'amount',
        'currency',
        'created_at',
        'paid',
        'paid_at',
        'invoice_reason',
        'corrections_count',
        'corrections',
    ]
    with open(path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for document in cursor:
            writer.writerow({k: format_csv_value(v) for k, v in build_csv_row(document).items()})


def write_meta(path, metadata):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)


def parse_args():
    parser = argparse.ArgumentParser(description='Create a legal invoice archive backup from the MongoDB invoice records.')
    parser.add_argument('--archive-dir', required=True, help='Directory to write archive files into')
    parser.add_argument('--base-name', default=None, help='Base filename prefix for archive files')
    parser.add_argument('--mongo-host', default=None, help='MongoDB host override')
    parser.add_argument('--mongo-port', type=int, default=None, help='MongoDB port override')
    parser.add_argument('--db-name', default=None, help='MongoDB database name override')
    parser.add_argument('--mongo-uri', default=None, help='MongoDB connection URI override')
    return parser.parse_args()


def main():
    args = parse_args()
    archive_dir = os.path.abspath(args.archive_dir)
    os.makedirs(archive_dir, exist_ok=True)

    base_name = args.base_name or f'invoices-{datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}'
    jsonl_path = os.path.join(archive_dir, f'{base_name}.jsonl')
    csv_path = os.path.join(archive_dir, f'{base_name}.csv')
    meta_path = os.path.join(archive_dir, f'{base_name}.meta.json')

    host, port, db_name, uri = resolve_mongo_settings(args)
    if uri:
        client = MongoClient(uri)
    else:
        client = MongoClient(host, port)

    try:
        db = client[db_name]
        collection = db['ausleihungen']
        query = {'InvoiceData.invoice_number': {'$exists': True, '$ne': ''}}
        projection = {'InvoiceData': 1, 'InvoiceCorrections': 1, 'User': 1, 'Item': 1, 'Status': 1}
        cursor = collection.find(query, projection)

        docs = list(cursor)
        if not docs:
            print('No invoice records found. No archive written.')
            return 0

        write_jsonl(jsonl_path, docs)
        write_csv(csv_path, docs)

        metadata = {
            'generated_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'invoice_count': len(docs),
            'archive_files': [os.path.basename(jsonl_path), os.path.basename(csv_path), os.path.basename(meta_path)],
            'mongo_db': db_name,
            'mongo_host': host,
            'mongo_port': port,
            'query': query,
        }
        write_meta(meta_path, metadata)

        print(f'Wrote invoice archive: {jsonl_path}')
        print(f'Wrote invoice archive CSV: {csv_path}')
        print(f'Wrote metadata: {meta_path}')
        return 0
    finally:
        client.close()

if __name__ == '__main__':
    sys.exit(main())
