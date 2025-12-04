# FA CS Automator

**Thomson Reuters Fixed Asset CS AI Automation Tool**

Automate the detection of asset schedules from various Excel files and import to Fixed Asset CS with AI-powered classification and RPA automation.

## Features

- **Auto-Detection**: Intelligent column detection from any Excel format
- **MACRS Classification**: AI-powered asset classification with rule-based engine + GPT fallback
- **Human-in-the-Loop**: CPA review and approval workflow before data conversion
- **Tax Compliance**: IRS Publication 946 compliant classifications
- **S3 Configuration**: Remote tax rules configuration via AWS S3
- **RPA Integration**: Playwright automation for Fixed Asset CS import (Windows)
- **Multi-Format Support**: Handles diverse client Excel formats
- **Session-Based**: Multi-user support with isolated sessions

## Deployment

| Component | Platform | URL |
|-----------|----------|-----|
| Backend API | Railway | `ai-antigravity-production.up.railway.app` |
| Frontend | Vercel | Configure with `VITE_API_URL` env var |

## Project Structure

```
FA_CS_Automator/
├── backend/                    # Python Backend
│   ├── api.py                 # FastAPI REST API server
│   ├── config/                # Configuration
│   │   ├── tax_rules.json    # Tax rules (local fallback)
│   │   └── s3_config_loader.py # S3 configuration loader
│   ├── logic/                 # Core processing logic
│   │   ├── smart_column_detector.py # Excel column auto-detection
│   │   ├── sheet_loader.py    # Multi-format Excel parsing
│   │   ├── transaction_classifier.py # Transaction classification
│   │   ├── macrs_tables.py    # MACRS depreciation tables
│   │   ├── fa_export.py       # FA CS export builder
│   │   ├── tax_year_config.py # Tax year configuration
│   │   ├── rollforward_reconciliation.py # Balance validation
│   │   └── convention_rules.py # MACRS convention detection
│   ├── models/                # Pydantic data models
│   ├── rpa/                   # RPA integration
│   │   ├── playwright_automation.py # Playwright RPA
│   │   ├── ai_rpa_orchestrator.py   # AI-guided RPA
│   │   └── rpa_fa_cs.py       # FA CS specific automation
│   └── database_manager.py    # SQLite database
├── src/                       # React Frontend
│   ├── components/           # React components
│   │   ├── Dashboard.jsx     # Main dashboard
│   │   ├── Review.jsx        # Asset review screen
│   │   ├── Import.jsx        # File import
│   │   └── Settings.jsx      # Configuration
│   ├── lib/                  # Utilities
│   │   └── api.client.js     # API client with retry
│   └── App.jsx               # Main React app
├── electron/                  # Electron desktop app
├── docs/                      # Documentation
├── Dockerfile.railway         # Railway deployment
├── vercel.json               # Vercel deployment
├── requirements.txt           # Python dependencies
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
```

### Frontend (React)

```bash
npm install
```

## Environment Variables

Create a `.env` file based on `.env.example`:

```bash
# OpenAI API Key (for GPT classification fallback)
OPENAI_API_KEY=sk-...

# AWS S3 Configuration (optional - for remote tax rules)
TAX_RULES_S3_BUCKET=fa-cs-automator-config-prod
TAX_RULES_S3_REGION=us-east-2
TAX_RULES_S3_KEY=tax_rules.json
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
```

## Running the Application

### Local Development

```bash
# Terminal 1 - Backend API
python -m backend.api
# API at http://127.0.0.1:8000

# Terminal 2 - React Frontend
npm run dev:server
# UI at http://localhost:5173
```

### Using npm scripts

```bash
# Run both backend and frontend
npm run dev
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/check-facs` | GET | Check FA CS connection status |
| `/stats` | GET | Dashboard statistics |
| `/upload` | POST | Upload Excel file for processing |
| `/assets` | GET | Get all loaded assets |
| `/assets/{id}/update` | POST | Update asset classification |
| `/assets/{id}/approve` | POST | Approve single asset |
| `/assets/approve-batch` | POST | Bulk approve assets |
| `/quality` | GET | Data quality score |
| `/rollforward` | GET | Rollforward reconciliation status |
| `/projection` | GET | 10-year depreciation projection |
| `/export` | GET | Export FA CS import file |
| `/docs` | GET | OpenAPI documentation |

## Human-in-the-Loop Workflow

1. **Upload**: CPA uploads client Excel file
2. **Detect**: System auto-detects columns and classifies assets
3. **Review**: CPA reviews classifications (low confidence highlighted)
4. **Approve**: CPA approves or overrides classifications
5. **Export**: System generates FA CS import file
6. **RPA** (Optional): Playwright imports data to Fixed Asset CS

## Classification Engine

Multi-tier classification with confidence scoring:

1. **User Overrides** - Previously corrected classifications (100% confidence)
2. **Rule-Based** - Pattern matching with 300+ rules (85-98% confidence)
3. **Client Category Mapping** - Map client categories to MACRS (85% confidence)
4. **GPT Fallback** - AI classification for ambiguous items (50-90% confidence)
5. **Keyword Fallback** - Basic keyword matching when GPT unavailable

## Tax Compliance Features

- **Section 179**: Automatic limits and phaseout calculation per tax year
- **Bonus Depreciation**: 100%/80%/60%/40%/20% based on placed-in-service date
- **Mid-Quarter Convention**: Automatic detection when >40% placed in Q4
- **De Minimis Safe Harbor**: Track expensed items under $2,500
- **Rollforward Reconciliation**: Balance validation for CPA review

## Configuration

Tax rules can be loaded from:
1. **AWS S3** (primary) - Remote configuration for production
2. **Local file** (fallback) - `backend/config/tax_rules.json`

## Tech Stack

- **Backend**: Python 3.11+, FastAPI, Pandas, boto3
- **AI**: OpenAI GPT-4o-mini for classification fallback
- **Frontend**: React 18, Vite, Tailwind CSS
- **Desktop**: Electron (optional)
- **RPA**: Playwright (Windows)
- **Database**: SQLite (session-based)
- **Deployment**: Railway (backend), Vercel (frontend)

## Documentation

See the `docs/` folder for detailed guides:

- [Active Features List](docs/ACTIVE_FEATURES_LIST.md)
- [Human-in-the-Loop Workflow](docs/HUMAN_IN_THE_LOOP_WORKFLOW.md)
- [FA CS Import Mapping](docs/FA_CS_IMPORT_MAPPING.md)

## License

Proprietary - All Rights Reserved

