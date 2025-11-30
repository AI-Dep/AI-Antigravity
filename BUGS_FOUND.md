# Bug Report: FA CS Automator

**Date:** 2025-11-30
**Reporter:** Claude (AI Code Auditor)
**Last Updated:** 2025-11-30

---

## FIX STATUS SUMMARY

| Bug | Severity | Status |
|-----|----------|--------|
| #1 Export without approval | CRITICAL | **FIXED** |
| #2 Backend ignores approvals | CRITICAL | **FIXED** |
| #3 Race condition in asset ID | CRITICAL | **FIXED** |
| #4 Global state shared | CRITICAL | PARTIAL (lock added, session manager ready but not integrated) |
| #5 File write races | HIGH | PARTIAL (temp files use UUID now) |
| #6 Frontend-backend desync | HIGH | **FIXED** |
| #7 No input validation | MEDIUM | **FIXED** |
| #8 Hardcoded URLs | MEDIUM | **FIXED** |
| #9 No pagination | MEDIUM | NOT FIXED |
| #10 Error log rotation | LOW | NOT FIXED |
| #11 Single-threaded classification | HIGH | INFRASTRUCTURE READY (job_processor.py) |
| #12 No OpenAI pooling | MEDIUM | NOT FIXED |
| #13 No request queue | HIGH | INFRASTRUCTURE READY (job_processor.py) |

**Additional Scalability Features Integrated:**
- Rate limiting middleware (token bucket algorithm)
- Request timeout middleware (configurable per operation)
- File cleanup scheduled task (automatic cleanup of temp files)
- Session cleanup scheduled task (automatic cleanup of expired sessions)

---

## CRITICAL BUGS (Must Fix)

### BUG #1: Export Allowed Without Full Approval
**Severity:** CRITICAL
**Location:** `src/components/Review.jsx:332-344`

**Description:**
The "Export to FA CS" button is only disabled when there are validation errors. It does NOT check:
- Whether ALL assets are approved
- Whether low-confidence assets have been reviewed/approved

**Current Code:**
```javascript
<Button
    onClick={handleExport}
    disabled={hasBlockingErrors}  // BUG: Only checks errors!
    ...
>
```

**Evidence from Screenshot:**
- 64 Total Assets
- 63 Approved
- 1 Needs Review (80% confidence shown at bottom)
- Export button is ACTIVE (green, clickable)

**Impact:**
- CPAs can accidentally export incomplete reviews
- Unapproved classifications go to FA CS
- Potential tax compliance issues

**Fix Required:**
```javascript
// Should also check:
const allApproved = stats.approved === stats.total;
const lowConfidenceApproved = localAssets
    .filter(a => a.confidence_score <= 0.8)
    .every(a => approvedIds.has(a.unique_id));

<Button
    disabled={hasBlockingErrors || !allApproved || !lowConfidenceApproved}
>
```

---

### BUG #2: Backend Export Ignores Approval Status
**Severity:** CRITICAL
**Location:** `backend/api.py:674-722`

**Description:**
The `/export` endpoint validates only for errors, not whether assets are approved.
The `APPROVED_ASSETS` set exists but is NEVER checked during export.

**Current Code:**
```python
@app.get("/export")
def export_assets():
    assets = list(ASSET_STORE.values())

    # Only checks for errors - NO approval check!
    assets_with_errors = [a for a in assets if getattr(a, 'validation_errors', None)]
    if assets_with_errors:
        raise HTTPException(...)

    # Exports ALL assets regardless of approval
    excel_file = exporter.generate_fa_cs_export(assets)
```

**Impact:**
- Even if frontend had proper validation, backend would still allow export
- API can be called directly, bypassing UI checks

---

### BUG #3: Race Condition in Asset ID Counter
**Severity:** CRITICAL (at scale)
**Location:** `backend/api.py:554-562`

**Description:**
No thread locking on global `ASSET_ID_COUNTER`. Concurrent uploads corrupt IDs.

**Current Code:**
```python
global ASSET_ID_COUNTER
ASSET_STORE.clear()  # Clears ALL users' data!
ASSET_ID_COUNTER = 0
for asset in classified_assets:
    asset.unique_id = ASSET_ID_COUNTER
    ASSET_STORE[ASSET_ID_COUNTER] = asset
    ASSET_ID_COUNTER += 1  # Race condition here
```

**Impact with 100+ users:**
- Two uploads at same time = duplicate IDs
- `ASSET_STORE.clear()` wipes other users' data mid-session
- Approval tracking breaks

---

### BUG #4: Global State Shared Between All Users
**Severity:** CRITICAL (at scale)
**Location:** `backend/api.py:75-99`

**Description:**
All these globals are shared without user isolation:
- `ASSET_STORE` - All users see same assets
- `APPROVED_ASSETS` - Approvals mixed between users
- `TAX_CONFIG` - User A changes tax year, affects User B
- `FACS_CONFIG` - Export path shared

**Impact:**
- User A uploads file → User B's assets disappear
- User A changes tax year to 2024 → User B's assets reclassified
- Complete data corruption with multiple concurrent users

---

### BUG #5: File Write Race Conditions
**Severity:** HIGH
**Locations:**
- `api.py:710` - Export file (no lock)
- `api.py:581-584` - Error log (no lock)
- `macrs_classification.py:78` - Overrides JSON (no lock)
- `client_mapping_manager.py:93` - Config files (no lock)

**Description:**
Multiple concurrent writes to same file = data corruption.

---

### BUG #6: Frontend-Backend Approval State Desync
**Severity:** HIGH
**Location:** `Review.jsx` + `api.py`

**Description:**
- Frontend tracks approvals in React state: `const [approvedIds, setApprovedIds] = useState(new Set())`
- Backend tracks in: `APPROVED_ASSETS: set = set()`
- Frontend calls `POST /assets/{id}/approve` but NEVER reads initial state
- Export uses ALL assets, not just approved ones

**Result:** Approval tracking is unreliable.

---

## STRUCTURAL ISSUES

### Issue #7: No Input Validation on Asset Updates
**Location:** `api.py:598-619`

Asset updates accept arbitrary fields without validation:
```python
for field, new_value in update_data.items():
    if hasattr(asset, field):
        setattr(asset, field, new_value)  # Any field can be set!
```

Could allow setting `validation_errors = []` to bypass error checks.

---

### Issue #8: Hardcoded localhost URLs in Frontend
**Location:** `Review.jsx:29, 38, 48, 213, 268, 272`

```javascript
await axios.get('http://127.0.0.1:8000/warnings');
await axios.post('http://127.0.0.1:8000/config/tax', ...);
```

Won't work in production deployment.

---

### Issue #9: No Pagination on Large Asset Lists
**Location:** `Review.jsx:549`

Renders ALL filtered assets in DOM:
```javascript
{filteredAssets.map((asset, index) => { ... })}
```

With 10,000 assets = browser freeze.

---

### Issue #10: Memory Leak in Error Handling
**Location:** `api.py:581-586`

Error log file opened with `"w"` mode, but errors accumulate:
```python
with open("backend_error.log", "w") as f:
    f.write(str(e))
```

Each error overwrites previous (actually good), but log is never rotated.

---

## CONCURRENCY ISSUES (100+ Users)

### Issue #11: Single-Threaded Classification
**Location:** `services/classifier.py`

Classification runs synchronously. With 100 users uploading 1000 assets each:
- 100,000 assets to classify sequentially
- API blocked during classification
- Request timeouts

---

### Issue #12: No Connection Pooling for OpenAI API
**Location:** `logic/macrs_classification.py`

Each classification batch creates new OpenAI client:
```python
client = OpenAI()  # New connection each time
```

With 100 users = 100 simultaneous OpenAI connections = rate limits hit.

---

### Issue #13: No Request Queue for Expensive Operations
Upload, classify, and export all run synchronously in request thread.
No queuing = server overwhelmed with concurrent requests.

---

## SUMMARY

| Bug ID | Severity | Type | Status |
|--------|----------|------|--------|
| #1 | CRITICAL | UI Logic | Needs Fix |
| #2 | CRITICAL | API Logic | Needs Fix |
| #3 | CRITICAL | Race Condition | Needs Fix |
| #4 | CRITICAL | No User Isolation | Needs Fix |
| #5 | HIGH | File Corruption | Needs Fix |
| #6 | HIGH | State Desync | Needs Fix |
| #7 | MEDIUM | Security | Needs Fix |
| #8 | MEDIUM | Config | Needs Fix |
| #9 | MEDIUM | Performance | Needs Fix |
| #10 | LOW | Logging | Nice to Have |
| #11 | HIGH | Scalability | Use Background Jobs |
| #12 | MEDIUM | API Limits | Add Pooling |
| #13 | HIGH | Scalability | Use Job Queue |
