from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypedDict

import structlog
from langgraph.graph import END, StateGraph

from nthlayer.clients import CortexClient, SlackNotifier
from nthlayer.db.repositories import RunRepository
from nthlayer.domain.models import Finding
from nthlayer.providers.pagerduty import PagerDutyProvider

logger = structlog.get_logger()


class TeamReconcileState(TypedDict, total=False):
    job_id: str
    team_id: str
    desired: dict[str, Any] | None
    cortex_team: dict[str, Any] | None
    pagerduty_team: dict[str, Any] | None
    diff: dict[str, list[str]]
    target_memberships: list[dict[str, Any]]
    applied: bool
    requested_by: str | None
    slack_channel: str | None
    outcome: str | None


@dataclass(slots=True)
class TeamReconcileWorkflow:
    cortex: CortexClient
    pagerduty: PagerDutyProvider
    slack: SlackNotifier
    repository: RunRepository
    _graph: Any = field(init=False)

    def __post_init__(self) -> None:
        graph = StateGraph(TeamReconcileState)
        graph.add_node("fetch_cortex", self._fetch_cortex)
        graph.add_node("fetch_pagerduty", self._fetch_pagerduty)
        graph.add_node("compute_diff", self._compute_diff)
        graph.add_node("apply_diff", self._apply_diff)
        graph.add_node("notify", self._notify)

        graph.set_entry_point("fetch_cortex")
        graph.add_edge("fetch_cortex", "fetch_pagerduty")
        graph.add_edge("fetch_pagerduty", "compute_diff")
        
        graph.add_conditional_edges(
            "compute_diff",
            self._should_apply,
            {
                "apply": "apply_diff",
                "skip": "notify",
            },
        )
        
        graph.add_edge("apply_diff", "notify")
        graph.add_edge("notify", END)

        self._graph = graph.compile()

    def _should_apply(self, state: TeamReconcileState) -> str:
        """Determine if diff should be applied."""
        diff = state.get("diff", {})
        has_changes = bool(diff.get("add") or diff.get("remove"))
        return "apply" if has_changes else "skip"

    async def run(self, state: TeamReconcileState) -> TeamReconcileState:
        return await self._graph.ainvoke(state)

    async def _fetch_cortex(self, state: TeamReconcileState) -> TeamReconcileState:
        team_id = state["team_id"]
        job_id = state["job_id"]
        logger.info("fetching_cortex_team", job_id=job_id, team_id=team_id)
        try:
            cortex_team = await self.cortex.get_team(team_id)
            logger.info("cortex_team_fetched", job_id=job_id, team_id=team_id)
        except Exception as exc:
            logger.error("cortex_fetch_failed", job_id=job_id, team_id=team_id, error=str(exc))
            cortex_team = None
        return state | {"cortex_team": cortex_team}

    async def _fetch_pagerduty(self, state: TeamReconcileState) -> TeamReconcileState:
        team_id = state["team_id"]
        job_id = state["job_id"]
        logger.info("fetching_pagerduty_team", job_id=job_id, team_id=team_id)
        pagerduty_team = await self.pagerduty.get_team(team_id)
        members = await self.pagerduty.get_team_members(team_id)
        pagerduty_team["members"] = members
        logger.info("pagerduty_team_fetched", job_id=job_id, team_id=team_id, member_count=len(members))
        return state | {"pagerduty_team": pagerduty_team}

    async def _compute_diff(self, state: TeamReconcileState) -> TeamReconcileState:
        job_id = state["job_id"]
        desired = state.get("desired") or (state.get("cortex_team") or {})
        desired_manager_ids = {str(m) for m in (desired.get("managers") or [])}

        pagerduty_team = state.get("pagerduty_team") or {}
        members = pagerduty_team.get("members", [])
        current_manager_ids = {member["user"]["id"] for member in members if member.get("user")}

        to_add = sorted(desired_manager_ids - current_manager_ids)
        to_remove = sorted(current_manager_ids - desired_manager_ids)
        diff = {"add": to_add, "remove": to_remove}
        desired_memberships = [
            {"user": {"id": identifier}, "role": "manager"}
            for identifier in sorted(desired_manager_ids)
        ]
        
        logger.info(
            "diff_computed",
            job_id=job_id,
            to_add=len(to_add),
            to_remove=len(to_remove),
        )
        return state | {"diff": diff, "target_memberships": desired_memberships}

    async def _apply_diff(self, state: TeamReconcileState) -> TeamReconcileState:
        diff = state.get("diff", {})
        team_id = state["team_id"]
        job_id = state["job_id"]
        memberships = state.get("target_memberships", [])
        
        logger.info("applying_diff", job_id=job_id, team_id=team_id)
        
        if diff.get("add") or diff.get("remove"):
            idempotency_key = f"{job_id}:{team_id}:members"
            
            await self.pagerduty.set_team_members(
                team_id,
                memberships,
                idempotency_key=idempotency_key,
            )
            
            await self.repository.record_finding(
                Finding(
                    run_id=job_id,
                    entity_ref=f"pagerduty:team:{team_id}",
                    before=state.get("pagerduty_team"),
                    after={"managers": [member["user"]["id"] for member in memberships]},
                    action="sync_team_members",
                    api_calls=[{"name": "set_team_members", "count": len(memberships)}],
                    outcome="applied",
                )
            )
            await self.repository.session.commit()
            logger.info("diff_applied", job_id=job_id, team_id=team_id, changes=len(memberships))
            applied = True
        else:
            applied = False
        return state | {"applied": applied}

    async def _notify(self, state: TeamReconcileState) -> TeamReconcileState:
        channel = state.get("slack_channel")
        if channel:
            summary = self._format_summary(state)
            await self.slack.post_message(channel, summary)
        return state | {"outcome": "applied" if state.get("applied") else "noop"}

    @staticmethod
    def _format_summary(state: TeamReconcileState) -> str:
        team_id = state["team_id"]
        diff = state.get("diff", {})
        added = ", ".join(diff.get("add", [])) or "none"
        removed = ", ".join(diff.get("remove", [])) or "none"
        return f"NthLayer reconciled PagerDuty team {team_id}. added={added} removed={removed}"
