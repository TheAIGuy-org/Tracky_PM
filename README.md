# Tracky PM

A project management system with Smart Merge capabilities for Excel imports.

## Architecture Overview

### Tech Stack
| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Frontend** | React (Vite) + ShadcnUI | Dashboard with "Impact Table" |
| **Backend** | FastAPI (Python) | Parsing MSP files, date calculations, AI (Phase 2) |
| **Database** | Supabase (Postgres) | Data, Auth, Real-time updates |
| **Auth** | Supabase Auth + Magic Links | Dashboard login + email update buttons |

## Core Philosophy

**"The Excel File updates the Plan, but the System preserves the Truth."**

### Smart Merge Algorithm

When importing Excel files:

1. **Case A: New Task (INSERT)**
   - Task doesn't exist in DB → Insert new row
   - `baseline = excel_date`, `current = excel_date`, `status = "Not Started"`

2. **Case B: Existing Task (UPDATE)**
   - Task exists → Update ONLY baseline fields
   - **PRESERVE**: `current_start`, `current_end`, `status`, `completion_percent`, `actual_*`
   - **UPDATE**: `planned_start`, `planned_end`, `planned_effort`, `revenue_impact`, etc.

3. **Ghost Check (CANCEL)**
   - Tasks in DB but missing from Excel → Set `status = 'Cancelled'`
   - We never hard delete (preserve historical data)

## Project Structure

```
Tracky_PM/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI entry point
│   │   ├── core/
│   │   │   ├── config.py              # Environment config
│   │   │   ├── database.py            # Supabase client
│   │   │   └── exceptions.py          # Custom exceptions
│   │   ├── models/
│   │   │   ├── enums.py               # Enum types matching DB
│   │   │   └── schemas.py             # Pydantic models
│   │   ├── services/
│   │   │   ├── parser/
│   │   │   │   ├── excel_parser.py    # Excel file parsing
│   │   │   │   └── validators.py      # Data validation
│   │   │   ├── ingestion/
│   │   │   │   ├── smart_merge.py     # Core merge algorithm
│   │   │   │   ├── resource_sync.py   # Resource processing
│   │   │   │   ├── hierarchy_sync.py  # Program/Project/Phase sync
│   │   │   │   └── dependency_sync.py # Dependency processing
│   │   │   └── recalculation/
│   │   │       └── engine.py          # Date recalculation (stub)
│   │   └── api/
│   │       └── routes/
│   │           └── import_routes.py   # Upload endpoints
│   ├── requirements.txt
│   └── .env.example
└── frontend/                          # (Phase 2)
```

## Getting Started

### Prerequisites
- Python 3.11+
- Supabase account and project

### Backend Setup

1. Navigate to backend directory:
   ```bash
   cd backend
   ```

2. Create virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Configure environment:
   ```bash
   cp .env.example .env
   # Edit .env with your Supabase credentials
   ```

5. Run the server:
   ```bash
   uvicorn app.main:app --reload
   ```

6. Access API docs:
   - Swagger UI: http://localhost:8000/docs
   - ReDoc: http://localhost:8000/redoc

## API Endpoints

### Import Excel File
```
POST /import/upload
Content-Type: multipart/form-data

Response:
{
  "status": "success",
  "summary": {
    "tasks_created": 5,
    "tasks_updated": 42,
    "tasks_preserved": 42,
    "tasks_cancelled": 1
  }
}
```

### Validate Excel File (without importing)
```
POST /import/validate
Content-Type: multipart/form-data
```

### Health Check
```
GET /health
```

## Database Schema

The database uses the following hierarchy:

```
Programs → Projects → Phases → Work Items
                                    ↓
                              Dependencies
                              Resources
                              Magic Tokens
```

### Work Items (Dual Timeline)
- **Baseline (Plan)**: `planned_start`, `planned_end` - Updated from Excel
- **Current (Forecast)**: `current_start`, `current_end` - System calculated
- **Actual (Reality)**: `actual_start`, `actual_end` - User input

## Development Phases

### Phase 1 (Current) ✅
- [x] Backend project structure
- [x] Excel parser service
- [x] Smart Merge algorithm
- [x] Hierarchy sync (Program/Project/Phase)
- [x] Resource sync
- [x] Dependency sync
- [x] Import API endpoints
- [x] Recalculation engine (stub)

### Phase 2 (Upcoming)
- [ ] Full recalculation engine
- [ ] Frontend dashboard
- [ ] ShadcnUI Impact Table
- [ ] Real-time updates

### Phase 3 (Future)
- [ ] Magic Links for updates
- [ ] AI-powered insights
- [ ] Advanced analytics

## License

Proprietary - All rights reserved
