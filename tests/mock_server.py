"""
Mock API server for local development and testing.

Simulates external APIs (PagerDuty, Grafana, Datadog, Cortex, Slack)
without requiring real accounts or services.

Usage:
    python -m tests.mock_server

Then point NthLayer at http://localhost:8001 for all integrations.
"""

import json
import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException, Request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="NthLayer Mock API Server", version="1.0.0")

# In-memory state storage
STATE: dict[str, dict[str, Any]] = {
    "pagerduty_teams": {},
    "pagerduty_users": {},
    "grafana_dashboards": {},
    "datadog_monitors": {},
    "cortex_teams": {},
    "slack_messages": [],
}


# ============================================================================
# PagerDuty Mock API
# ============================================================================


@app.get("/pagerduty/teams/{team_id}")
async def pd_get_team(team_id: str, authorization: str = Header(None)):
    """Get PagerDuty team details"""
    logger.info(f"[PagerDuty] GET /teams/{team_id}")
    
    if team_id not in STATE["pagerduty_teams"]:
        # Return a default team
        team = {
            "id": team_id,
            "name": f"Team {team_id}",
            "description": "Mock team from NthLayer dev server",
        }
        STATE["pagerduty_teams"][team_id] = team
    
    return {"team": STATE["pagerduty_teams"][team_id]}


@app.get("/pagerduty/teams/{team_id}/members")
async def pd_get_team_members(team_id: str, authorization: str = Header(None)):
    """Get PagerDuty team members"""
    logger.info(f"[PagerDuty] GET /teams/{team_id}/members")
    
    members = STATE["pagerduty_teams"].get(team_id, {}).get("members", [])
    return {"members": members}


@app.post("/pagerduty/teams/{team_id}/users")
async def pd_set_team_members(
    team_id: str,
    request: Request,
    authorization: str = Header(None),
    idempotency_key: str = Header(None, alias="Idempotency-Key"),
):
    """Set PagerDuty team members (idempotent)"""
    body = await request.json()
    logger.info(f"[PagerDuty] POST /teams/{team_id}/users (idempotency_key={idempotency_key})")
    logger.info(f"  Body: {json.dumps(body, indent=2)}")
    
    if team_id not in STATE["pagerduty_teams"]:
        STATE["pagerduty_teams"][team_id] = {"id": team_id, "members": []}
    
    STATE["pagerduty_teams"][team_id]["members"] = body.get("members", [])
    
    return {"status": "success", "team_id": team_id}


@app.get("/pagerduty/escalation_policies")
async def pd_list_escalation_policies(authorization: str = Header(None)):
    """List PagerDuty escalation policies"""
    logger.info("[PagerDuty] GET /escalation_policies")
    
    return {
        "escalation_policies": [
            {
                "id": "POLICY1",
                "name": "Default Escalation",
                "escalation_rules": [
                    {"escalation_delay_in_minutes": 30, "targets": [{"type": "user"}]}
                ],
            }
        ]
    }


# ============================================================================
# Grafana Mock API
# ============================================================================


@app.get("/grafana/api/dashboards/uid/{uid}")
async def grafana_get_dashboard(uid: str, authorization: str = Header(None)):
    """Get Grafana dashboard by UID"""
    logger.info(f"[Grafana] GET /api/dashboards/uid/{uid}")
    
    if uid not in STATE["grafana_dashboards"]:
        raise HTTPException(status_code=404, detail="Dashboard not found")
    
    return {"dashboard": STATE["grafana_dashboards"][uid]}


@app.post("/grafana/api/dashboards/db")
async def grafana_create_dashboard(request: Request, authorization: str = Header(None)):
    """Create Grafana dashboard"""
    body = await request.json()
    logger.info("[Grafana] POST /api/dashboards/db")
    logger.info(f"  Title: {body.get('dashboard', {}).get('title')}")
    
    uid = body.get("dashboard", {}).get("uid", str(uuid4())[:8])
    STATE["grafana_dashboards"][uid] = body.get("dashboard", {})
    
    return {
        "status": "success",
        "uid": uid,
        "url": f"/d/{uid}",
        "version": 1,
    }


@app.get("/grafana/api/folders")
async def grafana_list_folders(authorization: str = Header(None)):
    """List Grafana folders"""
    logger.info("[Grafana] GET /api/folders")
    
    return [
        {"id": 1, "uid": "general", "title": "General"},
        {"id": 2, "uid": "nthlayer", "title": "NthLayer Dashboards"},
    ]


# ============================================================================
# Datadog Mock API
# ============================================================================


@app.get("/datadog/api/v1/monitor")
async def datadog_list_monitors(authorization: str = Header(None)):
    """List Datadog monitors"""
    logger.info("[Datadog] GET /api/v1/monitor")
    
    monitors = list(STATE["datadog_monitors"].values())
    return {"monitors": monitors}


@app.post("/datadog/api/v1/monitor")
async def datadog_create_monitor(request: Request, authorization: str = Header(None)):
    """Create Datadog monitor"""
    body = await request.json()
    logger.info("[Datadog] POST /api/v1/monitor")
    logger.info(f"  Name: {body.get('name')}")
    logger.info(f"  Query: {body.get('query')}")
    
    monitor_id = len(STATE["datadog_monitors"]) + 1
    monitor = {
        "id": monitor_id,
        "name": body.get("name"),
        "type": body.get("type", "metric alert"),
        "query": body.get("query"),
        "message": body.get("message"),
        "tags": body.get("tags", []),
        "created": datetime.utcnow().isoformat(),
    }
    STATE["datadog_monitors"][monitor_id] = monitor
    
    return monitor


@app.put("/datadog/api/v1/monitor/{monitor_id}")
async def datadog_update_monitor(
    monitor_id: int, request: Request, authorization: str = Header(None)
):
    """Update Datadog monitor"""
    body = await request.json()
    logger.info(f"[Datadog] PUT /api/v1/monitor/{monitor_id}")
    
    if monitor_id not in STATE["datadog_monitors"]:
        raise HTTPException(status_code=404, detail="Monitor not found")
    
    STATE["datadog_monitors"][monitor_id].update(body)
    return STATE["datadog_monitors"][monitor_id]


# ============================================================================
# Cortex Mock API
# ============================================================================


@app.get("/cortex/api/teams/{team_id}")
async def cortex_get_team(team_id: str, authorization: str = Header(None)):
    """Get Cortex team"""
    logger.info(f"[Cortex] GET /api/teams/{team_id}")
    
    if team_id not in STATE["cortex_teams"]:
        # Return default team
        team = {
            "id": team_id,
            "name": f"Team {team_id}",
            "members": [
                {"email": f"user1@{team_id}.example.com", "role": "owner"},
                {"email": f"user2@{team_id}.example.com", "role": "member"},
            ],
        }
        STATE["cortex_teams"][team_id] = team
    
    return STATE["cortex_teams"][team_id]


@app.get("/cortex/api/catalog")
async def cortex_list_services(authorization: str = Header(None)):
    """List Cortex services"""
    logger.info("[Cortex] GET /api/catalog")
    
    return {
        "services": [
            {
                "tag": "search-api",
                "name": "Search API",
                "tier": 1,
                "owner": "team-platform",
                "description": "Core search service",
            },
            {
                "tag": "user-service",
                "name": "User Service",
                "tier": 2,
                "owner": "team-identity",
                "description": "User management",
            },
        ]
    }


# ============================================================================
# Slack Mock API
# ============================================================================


@app.post("/slack/chat.postMessage")
async def slack_post_message(request: Request, authorization: str = Header(None)):
    """Post Slack message"""
    body = await request.json()
    logger.info("[Slack] POST /chat.postMessage")
    logger.info(f"  Channel: {body.get('channel')}")
    logger.info(f"  Text: {body.get('text', '')[:100]}...")
    
    message = {
        "ts": str(datetime.utcnow().timestamp()),
        "channel": body.get("channel"),
        "text": body.get("text"),
        "created_at": datetime.utcnow().isoformat(),
    }
    STATE["slack_messages"].append(message)
    
    return {"ok": True, "ts": message["ts"], "channel": message["channel"]}


# ============================================================================
# Admin/Debug Endpoints
# ============================================================================


@app.get("/")
async def root():
    """Root endpoint with API info"""
    return {
        "service": "NthLayer Mock API Server",
        "version": "1.0.0",
        "endpoints": {
            "pagerduty": "http://localhost:8001/pagerduty",
            "grafana": "http://localhost:8001/grafana",
            "datadog": "http://localhost:8001/datadog",
            "cortex": "http://localhost:8001/cortex",
            "slack": "http://localhost:8001/slack",
        },
        "state": "/state",
        "reset": "/reset (POST)",
    }


@app.get("/state")
async def get_state():
    """Get current mock server state"""
    return {
        "pagerduty_teams": len(STATE["pagerduty_teams"]),
        "grafana_dashboards": len(STATE["grafana_dashboards"]),
        "datadog_monitors": len(STATE["datadog_monitors"]),
        "cortex_teams": len(STATE["cortex_teams"]),
        "slack_messages": len(STATE["slack_messages"]),
        "details": STATE,
    }


@app.post("/reset")
async def reset_state():
    """Reset all mock server state"""
    logger.info("[Admin] Resetting all state")
    for key in STATE:
        if isinstance(STATE[key], list):
            STATE[key] = []
        else:
            STATE[key] = {}
    return {"status": "reset", "message": "All state cleared"}


@app.get("/health")
async def health():
    """Health check"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    
    print("=" * 70)
    print("🚀 NthLayer Mock API Server")
    print("=" * 70)
    print()
    print("Running on: http://localhost:8001")
    print()
    print("Available APIs:")
    print("  • PagerDuty:  http://localhost:8001/pagerduty")
    print("  • Grafana:    http://localhost:8001/grafana")
    print("  • Datadog:    http://localhost:8001/datadog")
    print("  • Cortex:     http://localhost:8001/cortex")
    print("  • Slack:      http://localhost:8001/slack")
    print()
    print("Admin endpoints:")
    print("  • State:      http://localhost:8001/state")
    print("  • Reset:      POST http://localhost:8001/reset")
    print("  • Health:     http://localhost:8001/health")
    print()
    print("Update your .env to point at mock server:")
    print("  NTHLAYER_PAGERDUTY_BASE_URL=http://localhost:8001/pagerduty")
    print("  NTHLAYER_GRAFANA_BASE_URL=http://localhost:8001/grafana")
    print("  NTHLAYER_CORTEX_BASE_URL=http://localhost:8001/cortex")
    print()
    print("=" * 70)
    print()
    
    uvicorn.run(app, host="0.0.0.0", port=8001, log_level="info")
