# FA CS Automator

**Thomson Reuters Fixed Asset CS AI Automation Tool**

Automate the detection of asset schedules from various Excel files and import to Fixed Asset CS with RPA (UiPath).

## Features

- **Auto-Detection**: Intelligent column detection from any Excel format
- **MACRS Classification**: AI-powered asset classification with rule-based engine
- **Human-in-the-Loop**: CPA review and approval workflow before data conversion
- **RPA Integration**: UiPath automation for Fixed Asset CS import
- **Multi-Format Support**: Handles diverse client Excel formats

## Project Structure

```
FA_CS_Automator/
├── backend/                    # Python Backend
│   ├── api.py                 # FastAPI main server
│   ├── logic/                 # Core processing logic
│   │   ├── column_detector.py # Excel column detection
│   │   ├── sheet_loader.py    # Excel parsing
│   │   ├── macrs_classification.py # MACRS classification engine
│   │   ├── fa_export.py       # FA CS export builder
│   │   └── config/            # JSON configuration files
│   ├── models/                # Data models
│   │   └── asset.py          # Asset Pydantic model
│   ├── services/              # Business logic services
│   │   ├── importer.py       # Excel import service
│   │   ├── classifier.py     # Classification service
│   │   ├── exporter.py       # Export service
│   │   └── auditor.py        # Audit trail service
│   ├── rpa/                   # RPA integration
│   │   ├── rpa_fa_cs.py      # FA CS automation
│   │   └── ai_rpa_orchestrator.py
│   └── ui/                    # Desktop UI (Tkinter)
├── src/                       # React Frontend
│   ├── App.jsx               # Main React app
│   ├── main.jsx              # Entry point
│   ├── index.css             # Styles
│   └── components/           # React components
│       ├── Dashboard.jsx
│       ├── Import.jsx
│       ├── Review.jsx
│       └── ui/               # UI primitives
├── tests/                     # Test files
├── index.html                 # Vite entry
├── package.json               # Node dependencies
├── requirements.txt           # Python dependencies
└── vite.config.js            # Vite configuration
```

## Installation

### Backend (Python)

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Frontend (React)

```bash
# Install Node dependencies
npm install

# Install additional dependencies
npm install -D tailwindcss postcss autoprefixer
npm install lucide-react clsx tailwind-merge class-variance-authority react-router-dom
```

## Running the Application

### Start Backend

```bash
cd backend
python api.py
# Server runs at http://127.0.0.1:8000
```

### Start Frontend

```bash
npm run dev
# Opens at http://localhost:5173
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/check-facs` | GET | Check if FA CS is running |
| `/upload` | POST | Upload Excel file for processing |
| `/assets/{id}/update` | POST | Update asset classification |
| `/export` | GET | Export FA CS import file |

## Human-in-the-Loop Workflow

1. **Upload**: CPA uploads client Excel file
2. **Detect**: System auto-detects columns and classifies assets
3. **Review**: CPA reviews classifications, confidence scores highlighted
4. **Approve**: CPA approves or overrides classifications
5. **Export**: System generates FA CS import file
6. **RPA**: UiPath imports data to Fixed Asset CS

## Configuration Files

- `backend/logic/config/rules.json` - Classification rules
- `backend/logic/config/overrides.json` - User overrides
- `backend/logic/config/client_input_mappings.json` - Client-specific mappings

## Tech Stack

- **Backend**: Python, FastAPI, Pandas, OpenAI
- **Frontend**: React, Vite, Tailwind CSS
- **RPA**: UiPath
- **Database**: SQLite (for persistence)

## License

Proprietary - All Rights Reserved
