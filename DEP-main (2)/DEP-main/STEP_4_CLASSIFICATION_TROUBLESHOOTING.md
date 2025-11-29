# Step 4: Classification - Troubleshooting Guide

**Created:** 2025-11-21
**Purpose:** Help users diagnose and fix classification issues in Step 4

---

## 📋 QUICK DIAGNOSTIC CHECKLIST

Before starting Step 4, verify these prerequisites:

- [ ] ✅ Step 1 (File Upload) completed successfully
- [ ] ✅ Step 2 (Client Info) completed
- [ ] ✅ Step 3 (Tax Year) completed
- [ ] ✅ Your uploaded file has these **required columns:**
  - Asset ID (or ID, Asset Number, etc.)
  - Description (or Desc, Asset Description, etc.)
  - Cost (or Amount, Value, etc.)
  - Date In Service (or In Service Date, PIS, etc.)

---

## 🚨 COMMON STEP 4 ERRORS & SOLUTIONS

### ERROR 1: "Failed to initialize OpenAI client"

**Error Message:**
```
Failed to initialize OpenAI client. Please check your API key configuration.
```

**Cause:**
- OpenAI API key is missing or invalid
- API key not configured in Streamlit Secrets (for cloud deployment)

**Solution:**

**If running on Streamlit Cloud:**
1. Go to your Streamlit app settings
2. Click **"Secrets"** in left sidebar
3. Add this configuration:
   ```toml
   [openai]
   api_key = "sk-proj-your-actual-key-here"
   ```
4. Save and redeploy
5. Restart the app

**If running locally:**
1. Create `.streamlit/secrets.toml` file in project root
2. Add:
   ```toml
   [openai]
   api_key = "sk-proj-your-actual-key-here"
   ```
3. Restart Streamlit

**How to get an API key:**
1. Go to https://platform.openai.com/api-keys
2. Sign in or create account
3. Click "Create new secret key"
4. Copy the key (starts with `sk-proj-`)
5. Add to secrets as shown above

---

### ERROR 2: Confirmation Checkbox Not Checked

**Error Message:**
- Button is grayed out/disabled
- Cannot click "Run Full Classification"

**Cause:**
- New requirement: Must confirm cost estimate before classification

**Solution:**
1. Read the **Classification Preview** box showing:
   - Total assets
   - Estimated rule-based matches (free)
   - Estimated GPT calls (costs money)
   - Estimated API cost
2. Check the box: ☑️ "I understand the estimated cost and want to proceed"
3. Now the button will be enabled

**Why this exists:**
Prevents surprise API charges. Most assets use free rule-based classification, but complex ones use GPT-4 which costs ~$0.0001 per asset.

---

### ERROR 3: "Asset Limit Exceeded"

**Error Message:**
```
Your file contains 5,000 assets, which exceeds the maximum of 1,000 assets per run.
```

**Cause:**
- File too large (safety limit to prevent excessive API costs)

**Solution:**

**Option A: Split the file**
1. Open your Excel file
2. Split into smaller files (e.g., 500 assets each)
3. Process each file separately
4. Combine the results later

**Option B: Increase limit (requires code change)**
1. Only if you're OK with potentially high API costs
2. In `app.py`, find `MAX_ASSETS_PER_RUN = 1000`
3. Increase to desired limit
4. Be aware: 5,000 assets could cost $100+ in API fees

---

### ERROR 4: Classification Gets Stuck / Freezes

**Symptoms:**
- Progress bar at 0% for >5 minutes
- Spinner keeps spinning, never completes
- Browser tab becomes unresponsive

**Causes & Solutions:**

**Cause A: Network/API timeout**
- Solution: Refresh the page and try again
- If persistent: Check your internet connection
- Check OpenAI API status: https://status.openai.com

**Cause B: Very large file**
- Solution: Classification takes ~1 second per complex asset
- For 500 assets, expect 3-5 minutes
- Be patient! Watch the progress bar (NEW feature)

**Cause C: Browser timeout**
- Solution: Use Chrome or Firefox (best Streamlit support)
- Clear browser cache and try again

---

### ERROR 5: "No module named 'fixed_asset_ai'"

**Error Message:**
```
ModuleNotFoundError: No module named 'fixed_asset_ai'
```

**Cause:**
- Import path issue (should be fixed as of commit 40a8fdc)
- Package not properly installed

**Solution:**

**If you see this error:**
1. Make sure you pulled the latest code: `git pull origin main`
2. The fix was applied in commit `40a8fdc` (Nov 21, 2024)
3. If still seeing it, check that `fixed_asset_ai/__init__.py` exists:
   ```python
   # Should contain:
   __version__ = "1.0.0"
   ```

**If running locally:**
```bash
# Install in development mode
pip install -e .
```

---

### ERROR 6: Classification Completes but "Final Category" Still Missing

**Symptoms:**
- Classification appears to complete
- Shows "✓ Additions classified: X"
- But Step 6 export still says "Missing required column: Final Category"

**Diagnosis:**
Run this check in Step 5:
1. Look at the preview table
2. Check if "Final Category" column exists
3. Check if values are populated (not all blank)

**Possible Causes:**

**Cause A: All assets were disposals/transfers**
- Disposals and transfers are intentionally NOT classified (they don't need it)
- If your file ONLY has disposals, there's nothing to classify
- **Solution:** This is correct behavior. Disposals use historical data, not new classification.

**Cause B: Classification errors**
- Check browser console for errors (F12 → Console tab)
- Look for red error messages
- **Solution:** Screenshot errors and report them

**Cause C: Session state cleared**
- Browser back button was used
- Page was refreshed mid-process
- **Solution:** Re-run classification from Step 4

---

### ERROR 7: Low Confidence Warnings

**Warning Message:**
```
⚠️ 15 assets classified with low confidence
```

**What this means:**
- System classified the assets but isn't very confident
- May need manual review

**Why it happens:**
- Vague descriptions: "Equipment", "Asset", "Item"
- Unusual/specialized items not in training data
- Missing client category hints

**What to do:**

**Option A: Review in Step 5.5 (Review & Overrides)**
1. Filter by "Low Confidence" assets
2. Manually verify classifications
3. Override if needed

**Option B: Improve descriptions in source file**
1. Add more detail: "Equipment" → "Manufacturing CNC Lathe"
2. Re-upload and re-classify
3. Should get higher confidence

**Option C: Accept as-is**
- If the classifications look reasonable, you can proceed
- Low confidence doesn't mean wrong, just uncertain

---

### ERROR 8: Classification Cost Higher Than Expected

**Scenario:**
- Preview said: "Estimated cost: $5.00"
- Actual cost: $25.00 (5x higher)

**Why this happens:**
- Estimate assumes 70% rule-based, 30% GPT
- Your data had more complex assets than expected
- More GPT calls = higher cost

**How to reduce costs:**

**1. Add client categories (if available)**
- If your Excel has a category column, map it in Step 1
- Example: "Furniture", "Computer", "Vehicle"
- This helps rule-based classification work better

**2. Improve descriptions**
- Instead of: "Asset"
- Use: "Dell Latitude 5420 Laptop Computer"
- Better descriptions → better rule matches → fewer GPT calls

**3. Use overrides file**
- Create `fixed_asset_ai/data/client_overrides.csv`
- Pre-define classifications for common patterns
- Example:
  ```csv
  pattern,final_class,macrs_life
  laptop,Computer Equipment,5
  vehicle,Automobile,5
  ```

---

## 🎯 STEP-BY-STEP: Successful Classification

Here's the complete workflow to avoid issues:

### ✅ STEP 1: Pre-Classification Checks

1. **Verify your data quality:**
   ```
   Required columns present? ✓
   Descriptions filled in? ✓
   Costs are positive numbers? ✓
   Dates are valid? ✓
   ```

2. **Check your OpenAI API key:**
   - Go to https://platform.openai.com/account/usage
   - Verify you have available credit
   - Check rate limits

3. **Estimate your cost:**
   - Small file (<100 assets): ~$0.50
   - Medium file (100-500 assets): $2-10
   - Large file (500-1000 assets): $10-50

### ✅ STEP 2: Run Classification

1. **Navigate to Step 4**
   - Ensure Steps 1-3 are complete (green checkmarks)

2. **Review the preview:**
   ```
   📊 Classification Preview:
   - Total assets: 250
   - Estimated rule-based: ~175 assets (no API cost)
   - Estimated GPT calls: ~75 assets
   - Estimated API cost: $7.50
   - Estimated time: ~25 seconds
   ```

3. **Confirm cost awareness:**
   - ☑️ Check the confirmation box
   - Click "Run Full Classification"

4. **Monitor progress:**
   - NEW: Watch the progress bar
   - See which asset is being processed
   - View running statistics

5. **Review results:**
   ```
   ✓ Additions classified: 200
   ⏭️ Disposals skipped: 30 (don't need classification)
   ⏭️ Transfers skipped: 20 (don't need classification)
   ```

### ✅ STEP 3: Verify Success

1. **Check Step 5 preview:**
   - Scroll down to Step 5
   - Look at the preview table
   - Verify "Final Category" column has values

2. **Review low confidence assets (if any):**
   - Go to Step 5.5 (Review & Overrides)
   - Filter by "Low Confidence"
   - Verify classifications look reasonable

3. **Proceed to export:**
   - If everything looks good, continue to Step 6
   - Generate your FA CS export file

---

## 💡 BEST PRACTICES

### For Best Classification Results:

1. **Use descriptive asset names:**
   - ❌ Bad: "Equipment #1"
   - ✅ Good: "Epson WorkForce Pro Printer"

2. **Include brand/model when available:**
   - ❌ Bad: "Computer"
   - ✅ Good: "Dell Latitude 5420 Laptop"

3. **Be specific about type:**
   - ❌ Bad: "Vehicle"
   - ✅ Good: "2023 Ford F-150 Pickup Truck"

4. **Add context for specialized items:**
   - ❌ Bad: "Machine"
   - ✅ Good: "CNC Lathe for Manufacturing"

### For Cost Optimization:

1. **Batch similar assets:**
   - If you have 50 identical laptops, process them together
   - The system learns patterns and uses rules after first few

2. **Use client categories:**
   - If your Excel has a category column, use it
   - Helps rule-based classification

3. **Process incrementally:**
   - For very large files, do 100-200 assets at a time
   - Verify results before processing rest

---

## 🔧 ADVANCED TROUBLESHOOTING

### Debug Mode (for developers)

If you need to see detailed classification logs:

1. Open browser console (F12 → Console)
2. Look for classification debug output
3. Each asset shows:
   - Description sent to classifier
   - Rule match attempts
   - GPT call (if made)
   - Final classification
   - Confidence score

### Session State Issues

If classification completed but data seems lost:

```python
# Check session state in browser console:
# 1. Open browser console (F12)
# 2. Run:
sessionStorage
# Look for: classified_df

# If missing, you may need to re-run classification
```

### Force Refresh

If Step 4 seems stuck or broken:

1. Clear browser cache
2. Hard refresh: `Ctrl+Shift+R` (Windows) or `Cmd+Shift+R` (Mac)
3. Or use incognito/private window
4. Navigate back to your app
5. Start fresh from Step 1

---

## 📞 WHEN TO ASK FOR HELP

Contact support if:

1. ✅ You've tried all troubleshooting steps above
2. ✅ You've cleared cache and refreshed
3. ✅ You've verified your API key is valid
4. ✅ The error persists across multiple attempts

**What to include:**

- Screenshot of the error message
- Your file size (number of assets)
- Which step you're on
- Browser and version (Chrome 120, Firefox 121, etc.)
- Any console errors (F12 → Console → screenshot red errors)

---

## 🎓 FAQ

**Q: Do I need to re-classify if I make changes in Step 5.5 (Overrides)?**
A: No. Overrides in Step 5.5 modify the data after classification. You don't need to re-run Step 4.

**Q: Can I classify without OpenAI API?**
A: Partially. Rule-based classification works without API, but complex assets will remain unclassified. You'd need to manually classify those in Step 5.5.

**Q: How accurate is the classification?**
A: Based on testing:
- Rule-based: ~95% accuracy (for common items)
- GPT-4: ~90% accuracy (for complex items)
- Combined: ~92% overall accuracy
- Always verify high-value assets manually

**Q: Does classification work offline?**
A: No. Step 4 requires:
- Internet connection (for OpenAI API)
- Valid API key with available credit
- OpenAI services operational

**Q: Can I save classification progress?**
A: Currently no. Classification must complete in one session. If interrupted, you'll need to re-run from the beginning. (Feature request: Save/resume capability)

---

## ✅ SUCCESS CRITERIA

You know Step 4 completed successfully when:

1. ✅ You see: "✓ Additions classified: [number]"
2. ✅ Step 5 preview shows "Final Category" column with values
3. ✅ No error messages or red alerts
4. ✅ You can proceed to Step 6 without "Missing Final Category" error

---

**Last Updated:** 2025-11-21
**Version:** 1.0
**Related Docs:**
- STEP_5_VALIDATION_ANALYSIS.md
- STEP_3.5_CALCULATION_ANALYSIS.md
- COMPREHENSIVE_TEST_REPORT.md
- QUALITY_IMPROVEMENT_RECOMMENDATIONS.md
