# Advanced Usage - RPA Customization

## Programmatic Usage

### Basic RPA Automation

```python
from fixed_asset_ai.logic.rpa_fa_cs import run_fa_cs_automation
import pandas as pd

# Your FA CS formatted data
df = pd.DataFrame({
    "Asset ID": ["A-001", "A-002"],
    "Property Description": ["Laptop", "Desk"],
    "Cost/Basis": [1500, 800],
    "Date In Service": ["01/15/2024", "01/20/2024"],
    "Method": ["200DB", "200DB"],
    "Life": [5, 7],
    "Convention": ["HY", "HY"],
})

# Run automation
results = run_fa_cs_automation(df, preview_mode=True)

print(f"Processed: {results['processed']}")
print(f"Succeeded: {results['succeeded']}")
print(f"Failed: {results['failed']}")
```

### Full AI + RPA Workflow

```python
from fixed_asset_ai.logic.ai_rpa_orchestrator import run_ai_to_rpa_workflow
import pandas as pd

# Your classified assets
classified_df = pd.read_excel("classified_assets.xlsx")

# Run complete workflow
results = run_ai_to_rpa_workflow(
    classified_df=classified_df,
    tax_year=2024,
    strategy="Balanced (Bonus Only)",
    taxable_income=200000,
    preview_mode=False,
    auto_run_rpa=True,
)

if results["success"]:
    print("Workflow completed successfully!")
    print(f"Duration: {results['duration_seconds']:.1f}s")
else:
    print(f"Workflow failed: {results['error']}")
```

### Custom RPA Configuration

```python
from fixed_asset_ai.logic.rpa_fa_cs import RPAConfig, FARobotOrchestrator
import pandas as pd

# Create custom configuration
config = RPAConfig()
config.WAIT_AFTER_TYPING = 0.5      # Slower typing
config.WAIT_FOR_WINDOW = 3.0        # Wait longer for windows
config.MAX_RETRIES = 5              # More retries
config.SCREENSHOT_ON_ERROR = True   # Always capture errors

# Use custom config
orchestrator = FARobotOrchestrator(config)
orchestrator.initialize()

# Run with custom config
stats = orchestrator.run_automation(df, preview_mode=False)
```

### Resume Failed Automation

```python
from fixed_asset_ai.logic.rpa_fa_cs import FARobotOrchestrator
import pandas as pd

# Load your data
df = pd.read_excel("assets.xlsx")

# Initialize
orchestrator = FARobotOrchestrator()
orchestrator.initialize()

# First run (failed at asset 150)
stats = orchestrator.run_automation(df)

# Resume from last successful
if stats['failed'] > 0:
    print(f"Resuming from asset {stats['succeeded']}")
    resume_stats = orchestrator.resume_automation(df, stats['succeeded'] - 1)
```

## Custom Window Automation

### Detect Different FA CS Version

```python
from fixed_asset_ai.logic.rpa_fa_cs import FACSWindowManager, RPAConfig

config = RPAConfig()
config.FA_CS_WINDOW_TITLE = "Fixed Assets CS 2024"  # Different version

wm = FACSWindowManager(config)
connected = wm.connect_to_fa_cs()

if connected:
    print("Connected to FA CS!")
    wm.activate_window()
else:
    print("Connection failed")
```

### Custom Field Mapping

If your FA CS has different field order, customize tab counts:

```python
from fixed_asset_ai.logic.rpa_fa_cs import RPAConfig, FACSDataEntry, FACSWindowManager

config = RPAConfig()

# Customize field tab counts
config.FIELD_TAB_COUNTS = {
    "asset_id": 1,
    "description": 3,       # Different order
    "date_in_service": 2,   # Different order
    "cost": 4,
    "method": 5,
    "life": 6,
    "convention": 7,
}

wm = FACSWindowManager(config)
wm.connect_to_fa_cs()

entry = FACSDataEntry(wm)
# Now uses custom field mapping
```

## Batch Processing

### Process in Chunks

```python
from fixed_asset_ai.logic.rpa_fa_cs import FARobotOrchestrator
import pandas as pd

df = pd.read_excel("large_file.xlsx")  # 500 assets

orchestrator = FARobotOrchestrator()
orchestrator.initialize()

# Process in batches of 100
batch_size = 100
for i in range(0, len(df), batch_size):
    batch = df.iloc[i:i+batch_size]

    print(f"Processing batch {i//batch_size + 1}")
    stats = orchestrator.data_entry.process_dataframe(batch)

    print(f"  Succeeded: {stats['succeeded']}")
    print(f"  Failed: {stats['failed']}")

    # Brief pause between batches
    import time
    time.sleep(5)
```

### Parallel Processing (Multiple Clients)

```python
from concurrent.futures import ThreadPoolExecutor
from fixed_asset_ai.logic.rpa_fa_cs import run_fa_cs_automation
import pandas as pd

clients = {
    "Client A": "client_a_assets.xlsx",
    "Client B": "client_b_assets.xlsx",
    "Client C": "client_c_assets.xlsx",
}

def process_client(client_name, filename):
    df = pd.read_excel(filename)
    results = run_fa_cs_automation(df)
    return client_name, results

# Note: Only works if you can open multiple FA CS instances
# Otherwise, process sequentially
with ThreadPoolExecutor(max_workers=3) as executor:
    futures = [
        executor.submit(process_client, name, file)
        for name, file in clients.items()
    ]

    for future in futures:
        client, results = future.result()
        print(f"{client}: {results['succeeded']} succeeded")
```

## Error Handling

### Comprehensive Error Handling

```python
from fixed_asset_ai.logic.rpa_fa_cs import FARobotOrchestrator
import pandas as pd
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)

df = pd.read_excel("assets.xlsx")

orchestrator = FARobotOrchestrator()

try:
    # Initialize
    if not orchestrator.initialize():
        raise Exception("Failed to initialize RPA")

    # Run automation
    stats = orchestrator.run_automation(df, preview_mode=False)

    # Check results
    if stats['failed'] == 0:
        print(f"✓ All {stats['succeeded']} assets processed successfully")
    else:
        print(f"⚠️ Partial success: {stats['succeeded']} succeeded, {stats['failed']} failed")

        # Log errors
        for error in stats['errors']:
            logging.error(error)

        # Save failed assets for review
        failed_indices = []  # You'd need to track these in your implementation
        df.iloc[failed_indices].to_excel("failed_assets.xlsx", index=False)

except KeyboardInterrupt:
    print("Automation cancelled by user")
except Exception as e:
    logging.error(f"Automation error: {e}")
    # Take screenshot for debugging
    orchestrator.window_manager.take_screenshot("fatal_error")
```

### Retry Logic for Failed Assets

```python
from fixed_asset_ai.logic.rpa_fa_cs import FARobotOrchestrator
import pandas as pd
import time

df = pd.read_excel("assets.xlsx")

orchestrator = FARobotOrchestrator()
orchestrator.initialize()

max_attempts = 3
attempt = 1

while attempt <= max_attempts:
    print(f"\nAttempt {attempt}/{max_attempts}")

    stats = orchestrator.run_automation(df)

    if stats['failed'] == 0:
        print("✓ All assets processed successfully!")
        break

    print(f"Failed: {stats['failed']} assets")

    if attempt < max_attempts:
        print("Retrying failed assets in 10 seconds...")
        time.sleep(10)

        # Filter to only failed assets
        # (you'd need to track which ones failed)
        # df = df.iloc[failed_indices]

    attempt += 1
```

## Integration with Other Systems

### Export to Multiple Formats

```python
from fixed_asset_ai.logic.ai_rpa_orchestrator import AIRPAOrchestrator
import pandas as pd

orchestrator = AIRPAOrchestrator()

results = orchestrator.run_full_workflow(
    classified_df=df,
    tax_year=2024,
    strategy="Balanced (Bonus Only)",
    taxable_income=200000,
    auto_run_rpa=False,  # Don't run RPA, just prepare data
)

# The workflow creates a backup Excel file
excel_file = results['steps']['excel_export']['filename']

# Load and convert to other formats
df = pd.read_excel(excel_file)

# CSV for import to other systems
df.to_csv("fa_import.csv", index=False)

# JSON for APIs
df.to_json("fa_import.json", orient="records", indent=2)

# SQL insert statements
# ... custom export logic
```

### Webhook Notifications

```python
from fixed_asset_ai.logic.rpa_fa_cs import FARobotOrchestrator
import pandas as pd
import requests

df = pd.read_excel("assets.xlsx")

orchestrator = FARobotOrchestrator()
orchestrator.initialize()

# Run automation
stats = orchestrator.run_automation(df)

# Send notification
webhook_url = "https://your-webhook.com/notify"
payload = {
    "event": "rpa_complete",
    "processed": stats['processed'],
    "succeeded": stats['succeeded'],
    "failed": stats['failed'],
    "client": "Client Name",
}

try:
    response = requests.post(webhook_url, json=payload)
    response.raise_for_status()
except Exception as e:
    print(f"Webhook notification failed: {e}")
```

## Testing and Development

### Mock RPA for Testing

```python
# For testing AI classification without RPA
from fixed_asset_ai.logic.ai_rpa_orchestrator import AIRPAOrchestrator
import pandas as pd

orchestrator = AIRPAOrchestrator()

results = orchestrator.run_full_workflow(
    classified_df=df,
    tax_year=2024,
    strategy="Balanced (Bonus Only)",
    taxable_income=200000,
    preview_mode=True,      # Test mode
    auto_run_rpa=False,     # Skip RPA
)

# Review classification results without touching FA CS
```

### Screenshot Debugging

```python
from fixed_asset_ai.logic.rpa_fa_cs import FACSWindowManager

wm = FACSWindowManager()
wm.connect_to_fa_cs()

# Take screenshot at any point
wm.take_screenshot("before_entry")

# Do some automation...

wm.take_screenshot("after_entry")

# Compare screenshots to debug field mapping issues
```

## Performance Optimization

### Reduce AI API Calls with Rules

Add more rules to `logic/rules.json` to avoid GPT calls:

```json
{
  "rules": [
    {
      "class": "Computer Equipment",
      "life": 5,
      "method": "200DB",
      "convention": "HY",
      "keywords": ["computer", "laptop", "desktop", "server", "printer"],
      "exclude": ["desk", "chair"],
      "weight": 1.0
    },
    {
      "class": "Office Furniture",
      "life": 7,
      "method": "200DB",
      "convention": "HY",
      "keywords": ["desk", "chair", "table", "cabinet", "bookshelf"],
      "exclude": ["computer"],
      "weight": 1.0
    }
  ]
}
```

More rules = faster classification + lower OpenAI costs.

### Faster RPA with Adjusted Timing

```python
from fixed_asset_ai.logic.rpa_fa_cs import RPAConfig, FARobotOrchestrator

# For fast computers/fast FA CS
config = RPAConfig()
config.WAIT_AFTER_CLICK = 0.2       # Faster
config.WAIT_AFTER_TYPING = 0.1      # Faster
config.WAIT_FOR_WINDOW = 1.0        # Faster

# But test thoroughly first!
```

## Production Deployment

### Scheduled Automation

```python
# Use with cron or Windows Task Scheduler
import sys
from pathlib import Path
from datetime import datetime

# Add to path
sys.path.insert(0, str(Path(__file__).parent / "fixed_asset_ai"))

from logic.ai_rpa_orchestrator import run_ai_to_rpa_workflow
import pandas as pd

# Load from network location
df = pd.read_excel("//fileserver/shared/assets/daily_additions.xlsx")

# Run automation
results = run_ai_to_rpa_workflow(
    classified_df=df,
    tax_year=datetime.now().year,
    strategy="Balanced (Bonus Only)",
    taxable_income=200000,
    auto_run_rpa=True,
)

# Log results
with open("automation_log.txt", "a") as f:
    f.write(f"{datetime.now()}: {results}\n")
```

### Environment Variables for Configuration

```python
import os
from fixed_asset_ai.logic.rpa_fa_cs import RPAConfig

config = RPAConfig()

# Override from environment
config.FA_CS_PROCESS_NAME = os.getenv("FA_CS_PROCESS", "FAwin.exe")
config.MAX_RETRIES = int(os.getenv("RPA_MAX_RETRIES", "3"))
config.WAIT_AFTER_TYPING = float(os.getenv("RPA_TYPE_DELAY", "0.3"))

# Use in automation...
```

---

## Need More Customization?

The RPA modules are designed to be extensible:

- **logic/rpa_fa_cs.py**: Core RPA automation
- **logic/ai_rpa_orchestrator.py**: Workflow orchestration
- **rpa_config.json**: User-editable configuration

Modify as needed for your specific FA CS version or workflow requirements.
