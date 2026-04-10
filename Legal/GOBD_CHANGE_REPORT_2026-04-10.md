# GoBD Hardening Change Report (2026-04-10)

## Scope
This change set implements core hardening measures for GoBD-oriented operation:

1. Soft-delete instead of hard-delete for inventory and borrowing records.
2. Tamper-evident audit log chain for critical accounting/inventory events.
3. Invoice immutability model with correction entries instead of overwrite.

## Implemented Changes

### 1) Tamper-evident audit chain

- New module: `Web/audit_log.py`
- Audit entries are chained by hash (`prev_hash` -> `entry_hash`) with monotonic `chain_index`.
- Canonical JSON serialization is used to make hashing deterministic.

Current fields per audit event:
- `event_type`
- `actor`
- `source`
- `ip`
- `payload`
- `timestamp`
- `created_at`
- `prev_hash`
- `entry_hash`
- `chain_index`

Integrated event writes in:
- Item soft-delete flow
- Invoice creation
- Invoice paid marking
- Invoice finalize+repair
- Invoice correction entry creation

### 1b) Audit operational controls (phase 2)

- Added index management in `Web/audit_log.py`:
   - Unique index on `chain_index`
   - Additional indexes on `created_at` and `event_type`
- Added chain verification function in `Web/audit_log.py`.
- Added CLI verification tool: `Web/verify_audit_chain.py`.
- Added admin verification endpoint:
   - `GET /admin/audit/verify`
   - Returns chain integrity result (`200` if valid, `409` on mismatch).
- Added lazy index provisioning helper invoked in admin borrowing views.

### 2) Soft-delete conversion

#### Inventory items

- Deletion endpoint now marks records logically deleted:
  - `Deleted: true`
  - `DeletedAt`
  - `DeletedBy`
  - `LastUpdated`
  - `Verfuegbar: false`
- Item-linked borrow records are also logically deleted (`Status: deleted`) instead of physically removed.
- Image files are no longer physically deleted in this flow.

#### Borrow records

- `remove_ausleihung` changed to set `Status: deleted` + timestamps.
- Retrieval helpers now exclude deleted records by default.

#### Item reads

- Item helper queries now exclude `Deleted: true` records.
- Grouped item lookups and appointment queries also exclude deleted records.
- Code uniqueness checks ignore deleted records, allowing controlled code reuse.

### 3) Invoice immutability and correction flow

- Invoice creation now blocks overwrite if an invoice already exists for the borrow record.
- New lock marker on invoice creation/update path: `InvoiceLocked: true`.
- New correction endpoint:
  - `POST /admin/borrowings/<borrow_id>/invoice/correction`
  - Appends entries to `InvoiceCorrections`
  - Does not mutate existing `InvoiceData` body
  - Requires correction reason
  - Supports optional amount delta

### 3b) UI integration for correction flow (phase 2)

- Added correction action forms in:
   - `Web/templates/admin_borrowings.html`
   - `Web/templates/library_borrowings_admin.html`
- Added correction count display (`invoice_corrections_count`) in both admin tables.

## Detailed File-Level Review

### `Web/audit_log.py`

- Introduces chain-based audit persistence.
- Uses last chain entry to calculate next `chain_index` and hash.
- Adds explicit index provisioning and full chain verification routine.
- Tradeoff: application-level sequencing is improved by unique index, but concurrent peak writes may still require retry logic around duplicate key conflicts.

### `Web/verify_audit_chain.py`

- New CLI operational tool for manual/cron verification.
- Returns non-zero exit code on chain mismatch.

### `Web/app.py`

- Added `_append_audit_event(...)` helper and integrated it at critical event boundaries.
- Inventory API routes now hide soft-deleted items.
- `delete_item` changed from destructive deletion to soft-delete semantics.
- Invoice route now rejects overwrite and requires correction route for changes.
- Added correction route with immutable invoice core.
- Added admin audit verification route and lazy audit index initialization helper.

Behavioral impact:
- Deleted items no longer disappear from DB; they are hidden from normal views.
- Existing UI actions for delete continue to work, but now preserve evidence.
- Invoice re-creation attempts now return warning and redirect.

### `Web/items.py`

- Introduced `_active_record_query(...)` and applied it across item retrieval APIs.
- Converted `remove_item` to soft-delete update.
- Updated maintenance reset (`unstuck_item`) to status updates instead of `delete_many`.

Behavioral impact:
- Item-level DB history is preserved.
- Legacy scripts relying on hard delete semantics may need adaptation.

### `Web/ausleihung.py`

- Converted `remove_ausleihung` to soft-delete by status.
- Default retrieval paths now exclude deleted records.

Behavioral impact:
- Borrowing history remains in DB for traceability.

## Validation Performed

- Static diagnostics reported no errors in modified files:
  - `Web/app.py`
  - `Web/items.py`
  - `Web/ausleihung.py`
  - `Web/audit_log.py`

- Additional phase-2 checks:
   - `python3 -m py_compile Web/app.py Web/audit_log.py Web/verify_audit_chain.py`
   - No syntax errors
   - Template diagnostics:
      - `Web/templates/admin_borrowings.html` no errors
      - `Web/templates/library_borrowings_admin.html` no errors

## Residual Risks / Open Points

1. Concurrency hardening for audit chain:
   - Current chain append may produce collisions under parallel writes.
   - Recommendation: transaction or optimistic retry with unique index on `chain_index`.

2. Broader query coverage:
   - Some direct Mongo queries outside helper paths may still need explicit `Deleted != true` filters.

3. Formal GoBD process requirements beyond code:
   - Verfahrensdokumentation must be updated.
   - WORM/immutable storage for exported archives should be enforced externally.
   - Operational controls (RBAC review, periodic reconciliation, restore drills) should be documented.

## Recommended Next Steps

1. Add retry strategy for audit write conflicts:
   - Retry `append_audit_event` on duplicate `chain_index` key errors.

2. Add admin UI page for chain status and recent audit events:
   - Human-readable inspection view on top of `/admin/audit/verify`.

3. Add policy enforcement tests:
   - Ensure invoice overwrite is blocked.
   - Ensure soft-deleted records are hidden in APIs.
   - Ensure deletion endpoints never call physical delete operators.

4. Infrastructure-level immutability:
   - Push periodic audit snapshots and invoice archives to immutable/WORM storage.
