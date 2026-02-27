#!/usr/bin/env python3
"""Test creating a schedule in PagerDuty."""

import os
import sys
from datetime import datetime, timezone

from pagerduty import RestApiV2Client

api_key = os.environ.get("PAGERDUTY_API_KEY")
if not api_key:
    print("Error: PAGERDUTY_API_KEY not set")
    sys.exit(1)

default_from = os.environ.get("PAGERDUTY_FROM_EMAIL", "test@example.com")
print(f"Using From email: {default_from}")

client = RestApiV2Client(api_key, default_from=default_from)

# First, get a user ID (required for schedule)
print("\n1. Getting users...")
response = client.get("/users")
users = response.json().get("users", [])
if not users:
    print("   No users found! Need at least one user for schedule.")
    sys.exit(1)

user_id = users[0]["id"]
user_email = users[0]["email"]
print(f"   Found user: {user_email} (id: {user_id})")

# Try creating a schedule
print("\n2. Creating test schedule...")
now = datetime.now(tz=timezone.utc)
start_time = now.replace(hour=9, minute=0, second=0, microsecond=0)

schedule_payload = {
    "schedule": {
        "name": "nthlayer-test-schedule",
        "type": "schedule",
        "time_zone": "America/New_York",
        "description": "Test schedule created by NthLayer",
        "schedule_layers": [
            {
                "name": "Primary Layer",
                "start": start_time.isoformat(),
                "rotation_virtual_start": start_time.isoformat(),
                "rotation_turn_length_seconds": 604800,  # 1 week
                "users": [{"user": {"id": user_id, "type": "user_reference"}}],
            }
        ],
    }
}

print(f"   Payload: {schedule_payload}")

try:
    response = client.post("/schedules", json=schedule_payload)
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.text[:500]}")

    if response.status_code in (200, 201):
        data = response.json()
        schedule_id = data["schedule"]["id"]
        print(f"\n   ✅ Created schedule: {schedule_id}")

        # Clean up - delete the test schedule
        print("\n3. Cleaning up - deleting test schedule...")
        del_response = client.delete(f"/schedules/{schedule_id}")
        print(f"   Delete status: {del_response.status_code}")
except Exception as e:
    print(f"   Error: {e}")
    sys.exit(1)

print("\nDone!")
