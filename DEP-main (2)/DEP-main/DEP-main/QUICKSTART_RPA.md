# Quick Start Guide - RPA Automation

## 5-Minute Setup

### 1. Install Dependencies (One Time)

```bash
# Install base dependencies
pip install -r requirements.txt

# Install RPA dependencies (Windows only, for automation features)
pip install -r requirements-rpa.txt
```

### 2. Setup OpenAI API Key (One Time)

Create a `.env` file:
```bash
OPENAI_API_KEY=sk-your-key-here
```

### 3. Start Fixed Asset CS

- Launch Fixed Asset CS application
- Open your client file
- Leave window visible (don't minimize)

### 4. Run the Application

```bash
streamlit run fixed_asset_ai/app.py
```

### 5. Complete the Workflow

1. **Upload** your Excel file (Step 1)
2. **Classify** assets (Step 4)
3. **Test Connection** to FA CS (Step 7)
4. **Run Preview** (first 3 assets)
5. **Run Full Automation**

---

## First-Time Checklist

Before running RPA automation:

- [ ] Fixed Asset CS is running
- [ ] FA CS window is visible (not minimized)
- [ ] No other applications stealing focus
- [ ] Mouse/keyboard free for automation
- [ ] Screen saver disabled
- [ ] .env file with OpenAI API key exists
- [ ] All dependencies installed

---

## Common First-Run Issues

### "Cannot connect to Fixed Asset CS"

**Fix:**
1. Make sure FA CS is actually running
2. Check Task Manager for "FAwin.exe" process
3. If different process name, edit `rpa_config.json`:
   ```json
   {
     "rpa_settings": {
       "fa_cs_process_name": "YourProcessName.exe"
     }
   }
   ```

### "OpenAI API Error"

**Fix:**
1. Check your `.env` file exists in project root
2. Verify API key is valid
3. Check billing on OpenAI account

### "RPA too fast/slow"

**Fix:**
Edit `rpa_config.json` timing values:
```json
{
  "timing": {
    "wait_after_click": 0.8,    // Increase if too fast
    "wait_after_typing": 0.5,   // Increase if typing skips chars
    "wait_for_window": 3.0      // Increase if windows load slow
  }
}
```

---

## Testing Your Setup

### Test 1: AI Classification

```bash
streamlit run fixed_asset_ai/app.py
```

1. Upload a small test file (5-10 assets)
2. Click "Run Full Classification"
3. Should complete in 10-30 seconds
4. Review results

### Test 2: FA CS Connection

1. Start Fixed Asset CS
2. In Streamlit app, go to Step 7
3. Click "Test FA CS Connection"
4. Should show green checkmark ✓

### Test 3: Preview Mode

1. Keep FA CS open
2. Click "Run RPA Automation" with Preview Mode ON
3. Watches as it processes 3 assets
4. Verify they appear in FA CS

---

## Your First Full Run

Once all tests pass:

1. Upload your full client file
2. Run classification
3. Review and override any low-confidence items
4. Generate FA CS export (creates backup)
5. **Uncheck** Preview Mode
6. Click "Run RPA Automation"
7. **DON'T TOUCH KEYBOARD/MOUSE**
8. Monitor progress in Streamlit
9. Review results when complete

---

## Emergency Stop

If something goes wrong:

1. **Move mouse to screen corner** (if failsafe enabled)
2. Or press `Ctrl+C` in terminal
3. Or close Streamlit app

Resume later from last successful asset index.

---

## Getting Help

1. Check `README_RPA.md` for full documentation
2. Review execution logs (Step 8)
3. Check error screenshots in working directory

---

**You're ready to go! Start with a small test file first.**
