# Human-in-the-Loop Approval Workflow

## Overview

This document describes the **mandatory human approval workflow** for Fixed Asset CS exports before RPA automation. This is a **CRITICAL production safety feature** for tax compliance.

---

## Why Human-in-the-Loop?

### Tax Compliance Requirements
- **IRC regulations** require professional judgment
- **Materiality decisions** need human oversight
- **Audit defense** requires documented review
- **Professional liability** demands CPA sign-off

### RPA Safety
- **Prevents automation errors** before they occur
- **Catches data quality issues** before import
- **Validates tax calculations** before submission
- **Ensures Fixed Asset CS compatibility**

### Audit Trail
- **Documented approvals** for IRS review
- **Timestamped checkpoints** for compliance
- **Named approvers** for accountability
- **Detailed justifications** for decisions

---

## Three-Checkpoint Approval System

### 🔍 **Checkpoint 1: Export Quality Review**

**Purpose**: Automated validation of export file quality

**Checks**:
- ✅ All required columns present
- ✅ No duplicate Asset IDs
- ✅ Proper date formats (Excel compatible)
- ✅ Valid number formats
- ✅ No null/missing required fields
- ✅ Data consistency (Sec179 + Bonus ≤ Cost)
- ✅ RPA compatibility (no problematic characters)

**Outcomes**:
- **CRITICAL errors**: BLOCKS workflow (must fix)
- **ERROR issues**: Requires human approval or fix
- **WARNINGS only**: Auto-approve or human review
- **PERFECT QUALITY**: Auto-approve option available

**Approval Options**:
```python
# Option A: Auto-approve if perfect
checkpoint_1_quality_review(df, auto_approve_if_perfect=True)

# Option B: Always require human approval
checkpoint_1_quality_review(df, auto_approve_if_perfect=False)
```

---

### 💰 **Checkpoint 2: Tax Calculation Review**

**Purpose**: Human verification of tax calculations

**Review Areas**:
1. **Section 179 Expensing**
   - Verify amounts don't exceed limits ($2.5M for 2025)
   - Check phase-out threshold ($4M for 2025)
   - Confirm eligible property only

2. **Bonus Depreciation**
   - Verify correct percentage (80% TCJA vs 100% OBBB)
   - Check acquisition and in-service dates
   - Confirm qualified property

3. **MACRS Classifications**
   - Verify recovery periods (3, 5, 7, 15, 20, 27.5, 39 years)
   - Check methods (200DB, 150DB, SL)
   - Confirm conventions (HY, MQ, MM)

4. **De Minimis Safe Harbor**
   - Verify amounts ≤ $2,500 threshold
   - Confirm eligible items

5. **Section 179 Carryforward**
   - Verify taxable income limitation
   - Confirm carryforward calculations
   - Check Form 4562 disclosure

**Variance Analysis**:
```python
# Provide expected totals for automated comparison
expected_totals = {
    "total_section_179": 500000.00,
    "total_bonus": 1200000.00,
    "year1_total_deduction": 1850000.00,
}

checkpoint_2_tax_review(df, tax_year=2024, expected_totals=expected_totals)
```

**Decision**: ALWAYS requires human approval (no auto-approve)

---

### ✅ **Checkpoint 3: Pre-RPA Checklist**

**Purpose**: Final verification before RPA automation

**Critical Checks**:
1. ✅ Export file exists and is readable
2. ✅ No duplicate Asset IDs (CRITICAL for RPA)
3. ✅ All required columns present
4. ✅ No null Asset IDs
5. ✅ Data consistency validated

**RPA Compatibility**:
- File format: Excel (.xlsx)
- Sheet name: FA_Import
- Column names: Match Fixed Asset CS expected format
- No control characters or problematic text
- Asset IDs: Unique and valid

**Decision**: Can auto-pass if all checks pass, but approval still recommended

---

### 📋 **Final Approval & Sign-Off**

**Purpose**: Create audit trail with named approver

**Required Information**:
- Approver name (e.g., "John Smith, CPA")
- Approver email
- Approval timestamp (auto-generated)
- Optional notes/justification

**Approval Record**:
```json
{
  "approval_id": "20241215_143022",
  "approval_timestamp": "2024-12-15T14:30:22",
  "approver_name": "John Smith, CPA",
  "approver_email": "jsmith@accounting.com",
  "approval_notes": "All calculations verified. Section 179 carryforward confirmed.",
  "status": "FINAL_APPROVED",
  "rpa_ready": true,
  "checkpoints": {
    "checkpoint_1_quality": { ... },
    "checkpoint_2_tax": { ... },
    "checkpoint_3_checklist": { ... }
  }
}
```

**Audit Trail**:
- Saved to JSON file: `approval_YYYYMMDD_HHMMSS.json`
- Contains all checkpoint results
- Includes validation errors/warnings
- Timestamped and signed
- Immutable record for IRS audit

---

## Workflow Options

### Option 1: Interactive Workflow (Recommended for First-Time Use)

**Best for**: Learning the system, complex scenarios, unusual situations

```python
from fixed_asset_ai.logic.human_approval_workflow import interactive_approval_workflow

approved, approval_record = interactive_approval_workflow(
    df=export_dataframe,
    export_file_path="FA_Import_2024.xlsx",
    tax_year=2024,
    expected_totals=None  # Optional
)

if approved:
    print("✅ RPA AUTHORIZED - Proceed with automation")
    # Run RPA automation here
else:
    print("❌ RPA NOT AUTHORIZED - Do not proceed")
```

**Features**:
- Step-by-step guidance through all checkpoints
- Prompts for human input at each stage
- Real-time display of validation results
- Interactive approval at each checkpoint
- Collects approver information
- Requires explicit "YES" for final approval

---

### Option 2: Programmatic Workflow (Recommended for Production)

**Best for**: Batch processing, repeated scenarios, automated pipelines

```python
from fixed_asset_ai.logic.human_approval_workflow import (
    checkpoint_1_quality_review,
    checkpoint_2_tax_review,
    checkpoint_3_pre_rpa_checklist,
    final_approval_and_signoff,
    save_approval_record,
)

# Checkpoint 1: Quality (auto-approve if perfect)
quality_approved, validation_summary, _ = checkpoint_1_quality_review(
    df, auto_approve_if_perfect=True
)

if not quality_approved:
    # Handle rejection (email alert, log, etc.)
    raise Exception("Quality validation failed")

# Checkpoint 2: Tax Review
tax_approved, tax_summary = checkpoint_2_tax_review(
    df, tax_year=2024, expected_totals=expected_totals
)

# Human reviews tax summary and approves programmatically
# (In production: email summary, wait for approval via web interface, etc.)

# Checkpoint 3: Pre-RPA
checklist_passed, checklist = checkpoint_3_pre_rpa_checklist(
    df, "FA_Import_2024.xlsx"
)

# Final approval with programmatic sign-off
approval_record = final_approval_and_signoff(
    validation_summary=validation_summary,
    tax_summary=tax_summary,
    checklist=checklist,
    approver_name="Tax Manager",
    approver_email="taxmgr@company.com",
    notes="Automated approval - standard scenario"
)

# Save audit trail
save_approval_record(approval_record)

# Proceed with RPA
if approval_record['rpa_ready']:
    # Run RPA automation
    pass
```

---

### Option 3: Hybrid Workflow (Recommended for Most Users)

**Best for**: Production use with quality gates

```python
# Auto-approve quality if perfect
quality_approved, validation_summary, approval_status = checkpoint_1_quality_review(
    df, auto_approve_if_perfect=True
)

if approval_status == "REJECTED":
    # Critical errors - stop immediately
    send_alert("CRITICAL: Export quality check failed")
    return

# Always require human review for tax
tax_approved, tax_summary = checkpoint_2_tax_review(df, 2024)

# Email tax summary to CPA for review
send_email_for_approval(tax_summary)

# Wait for approval (polling, webhook, etc.)
while not tax_approved:
    wait_for_approval()

# Auto-pass pre-RPA if all checks pass
checklist_passed, checklist = checkpoint_3_pre_rpa_checklist(df, filepath)

# Final sign-off
approval_record = final_approval_and_signoff(
    validation_summary, tax_summary, checklist,
    approver_name=get_approver_from_email(),
    approver_email=get_approver_email(),
    notes=get_approval_notes()
)

save_approval_record(approval_record)

# Safe to proceed with RPA
run_rpa_automation()
```

---

## Integration with Existing Workflow

### Before Human-in-the-Loop:
```python
# OLD WORKFLOW (NOT RECOMMENDED)
from fixed_asset_ai.logic.fa_export import build_fa, export_fa_excel

# 1. Build export
fa_df = build_fa(df, tax_year=2024, strategy="Aggressive", taxable_income=500000)

# 2. Save to Excel
excel_bytes = export_fa_excel(fa_df)
with open("FA_Import_2024.xlsx", "wb") as f:
    f.write(excel_bytes)

# 3. Run RPA immediately (DANGEROUS!)
run_rpa_bot("FA_Import_2024.xlsx")  # ❌ NO HUMAN OVERSIGHT!
```

### After Human-in-the-Loop:
```python
# NEW WORKFLOW (RECOMMENDED)
from fixed_asset_ai.logic.fa_export import build_fa, export_fa_excel
from fixed_asset_ai.logic.human_approval_workflow import interactive_approval_workflow

# 1. Build export
fa_df = build_fa(df, tax_year=2024, strategy="Aggressive", taxable_income=500000)
# Note: build_fa() now automatically runs checkpoint 1 (quality validation)

# 2. Save to Excel
excel_bytes = export_fa_excel(fa_df)
filepath = "FA_Import_2024.xlsx"
with open(filepath, "wb") as f:
    f.write(excel_bytes)

# 3. HUMAN APPROVAL WORKFLOW
approved, approval_record = interactive_approval_workflow(
    df=fa_df,
    export_file_path=filepath,
    tax_year=2024
)

# 4. Run RPA ONLY if approved
if approved:
    run_rpa_bot(filepath)  # ✅ SAFE - Human approved
    log_approval(approval_record)  # Audit trail
else:
    send_alert("RPA blocked - approval not granted")
```

---

## Approval Decision Matrix

| Checkpoint | Auto-Approve Available? | Human Review Required? | Blocking Errors? |
|------------|------------------------|------------------------|------------------|
| **1. Quality** | ✅ Yes (if perfect) | Optional (if warnings) | ✅ Yes (critical) |
| **2. Tax** | ❌ No | ✅ Always | ❌ No |
| **3. Pre-RPA** | ✅ Yes (if all pass) | Recommended | ⚠️ Can override |
| **Final** | ❌ No | ✅ Always | N/A |

---

## Best Practices

### For Tax Professionals:
1. **ALWAYS review Checkpoint 2** (tax calculations) personally
2. **Document unusual decisions** in approval notes
3. **Verify Section 179 carryforward** calculations
4. **Check for audit red flags** (large amounts, unusual patterns)
5. **Keep approval records** for 7 years (IRS audit period)

### For RPA Developers:
1. **NEVER bypass approval workflow** for tax data
2. **Check approval record** before running RPA bot
3. **Log approval ID** with RPA execution for traceability
4. **Handle rejections gracefully** (alerts, logging, retry)
5. **Test with demo scenarios** before production

### For System Administrators:
1. **Store approval records** in secure location
2. **Back up approval trail** regularly
3. **Monitor approval patterns** for anomalies
4. **Set up email alerts** for rejections
5. **Audit approval workflow** periodically

---

## Security & Compliance

### Audit Trail Requirements:
- ✅ Who approved (name + email)
- ✅ When approved (timestamp)
- ✅ What was approved (full data snapshot)
- ✅ Why approved (notes/justification)
- ✅ Validation results (all checkpoints)

### IRS Compliance:
- ✅ Professional responsibility (CPA sign-off)
- ✅ Documentation requirements (Form 4562)
- ✅ Audit defense (approval trail)
- ✅ Materiality thresholds (human judgment)

### Data Protection:
- ✅ Approval records: JSON format (not modifiable)
- ✅ Timestamps: ISO 8601 format (internationally recognized)
- ✅ Storage: Secure location with access controls
- ✅ Retention: 7 years minimum (IRS requirement)

---

## Troubleshooting

### Q: What if quality validation fails?
**A**: Fix the issues and re-run. Critical errors BLOCK the workflow. No override available.

### Q: Can I skip tax review?
**A**: No. Tax review ALWAYS requires human approval. This is for your protection.

### Q: What if I disagree with validation warnings?
**A**: You can approve with override, but document your reasoning in approval notes.

### Q: Can RPA run without approval?
**A**: Technically yes, but STRONGLY NOT RECOMMENDED for tax data. You're bypassing critical safety checks.

### Q: How long to keep approval records?
**A**: Minimum 7 years (IRS audit period). Recommend 10 years for safety.

### Q: Who should be the approver?
**A**: A licensed CPA or EA (Enrolled Agent) who understands tax depreciation rules.

---

## Example Scenarios

### Scenario 1: Perfect Quality Export
- ✅ Checkpoint 1: Auto-approved (no issues)
- ⚠️  Checkpoint 2: Human reviews and approves
- ✅ Checkpoint 3: Auto-approved (all checks pass)
- ✅ Final: Human signs off
- **Result**: RPA authorized in < 5 minutes

### Scenario 2: Export with Warnings
- ⚠️  Checkpoint 1: Warnings detected, human reviews
- ⚠️  Checkpoint 2: Human reviews tax calculations
- ✅ Checkpoint 3: Auto-approved
- ✅ Final: Human signs off with justification
- **Result**: RPA authorized with documented overrides

### Scenario 3: Export with Critical Errors
- ❌ Checkpoint 1: CRITICAL errors detected, BLOCKED
- **Result**: RPA NOT authorized, must fix and re-run

---

## Summary

The Human-in-the-Loop approval workflow provides:

✅ **Tax Compliance**: Professional oversight for IRC regulations
✅ **RPA Safety**: Multiple checkpoints before automation
✅ **Audit Trail**: Complete documentation for IRS review
✅ **Flexibility**: Interactive or programmatic workflows
✅ **Quality Assurance**: Automated validation + human judgment

**CRITICAL**: This is not optional for tax data. Always use the approval workflow before RPA automation.

---

## Files Reference

- **Module**: `fixed_asset_ai/logic/human_approval_workflow.py`
- **Demo**: `demo_human_in_the_loop.py`
- **Documentation**: `HUMAN_IN_THE_LOOP_WORKFLOW.md` (this file)

Run demo:
```bash
python demo_human_in_the_loop.py
```

For questions or support, contact your tax compliance team.
