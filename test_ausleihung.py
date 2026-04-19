"""
Test Suite for Ausleihung (Borrowing) System
Tests all core functionality of the borrowing/lending module

Run with: pytest test_ausleihung.py -v
"""

import pytest
import datetime
from bson.objectid import ObjectId
import sys
import os

# Add Web directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'Web'))

import ausleihung
import settings as cfg
from settings import MongoClient


@pytest.fixture(scope='session')
def db_client():
    """Create MongoDB connection for tests"""
    client = MongoClient(cfg.MONGODB_HOST, cfg.MONGODB_PORT)
    yield client
    client.close()


@pytest.fixture(scope='session')
def test_db(db_client):
    """Get test database"""
    return db_client[cfg.MONGODB_DB]


@pytest.fixture(autouse=True)
def cleanup_test_data(test_db):
    """Clean up test data before and after each test"""
    yield
    # Clean up after test
    test_db['ausleihungen'].delete_many({})


@pytest.fixture
def sample_ausleihung_data():
    """Fixture with sample borrowing data"""
    now = datetime.datetime.now()
    return {
        'item_id': str(ObjectId()),
        'user': 'test_user',
        'start_date': now,
        'end_date': now + datetime.timedelta(days=1),
        'notes': 'Test borrowing',
        'period': None
    }


# ============================================================================
# Status Determination Tests
# ============================================================================

class TestGetCurrentStatus:
    """Test status determination based on dates"""
    
    def test_planned_status_future_date(self):
        """Test that future borrowing is marked as 'planned'"""
        future_time = datetime.datetime.now() + datetime.timedelta(days=1)
        ausleihung_doc = {
            'Status': 'planned',
            'Start': future_time,
            'End': future_time + datetime.timedelta(hours=1)
        }
        status = ausleihung.get_current_status(ausleihung_doc)
        assert status == 'planned'
    
    def test_active_status_during_borrowing(self):
        """Test that current borrowing is marked as 'active'"""
        now = datetime.datetime.now()
        start = now - datetime.timedelta(hours=1)
        end = now + datetime.timedelta(hours=1)
        ausleihung_doc = {
            'Status': 'active',
            'Start': start,
            'End': end
        }
        status = ausleihung.get_current_status(ausleihung_doc)
        assert status == 'active'
    
    def test_completed_status_after_end_time(self):
        """Test that past borrowing is marked as 'completed'"""
        now = datetime.datetime.now()
        start = now - datetime.timedelta(days=2)
        end = now - datetime.timedelta(hours=1)
        ausleihung_doc = {
            'Status': 'active',
            'Start': start,
            'End': end
        }
        status = ausleihung.get_current_status(ausleihung_doc)
        assert status == 'completed'
    
    def test_cancelled_status_remains_cancelled(self):
        """Test that cancelled status is never changed"""
        future_time = datetime.datetime.now() + datetime.timedelta(days=1)
        ausleihung_doc = {
            'Status': 'cancelled',
            'Start': future_time,
            'End': future_time + datetime.timedelta(hours=1)
        }
        status = ausleihung.get_current_status(ausleihung_doc)
        assert status == 'cancelled'
    
    def test_active_with_no_end_time(self):
        """Test that borrowing without end time stays active if started"""
        now = datetime.datetime.now()
        start = now - datetime.timedelta(hours=1)
        ausleihung_doc = {
            'Status': 'active',
            'Start': start,
            'End': None
        }
        status = ausleihung.get_current_status(ausleihung_doc)
        assert status == 'active'


# ============================================================================
# Create and Update Tests
# ============================================================================

class TestCreateAusleihung:
    """Test creating new borrowings"""
    
    def test_create_active_ausleihung(self, test_db):
        """Test creating an immediately active borrowing"""
        item_id = str(ObjectId())
        user = 'test_user'
        start = datetime.datetime.now()
        end = start + datetime.timedelta(hours=2)
        
        result = ausleihung.add_ausleihung(
            item_id=item_id,
            user=user,
            start_date=start,
            end_date=end,
            notes='Test active',
            status='active'
        )
        
        assert result is not None
        
        # Verify in database
        ausleihung_col = test_db['ausleihungen']
        stored = ausleihung_col.find_one({'_id': result})
        assert stored is not None
        assert stored['Item'] == item_id  # Correct field name
        assert stored['User'] == user
        assert stored['Status'] == 'active'
    
    def test_create_planned_ausleihung(self, test_db):
        """Test creating a future/planned borrowing"""
        item_id = str(ObjectId())
        user = 'test_user'
        future_start = datetime.datetime.now() + datetime.timedelta(days=1)
        future_end = future_start + datetime.timedelta(hours=2)
        
        result = ausleihung.add_ausleihung(
            item_id=item_id,
            user=user,
            start_date=future_start,
            end_date=future_end,
            notes='Test planned',
            status='planned'
        )
        
        assert result is not None
        
        ausleihung_col = test_db['ausleihungen']
        stored = ausleihung_col.find_one({'_id': result})
        assert stored['Status'] == 'planned'
        # Check approximately equal (within 1 second for datetime precision)
        assert abs((stored['Start'] - future_start).total_seconds()) < 1


class TestUpdateAusleihung:
    """Test updating existing borrowings"""
    
    def test_update_ausleihung_dates(self, test_db, sample_ausleihung_data):
        """Test updating borrowing dates"""
        # Create initial borrowing
        ausleihung_id = ausleihung.add_ausleihung(**sample_ausleihung_data)
        assert ausleihung_id is not None
        
        # Update dates
        new_start = datetime.datetime.now() + datetime.timedelta(days=2)
        new_end = new_start + datetime.timedelta(hours=1)
        
        ausleihung.update_ausleihung(
            id=ausleihung_id,
            start=new_start,
            end=new_end
        )
        
        # Verify update (within 1 second tolerance for datetime precision)
        stored = test_db['ausleihungen'].find_one({'_id': ausleihung_id})
        assert abs((stored['Start'] - new_start).total_seconds()) < 1
        assert abs((stored['End'] - new_end).total_seconds()) < 1
    
    def test_update_ausleihung_status(self, test_db, sample_ausleihung_data):
        """Test updating borrowing status"""
        ausleihung_id = ausleihung.add_ausleihung(**sample_ausleihung_data)
        
        ausleihung.update_ausleihung(id=ausleihung_id, status='completed')
        
        stored = test_db['ausleihungen'].find_one({'_id': ausleihung_id})
        assert stored['Status'] == 'completed'
    
    def test_update_ausleihung_notes(self, test_db, sample_ausleihung_data):
        """Test updating borrowing notes"""
        ausleihung_id = ausleihung.add_ausleihung(**sample_ausleihung_data)
        new_notes = 'Updated notes'
        
        ausleihung.update_ausleihung(id=ausleihung_id, notes=new_notes)
        
        stored = test_db['ausleihungen'].find_one({'_id': ausleihung_id})
        assert stored['Notes'] == new_notes


# ============================================================================
# Complete and Cancel Tests
# ============================================================================

class TestCompleteAusleihung:
    """Test completing borrowings"""
    
    def test_complete_ausleihung(self, test_db, sample_ausleihung_data):
        """Test marking a borrowing as completed"""
        ausleihung_id = ausleihung.add_ausleihung(**sample_ausleihung_data)
        
        end_time = datetime.datetime.now()
        ausleihung.complete_ausleihung(ausleihung_id, end_time=end_time)
        
        stored = test_db['ausleihungen'].find_one({'_id': ausleihung_id})
        assert stored['Status'] == 'completed'
        assert stored['End'] == end_time or stored['End'] is not None


class TestCancelAusleihung:
    """Test canceling borrowings"""
    
    def test_cancel_ausleihung(self, test_db, sample_ausleihung_data):
        """Test canceling a borrowing"""
        ausleihung_id = ausleihung.add_ausleihung(**sample_ausleihung_data)
        
        ausleihung.cancel_ausleihung(ausleihung_id)
        
        stored = test_db['ausleihungen'].find_one({'_id': ausleihung_id})
        assert stored['Status'] == 'cancelled'


# ============================================================================
# Query Tests
# ============================================================================

class TestGetAusleihung:
    """Test retrieving borrowings"""
    
    def test_get_ausleihung_by_id(self, test_db, sample_ausleihung_data):
        """Test fetching a borrowing by ID"""
        ausleihung_id = ausleihung.add_ausleihung(**sample_ausleihung_data)
        
        retrieved = ausleihung.get_ausleihung(ausleihung_id)
        assert retrieved is not None
        assert retrieved['_id'] == ausleihung_id
        assert retrieved['User'] == sample_ausleihung_data['user']
    
    def test_get_ausleihung_by_user(self, test_db):
        """Test retrieving all borrowings for a user"""
        user = 'test_user_xyz'
        item1 = str(ObjectId())
        item2 = str(ObjectId())
        now = datetime.datetime.now()
        
        # Create multiple borrowings for same user
        ausleihung.add_ausleihung(
            item_id=item1,
            user=user,
            start_date=now,
            end_date=now + datetime.timedelta(hours=1),
            status='active'
        )
        ausleihung.add_ausleihung(
            item_id=item2,
            user=user,
            start_date=now + datetime.timedelta(days=1),
            end_date=now + datetime.timedelta(days=1, hours=1),
            status='planned'
        )
        
        # Retrieve all for user
        borrowings = ausleihung.get_ausleihung_by_user(user)
        assert len(borrowings) >= 2
        assert all(b['User'] == user for b in borrowings)
    
    def test_get_ausleihungen_by_status(self, test_db):
        """Test retrieving borrowings by status"""
        item_id = str(ObjectId())
        user = 'test_user'
        now = datetime.datetime.now()
        
        # Create active
        active_id = ausleihung.add_ausleihung(
            item_id=item_id,
            user=user,
            start_date=now - datetime.timedelta(hours=1),
            end_date=now + datetime.timedelta(hours=1),
            status='active'
        )
        
        # Get active borrowings
        active_borrowings = ausleihung.get_active_ausleihungen()
        assert any(b['_id'] == active_id for b in active_borrowings)


# ============================================================================
# Conflict Detection Tests
# ============================================================================

class TestConflictDetection:
    """Test detecting overlapping/conflicting borrowings"""
    
    def test_no_conflict_different_items(self, test_db):
        """Test that different items don't conflict"""
        item1 = str(ObjectId())
        item2 = str(ObjectId())
        now = datetime.datetime.now()
        start = now
        end = now + datetime.timedelta(hours=1)
        
        # Create first borrowing
        ausleihung.add_ausleihung(
            item_id=item1,
            user='user1',
            start_date=start,
            end_date=end,
            status='active'
        )
        
        # Check conflict on different item (should be no conflict)
        conflict = ausleihung.check_ausleihung_conflict(
            item_id=item2,
            start_date=start,
            end_date=end
        )
        assert conflict is False
    
    def test_conflict_same_item_overlapping(self, test_db):
        """Test that overlapping borrowings on same item are detected"""
        item_id = str(ObjectId())
        now = datetime.datetime.now()
        
        # Create first borrowing
        ausleihung.add_ausleihung(
            item_id=item_id,
            user='user1',
            start_date=now,
            end_date=now + datetime.timedelta(hours=2),
            status='active'
        )
        
        # Try to create overlapping borrowing
        conflict = ausleihung.check_ausleihung_conflict(
            item_id=item_id,
            start_date=now + datetime.timedelta(minutes=30),
            end_date=now + datetime.timedelta(hours=3)
        )
        assert conflict is True or conflict == item_id  # Depending on implementation
    
    def test_no_conflict_different_times(self, test_db):
        """Test that non-overlapping borrowings don't conflict"""
        item_id = str(ObjectId())
        now = datetime.datetime.now()
        
        # Create first borrowing
        ausleihung.add_ausleihung(
            item_id=item_id,
            user='user1',
            start_date=now,
            end_date=now + datetime.timedelta(hours=1),
            status='active'
        )
        
        # Check borrowing after first ends (should be no conflict)
        conflict = ausleihung.check_ausleihung_conflict(
            item_id=item_id,
            start_date=now + datetime.timedelta(hours=2),
            end_date=now + datetime.timedelta(hours=3)
        )
        assert conflict is False or conflict is None


# ============================================================================
# Period-based Borrowing Tests
# ============================================================================

class TestPeriodBookings:
    """Test period-based borrowings (school periods)"""
    
    def test_create_period_booking(self, test_db):
        """Test creating a borrowing for a specific school period"""
        item_id = str(ObjectId())
        user = 'test_user'
        today = datetime.datetime.now().date()
        
        result = ausleihung.add_ausleihung(
            item_id=item_id,
            user=user,
            start_date=datetime.datetime.combine(today, datetime.time(8, 0)),
            end_date=datetime.datetime.combine(today, datetime.time(9, 0)),
            period=1,  # Assuming period 1 is first period
            status='active'
        )
        
        assert result is not None
        stored = test_db['ausleihungen'].find_one({'_id': result})
        assert stored.get('Period') == 1


# ============================================================================
# Remove Tests
# ============================================================================

class TestRemoveAusleihung:
    """Test removing/deleting borrowings"""
    
    def test_remove_ausleihung(self, test_db, sample_ausleihung_data):
        """Test deleting a borrowing record (soft delete)"""
        ausleihung_id = ausleihung.add_ausleihung(**sample_ausleihung_data)
        stored_before = test_db['ausleihungen'].find_one({'_id': ausleihung_id})
        assert stored_before is not None
        
        # Remove (soft delete - adds DeletedAt timestamp)
        ausleihung.remove_ausleihung(ausleihung_id)
        
        # Verify it's marked as deleted (soft delete)
        stored_after = test_db['ausleihungen'].find_one({'_id': ausleihung_id})
        assert stored_after is not None  # Still exists
        assert 'DeletedAt' in stored_after or stored_after.get('Status') == 'deleted'


# ============================================================================
# Integration Tests
# ============================================================================

class TestAusleihungLifecycle:
    """Test complete borrowing lifecycle"""
    
    def test_full_lifecycle_active_to_complete(self, test_db):
        """Test a complete borrowing lifecycle: active → complete"""
        item_id = str(ObjectId())
        user = 'test_user'
        now = datetime.datetime.now()
        
        # 1. Create active borrowing
        ausleihung_id = ausleihung.add_ausleihung(
            item_id=item_id,
            user=user,
            start_date=now - datetime.timedelta(hours=1),
            end_date=now + datetime.timedelta(hours=1),
            status='active'
        )
        
        stored = test_db['ausleihungen'].find_one({'_id': ausleihung_id})
        status = ausleihung.get_current_status(stored)
        assert status == 'active'
        
        # 2. Complete the borrowing
        ausleihung.complete_ausleihung(ausleihung_id)
        
        stored = test_db['ausleihungen'].find_one({'_id': ausleihung_id})
        status = ausleihung.get_current_status(stored)
        assert status == 'completed'
    
    def test_full_lifecycle_planned_to_active_to_complete(self, test_db):
        """Test complete lifecycle: planned → active → complete"""
        item_id = str(ObjectId())
        user = 'test_user'
        now = datetime.datetime.now()
        future = now + datetime.timedelta(hours=1)
        
        # 1. Create planned borrowing
        ausleihung_id = ausleihung.add_ausleihung(
            item_id=item_id,
            user=user,
            start_date=future,
            end_date=future + datetime.timedelta(hours=1),
            status='planned'
        )
        
        stored = test_db['ausleihungen'].find_one({'_id': ausleihung_id})
        assert ausleihung.get_current_status(stored) == 'planned'
        
        # 2. Update to active (simulate time passing or manual activation)
        ausleihung.update_ausleihung(id=ausleihung_id, status='active')
        stored = test_db['ausleihungen'].find_one({'_id': ausleihung_id})
        assert stored['Status'] == 'active'
        
        # 3. Complete
        ausleihung.complete_ausleihung(ausleihung_id)
        stored = test_db['ausleihungen'].find_one({'_id': ausleihung_id})
        assert ausleihung.get_current_status(stored) == 'completed'
    
    def test_cancel_planned_borrowing(self, test_db):
        """Test canceling a planned borrowing"""
        item_id = str(ObjectId())
        user = 'test_user'
        future = datetime.datetime.now() + datetime.timedelta(days=1)
        
        # Create planned
        ausleihung_id = ausleihung.add_ausleihung(
            item_id=item_id,
            user=user,
            start_date=future,
            end_date=future + datetime.timedelta(hours=1),
            status='planned'
        )
        
        # Cancel
        ausleihung.cancel_ausleihung(ausleihung_id)
        
        stored = test_db['ausleihungen'].find_one({'_id': ausleihung_id})
        assert stored['Status'] == 'cancelled'


# ============================================================================
# Edge Cases
# ============================================================================

class TestEdgeCases:
    """Test edge cases and boundary conditions"""
    
    def test_borrowing_with_same_start_and_end(self, test_db):
        """Test borrowing where start equals end"""
        item_id = str(ObjectId())
        user = 'test_user'
        now = datetime.datetime.now()
        
        result = ausleihung.add_ausleihung(
            item_id=item_id,
            user=user,
            start_date=now,
            end_date=now,  # Same time
            status='active'
        )
        
        assert result is not None
    
    def test_borrowing_without_end_date(self, test_db):
        """Test creating borrowing without end date"""
        item_id = str(ObjectId())
        user = 'test_user'
        now = datetime.datetime.now()
        
        result = ausleihung.add_ausleihung(
            item_id=item_id,
            user=user,
            start_date=now,
            end_date=None,
            status='active'
        )
        
        assert result is not None
        stored = test_db['ausleihungen'].find_one({'_id': result})
        # End field should not exist or be None if not provided
        assert 'End' not in stored or stored.get('End') is None
    
    def test_get_nonexistent_borrowing(self, test_db):
        """Test retrieving a nonexistent borrowing"""
        fake_id = ObjectId()
        result = ausleihung.get_ausleihung(fake_id)
        assert result is None or result == {} or result == []


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
