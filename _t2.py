import sys, json
from base64 import b64encode
sys.path.insert(0, "src")
from starlette.testclient import TestClient
from itsdangerous import TimestampSigner
from src.app import app

signer = TimestampSigner("change-me-car-service-ai-secret")
cookie = signer.sign(b64encode(json.dumps({"user":"test@example.com","name":"Test","lang":"en"}).encode()).decode()).decode()
c = TestClient(app, raise_server_exceptions=False)
c.cookies.set("session", cookie)

# 1. Run diagnosis to get an ID
r = c.post("/api/diagnose/complete", json={
    "problem": "Car pulls to the right when braking at high speed",
    "answers": {"when": "When braking", "severity": "Moderate — noticeable while driving"},
    "image": None
})
data = r.json()
diag_id = data["result"]["id"]
print(f"1. Diagnosis created: {diag_id}")

# 2. Test diagnosis detail page
r2 = c.get(f"/diagnosis/{diag_id}")
print(f"2. /diagnosis/{diag_id}: {r2.status_code} ({len(r2.text)} bytes)")
checks_detail = ["Failing", "Front CV Joint" in r2.text or "brake" in r2.text.lower() or "pull" in r2.text.lower(),
                 "urgency", "confidence"]
for ch in checks_detail:
    if isinstance(ch, bool):
        print(f"   content match: {ch}")
    else:
        print(f"   '{ch}' present: {ch in r2.text}")

# 3. Test reports page
r3 = c.get("/reports")
print(f"3. /reports: {r3.status_code} ({len(r3.text)} bytes)")
print(f"   has diagnosis ID: {diag_id in r3.text}")

# 4. Test diagnosis print page
r4 = c.get(f"/diagnosis/{diag_id}/print")
print(f"4. /diagnosis/{diag_id}/print: {r4.status_code} ({len(r4.text)} bytes)")

# 5. Test wizard result link works in JS
r5 = c.get("/diagnose")
has_link = f"/diagnosis/{'DIA' if True else ''}" in r5.text
print(f"5. Wizard page has diagnosis link pattern: {'diagnosis/' in r5.text}")

print("\nALL CHECKS DONE")
