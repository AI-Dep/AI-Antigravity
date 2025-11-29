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

### 3. Start Fixed Asset CS and Complete Manual Login

⚠️ **CRITICAL: You MUST manually complete the entire FA CS login process.**

**RPA CANNOT automate the login steps.** Complete these steps manually:

1. **Launch RemoteApp**
   - Open the Fixed Asset CS RemoteApp shortcut
   - Wait for "Starting your app..." screen to complete

2. **Enter Windows Credentials** (MANUAL - Cannot be automated)
   - Windows Security dialog will appear
   - Manually type your username and password
   - Click OK

3. **Wait for RemoteApp Configuration** (MANUAL - Cannot be automated)
   - Allow RemoteApp to configure the session
   - This typically takes 10-30 seconds

4. **Click FA CS Sign-In Button** (MANUAL - Cannot be automated)
   - When "Let's get started - Sign in" appears
   - Manually click the button

5. **Complete Thomson Reuters Login** (MANUAL - Cannot be automated)
   - Browser opens (usually Edge)
   - Enter your work email
   - Enter your password
   - Click Sign In

6. **Enter MFA Code** (MANUAL - Cannot be automated)
   - Check your smartphone for verification code
   - Enter the 6-digit code
   - Click Verify

7. **Verify FA CS is Ready**
   - ✅ FA CS main window is visible (not minimized)
   - ✅ You are fully logged in
   - ✅ No login prompts are showing
   - ✅ You can see client data / main menu

**See [FA_CS_LOGIN_LIMITATIONS.md](FA_CS_LOGIN_LIMITATIONS.md) for detailed explanation of why these steps cannot be automated.**

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

### Manual Login Completed:
- [ ] **Completed Windows Security credential entry** (MANUAL step)
- [ ] **Completed RemoteApp session configuration** (MANUAL step)
- [ ] **Clicked FA CS Sign-In button** (MANUAL step)
- [ ] **Completed Thomson Reuters browser login** (MANUAL step)
- [ ] **Entered email and password** (MANUAL step)
- [ ] **Entered MFA verification code from phone** (MANUAL step - REQUIRED)
- [ ] **FA CS is fully logged in and main window visible**

### RPA Prerequisites:
- [ ] Fixed Asset CS is running AND fully logged in
- [ ] FA CS window is visible (not minimized)
- [ ] No login prompts are showing
- [ ] You can see client data in FA CS
- [ ] No other applications stealing focus
- [ ] Mouse/keyboard free for automation
- [ ] Screen saver disabled
- [ ] .env file with OpenAI API key exists
- [ ] All dependencies installed

⚠️ **CRITICAL**: Do not attempt to run RPA until ALL manual login steps are complete!

---

## Common First-Run Issues

### "Cannot connect to Fixed Asset CS"

**Fix:**
1. **Make sure you have MANUALLY COMPLETED the entire login process:**
   - Windows Security credential prompt ✓
   - RemoteApp session configuration ✓
   - FA CS Sign-In button click ✓
   - Thomson Reuters browser login ✓
   - Email/Password entry ✓
   - MFA code entry ✓
2. Verify FA CS main window is visible (not login screen)
3. Check Task Manager for "FAwin.exe" process
4. If different process name, edit `rpa_config.json`:
   ```json
   {
     "rpa_settings": {
       "fa_cs_process_name": "YourProcessName.exe"
     }
   }
   ```

⚠️ **IMPORTANT**: RPA CANNOT automate the login process. You MUST complete all login steps manually before running RPA.

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
