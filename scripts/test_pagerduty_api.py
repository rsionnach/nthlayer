#!/usr/bin/env python3
"""Quick test script to debug PagerDuty API access."""

import os
import sys

try:
    from pagerduty import RestApiV2Client
except ImportError:
    print("Error: pagerduty package not installed")
    print("Run: pip install pagerduty")
    sys.exit(1)

# Check for API key
api_key = os.environ.get("PAGERDUTY_API_KEY")
if not api_key:
    print("Error: PAGERDUTY_API_KEY environment variable not set")
    sys.exit(1)

print(f"API Key: {api_key[:8]}...{api_key[-4:]}")
print()

# Initialize client
default_from = os.environ.get("PAGERDUTY_FROM_EMAIL", "test@example.com")
client = RestApiV2Client(api_key, default_from=default_from)

print("Testing API endpoints...")
print()

# Test 1: List abilities (basic API test)
print("1. Testing /abilities (basic auth test)...")
try:
    response = client.get("/abilities")
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        abilities = response.json().get("abilities", [])
        print(f"   Abilities: {len(abilities)} available")
        print(f"   Sample: {abilities[:5]}")
except Exception as e:
    print(f"   Error: {e}")

print()

# Test 2: List users
print("2. Testing /users...")
try:
    response = client.get("/users")
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        users = response.json().get("users", [])
        print(f"   Users: {len(users)} found")
        for user in users[:3]:
            print(f"   - {user['name']} ({user['email']})")
except Exception as e:
    print(f"   Error: {e}")

print()

# Test 3: List teams
print("3. Testing /teams...")
try:
    response = client.get("/teams")
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        teams = response.json().get("teams", [])
        print(f"   Teams: {len(teams)} found")
        for team in teams[:3]:
            print(f"   - {team['name']} (id: {team['id']})")
except Exception as e:
    print(f"   Error: {e}")

print()

# Test 4: List schedules
print("4. Testing /schedules...")
try:
    response = client.get("/schedules")
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        schedules = response.json().get("schedules", [])
        print(f"   Schedules: {len(schedules)} found")
        for schedule in schedules[:3]:
            print(f"   - {schedule['name']} (id: {schedule['id']})")
    elif response.status_code == 404:
        print(f"   Response body: {response.text[:500]}")
except Exception as e:
    print(f"   Error: {e}")

print()

# Test 5: List escalation policies
print("5. Testing /escalation_policies...")
try:
    response = client.get("/escalation_policies")
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        policies = response.json().get("escalation_policies", [])
        print(f"   Policies: {len(policies)} found")
        for policy in policies[:3]:
            print(f"   - {policy['name']} (id: {policy['id']})")
except Exception as e:
    print(f"   Error: {e}")

print()

# Test 6: List services
print("6. Testing /services...")
try:
    response = client.get("/services")
    print(f"   Status: {response.status_code}")
    if response.status_code == 200:
        services = response.json().get("services", [])
        print(f"   Services: {len(services)} found")
        for service in services[:3]:
            print(f"   - {service['name']} (id: {service['id']})")
except Exception as e:
    print(f"   Error: {e}")

print()
print("Done!")
