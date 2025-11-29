# FA CS Automator Setup Guide

## Quick Start

### 1. Backend Setup (Python)

```bash
# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (Mac/Linux)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Frontend Setup (Node.js)

```bash
# Install dependencies
npm install

# Install additional packages (if not in package.json)
npm install -D tailwindcss postcss autoprefixer
npm install lucide-react clsx tailwind-merge class-variance-authority react-router-dom
```

### 3. Run the Application

**Terminal 1 - Backend:**
```bash
cd backend
python api.py
```

**Terminal 2 - Frontend:**
```bash
npm run dev
```

### 4. Access the Application

- **Frontend**: http://localhost:5173
- **Backend API**: http://127.0.0.1:8000
- **API Docs**: http://127.0.0.1:8000/docs

## Environment Variables (Optional)

Create a `.env` file in the root directory:

```env
OPENAI_API_KEY=your_api_key_here
```

## Notes

- Make sure Fixed Asset CS is installed on the target machine for RPA
- The RPA component requires UiPath to be configured
- Database will be created automatically on first run
