# Database Package (`backend/db/`)

This package contains the PostgreSQL database layer for ScrumPilot, built with SQLAlchemy 2.0 and Alembic.

## What's in This Package

- **`connection.py`** - Database connection management and session factory
- **`models.py`** - SQLAlchemy ORM models (8 tables, 6 enums)
- **`crud.py`** - Low-level CRUD operations for all tables
- **`test_storage.py`** - Test suite for storage layer
- **`__init__.py`** - Package exports

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run migrations
python -m alembic upgrade head

# Test the setup
python -m backend.db.test_storage
```

## Usage

Use the high-level `StorageService` API from `backend/tools/storage.py`:

```python
from backend.tools.storage import storage

# Create a meeting
meeting_id = storage.create_meeting(
    meeting_type="scrum",
    meeting_date=date.today(),
    title="Daily Standup",
)

# Start processing
run_id = storage.start_processing_run(
    meeting_id=meeting_id,
    run_type="scrum_actions",
)

# Save artifacts and complete
storage.save_artifact(meeting_id, "transcript", text_content=transcript)
storage.complete_processing_run(run_id)
```

## Full Documentation

For complete setup instructions, troubleshooting, SQL queries, and architecture details, see:

**[docs/database/README.md](../../docs/database/README.md)**

For file inventory and ownership boundaries, see:

**[docs/database/FILE_INVENTORY.md](../../docs/database/FILE_INVENTORY.md)**
