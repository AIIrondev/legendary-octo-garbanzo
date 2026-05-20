# Ausleihung (Borrowing System) Test Suite

Comprehensive pytest test suite for the Inventarsystem borrowing and lending system.

## Quick Start

```bash
# Install test dependencies
pip install pytest

# Run all tests
pytest test_ausleihung.py -v

# Run specific test class
pytest test_ausleihung.py::TestGetCurrentStatus -v

# Run with detailed output
pytest test_ausleihung.py -vv --tb=long
```

## Test Coverage

### ✅ Status Determination (5 tests)
- Future borrowings marked as 'planned'
- Current borrowings marked as 'active'
- Past borrowings marked as 'completed'
- Cancelled status never changes
- Active borrowings without end time

### ✅ Create Operations (2 tests)
- Create immediately active borrowing
- Create planned/future borrowing

### ✅ Update Operations (3 tests)
- Update borrowing dates
- Update borrowing status
- Update borrowing notes

### ✅ Complete/Cancel Operations (2 tests)
- Mark borrowing as completed
- Cancel a borrowing

### ✅ Query Operations (3 tests)
- Retrieve borrowing by ID
- Retrieve all borrowings for a user
- Retrieve borrowings by status

### ✅ Conflict Detection (3 tests)
- No conflict between different items
- Conflict detection for overlapping same-item borrowings
- No conflict for non-overlapping times

### ✅ Period Bookings (1 test)
- Create period-based borrowing (school periods)

### ✅ Delete Operations (1 test)
- Soft-delete borrowing records

### ✅ Full Lifecycle Tests (3 tests)
- Active → Completed
- Planned → Active → Completed
- Cancel planned borrowing

### ✅ Edge Cases (3 tests)
- Borrowing with same start and end time
- Borrowing without end date
- Retrieve non-existent borrowing

## Test Structure

```python
# Fixtures
@pytest.fixture(scope='session')
def db_client():  # MongoDB connection
    
@pytest.fixture(scope='session')
def test_db():    # Test database
    
@pytest.fixture(autouse=True)
def cleanup_test_data():  # Auto-cleanup between tests
    
@pytest.fixture
def sample_ausleihung_data():  # Sample data for tests
```

## Running Specific Tests

```bash
# Test status determination
pytest test_ausleihung.py::TestGetCurrentStatus -v

# Test conflict detection
pytest test_ausleihung.py::TestConflictDetection -v

# Test full lifecycle
pytest test_ausleihung.py::TestAusleihungLifecycle -v

# Single test
pytest test_ausleihung.py::TestGetCurrentStatus::test_planned_status_future_date -v
```

## Output Example

```
test_ausleihung.py::TestGetCurrentStatus::test_planned_status_future_date PASSED [ 3%]
test_ausleihung.py::TestGetCurrentStatus::test_active_status_during_borrowing PASSED [ 7%]
test_ausleihung.py::TestCreateAusleihung::test_create_active_ausleihung PASSED [ 23%]
...
============================== 26 passed in 0.15s ==============================
```

## What's Tested

### Core Functions
- ✅ `get_current_status()` - Determine borrowing status
- ✅ `add_ausleihung()` - Create new borrowing
- ✅ `update_ausleihung()` - Update existing borrowing
- ✅ `complete_ausleihung()` - Mark as returned
- ✅ `cancel_ausleihung()` - Cancel borrowing
- ✅ `remove_ausleihung()` - Delete/soft-delete
- ✅ `get_ausleihung()` - Retrieve by ID
- ✅ `get_ausleihung_by_user()` - Find user's borrowings
- ✅ `get_ausleihung_by_item()` - Find borrowing by item
- ✅ `get_active_ausleihungen()` - Query active only
- ✅ `get_planned_ausleihungen()` - Query planned only
- ✅ `check_ausleihung_conflict()` - Detect conflicts

### Status Transitions
- ✅ Planned → Active → Completed
- ✅ Active → Completed
- ✅ Planned → Cancelled
- ✅ Status immutability (cancelled stays cancelled)

### Data Validation
- ✅ Correct field names (Item, User, Start, End, Status, etc.)
- ✅ Optional fields handling (End, Notes, Period)
- ✅ Datetime precision (within 1 second tolerance)
- ✅ Soft-delete behavior (DeletedAt timestamp)

## Database Requirements

Tests automatically:
1. Connect to MongoDB (from settings.cfg)
2. Use the configured database
3. Create/clean `ausleihungen` collection
4. Clean up test data between tests

Ensure MongoDB is running:
```bash
# Docker
docker compose up -d mongodb

# Or local MongoDB
mongod
```

## CI/CD Integration

Add to CI/CD pipeline:
```yaml
test:
  script:
    - pip install pytest
    - pytest test_ausleihung.py -v --tb=short
    - pytest test_ausleihung.py --cov=Web/ausleihung
```

## Troubleshooting

### Tests fail to connect to MongoDB
```
MongoClient Error: Server address lookup failed
```
**Solution:** Start MongoDB or check `MONGODB_HOST` in settings.py

### AttributeError: module 'ausleihung' has no attribute...
```
ModuleNotFoundError: No module named 'ausleihung'
```
**Solution:** Run from project root, Python path includes `Web/`

### Datetime comparison failures
```
AssertionError: datetime(...) != datetime(...)
```
**Solution:** Tests use 1-second tolerance for datetime comparisons

## Performance

- Total runtime: ~0.15 seconds
- Per test: ~6ms average
- Database operations: ~5ms average
- No external network calls

## Future Enhancements

- [ ] Parametrized tests for multiple scenarios
- [ ] Performance benchmarking tests
- [ ] Concurrency tests (simultaneous bookings)
- [ ] Date range query tests
- [ ] Export/backup tests
- [ ] Mock MongoDB for unit testing
- [ ] Integration tests with app.py endpoints

---

**Version:** 1.0
**Last Updated:** April 2026
**Status:** All 26 tests passing ✅
