# FA CS Automator

**Thomson Reuters Fixed Asset CS AI Automation Tool**

Automate the detection of asset schedules from various Excel files and import to Fixed Asset CS with RPA (UiPath).

## Features

- **Auto-Detection**: Intelligent column detection from any Excel format
- **MACRS Classification**: AI-powered asset classification with rule-based engine + GPT fallback
- **Human-in-the-Loop**: CPA review and approval workflow before data conversion
- **RPA Integration**: UiPath automation for Fixed Asset CS import
- **Multi-Format Support**: Handles diverse client Excel formats
- **Dual UI**: React web interface + Streamlit professional dashboard
- **SQLite Database**: Full audit trail and multi-client support
- **Tax Compliance**: IRS Publication 946 compliant classifications

## Project Structure

```
FA_CS_Automator/
├── backend/                    # Python Backend
│   ├── api.py                 # FastAPI REST API server
│   ├── streamlit_app.py       # Streamlit professional UI
│   ├── logic/                 # Core processing logic (57+ modules)
│   │   ├── column_detector.py # Excel column auto-detection
│   │   ├── sheet_loader.py    # Multi-format Excel parsing
│   │   ├── macrs_classification.py # MACRS classification engine
│   │   ├── fa_export.py       # FA CS export builder (150KB)
│   │   ├── database_schema.sql # SQLite schema
│   │   └── config/            # JSON configuration files
│   ├── models/                # Pydantic data models
│   ├── services/              # Business logic services
│   ├── rpa/                   # RPA integration
│   │   ├── uipath/           # UiPath XAML workflows
│   │   └── rpa_config.json   # RPA configuration
│   └── ui/                    # Desktop UI (Tkinter)
├── src/                       # React Frontend
│   ├── components/           # React components
│   └── App.jsx               # Main React app
├── docs/                      # Documentation
│   ├── ACTIVE_FEATURES_LIST.md
│   ├── HUMAN_IN_THE_LOOP_WORKFLOW.md
│   ├── FA_CS_IMPORT_MAPPING.md
│   └── ...
├── test_data/                 # Test data files
├── tests/                     # Test suite
├── requirements.txt           # Python dependencies
├── requirements-rpa.txt       # Windows RPA dependencies
└── package.json               # Node dependencies
```

## Installation

### Backend (Python)

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# For Windows RPA features
pip install -r requirements-rpa.txt
```

### Frontend (React)

```bash
npm install
```

## Running the Application

### Option 1: FastAPI + React (Development)

```bash
# Terminal 1 - Backend API
cd backend && python api.py
# API at http://127.0.0.1:8000

# Terminal 2 - React Frontend
npm run dev
# UI at http://localhost:5173
```

### Option 2: Streamlit (Production)

```bash
cd backend && streamlit run streamlit_app.py
# Opens at http://localhost:8501
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/check-facs` | GET | Check if FA CS is running |
| `/upload` | POST | Upload Excel file for processing |
| `/assets/{id}/update` | POST | Update asset classification |
| `/export` | GET | Export FA CS import file |
| `/docs` | GET | OpenAPI documentation |

## Human-in-the-Loop Workflow

1. **Upload**: CPA uploads client Excel file
2. **Detect**: System auto-detects columns and classifies assets
3. **Review**: CPA reviews classifications (low confidence highlighted)
4. **Approve**: CPA approves or overrides classifications
5. **Export**: System generates FA CS import file
6. **RPA**: UiPath imports data to Fixed Asset CS

## Classification Engine

Multi-tier classification with confidence scoring:

1. **User Overrides** - Previously corrected classifications (100% confidence)
2. **Rule-Based** - Pattern matching with 300+ rules (85-98% confidence)
3. **Client Category Mapping** - Map client categories to MACRS (85% confidence)
4. **GPT Fallback** - AI classification for ambiguous items (50-90% confidence)
5. **Keyword Fallback** - Basic keyword matching when GPT unavailable

## Configuration Files

| File | Purpose |
|------|---------|
| `backend/logic/config/rules.json` | 300+ classification rules |
| `backend/logic/config/overrides.json` | User override history |
| `backend/logic/config/client_input_mappings.json` | Client-specific column mappings |
| `backend/logic/config/bonus.json` | Bonus depreciation rules by year |
| `backend/logic/config/section179.json` | Section 179 limits |

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, Streamlit, Pandas
- **AI**: OpenAI GPT-4o-mini for classification fallback
- **Frontend**: React 18, Vite, Tailwind CSS
- **RPA**: UiPath (Windows only)
- **Database**: SQLite

## Documentation

See the `docs/` folder for detailed guides:

- [Active Features List](docs/ACTIVE_FEATURES_LIST.md)
- [Human-in-the-Loop Workflow](docs/HUMAN_IN_THE_LOOP_WORKFLOW.md)
- [FA CS Import Mapping](docs/FA_CS_IMPORT_MAPPING.md)
- [Example Input Format](docs/EXAMPLE_INPUT_FORMAT.md)
- [RPA Quickstart](docs/QUICKSTART_RPA.md)

## License

Proprietary - All Rights Reserved
