import urllib.request
import urllib.parse
import json
import pandas as pd
import io
import mimetypes

# Create a dummy Excel file with some assets
data = [
    ["Asset ID", "Description", "Cost", "Acquisition Date", "In Service Date"],
    ["A001", "Dell Optiplex 7090", 1200.00, "2023-01-15", "2023-01-15"],
    ["A002", "Herman Miller Aeron Chair", 850.00, "2023-02-01", "2023-02-01"],
    ["A003", "Ford F-150 Truck", 45000.00, "2023-03-10", "2023-03-10"],
    ["A004", "Office Renovation - Painting", 5000.00, "2023-04-01", "2023-04-01"]
]

df = pd.DataFrame(data[1:], columns=data[0])
output = io.BytesIO()
with pd.ExcelWriter(output, engine='openpyxl') as writer:
    df.to_excel(writer, index=False, sheet_name="Assets")
file_content = output.getvalue()

# Prepare multipart request manually (since no requests lib)
boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
body = []
body.append(f'--{boundary}'.encode())
body.append(f'Content-Disposition: form-data; name="file"; filename="test_assets.xlsx"'.encode())
body.append('Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'.encode())
body.append(b'')
body.append(file_content)
body.append(f'--{boundary}--'.encode())
body.append(b'')
body = b'\r\n'.join(body)

req = urllib.request.Request("http://127.0.0.1:8000/upload", data=body)
req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')

print(f"Sending request to http://127.0.0.1:8000/upload...")
try:
    with urllib.request.urlopen(req) as response:
        print(f"Status Code: {response.getcode()}")
        resp_body = response.read().decode('utf-8')
        assets = json.loads(resp_body)
        print(f"Response: {len(assets)} assets processed")
        for asset in assets:
            print(f"  - {asset.get('description')}: {asset.get('macrs_class')} ({asset.get('macrs_life')} yrs) - {asset.get('macrs_method')}/{asset.get('macrs_convention')}")
except urllib.error.HTTPError as e:
    print(f"HTTP Error: {e.code} {e.reason}")
    print(e.read().decode('utf-8'))
except Exception as e:
    print(f"Error: {e}")
