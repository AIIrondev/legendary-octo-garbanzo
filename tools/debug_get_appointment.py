#!/usr/bin/env python3
"""
Small debug script to check tenant-aware lookup for an appointment id.
Usage: ./tools/debug_get_appointment.py <appointment_id> [tenant]
"""
import sys
from bson.objectid import ObjectId
from Web.modules.database.settings import MongoClient, MONGODB_HOST, MONGODB_PORT, MONGODB_DB
import Web.modules.database.termine as termine


def main():
    if len(sys.argv) < 2:
        print("Usage: debug_get_appointment.py <appointment_id> [tenant]")
        sys.exit(2)
    aid = sys.argv[1]
    tenant = sys.argv[2] if len(sys.argv) > 2 else None

    if tenant:
        print(f"Looking up appointment {aid} for tenant {tenant}")
    else:
        print(f"Looking up appointment {aid} for default tenant")

    try:
        # Use the module helper directly
        item = termine.get_item(aid)
        if item:
            print('Found with termini.get_item:')
            print(item)
        else:
            print('termin.get_item returned None')

        # Try explicit MongoClient + tenant DB resolution
        client = MongoClient(MONGODB_HOST, MONGODB_PORT)
        try:
            from Web.tenant import TenantContext, get_tenant_db
            if tenant:
                ctx = TenantContext()
                ctx.tenant_id = tenant
                db = ctx.get_database(client)
            else:
                db = get_tenant_db(client) if 'get_tenant_db' in dir() else client[MONGODB_DB]

            doc = db['appointments'].find_one({'_id': ObjectId(aid)})
            print('Direct DB find_one returned:')
            print(doc)
        finally:
            client.close()
    except Exception as e:
        print('Error during debug lookup:', e)


if __name__ == '__main__':
    main()
