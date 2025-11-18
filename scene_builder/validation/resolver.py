"""Agent-backed lint issue resolution helpers."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from rich.console import Console

from scene_builder.decoder.blender import blender
from scene_builder.utils.pai import transform_paths_to_binary
from scene_builder.validation.heuristics import HEURISTIC_RESOLVERS
from scene_builder.validation.models import (
    IssueResolutionOutput,
    LintIssue,
    LintIssueTicket,
)
from scene_builder.validation.tracker import IssueTracker
from scene_builder.workflow.agents import issue_resolution_agent
from scene_builder.workflow.states import RoomDesignState


logger = logging.getLogger(__name__)


class IssueResolver:
    """Runs automatic lint resolution without mutating the room state."""

    def __init__(
        self,
        state: RoomDesignState,
        *,
        max_attempts: int = 3,
        console: Console | None = None,
    ) -> None:
        self.state = state
        self.max_attempts = max_attempts
        self.console = console

    async def attempt_auto_resolution(
        self,
        tracker: IssueTracker,
        issue_lookup: dict[str, LintIssue],
    ) -> list[IssueResolutionOutput]:
        """Attempt to resolve all open tickets once and return proposed actions."""
        tickets_to_resolve = [
            ticket
            for ticket in tracker.tickets.values()
            if ticket.status == "open" and ticket.retries < self.max_attempts
        ]

        if not tickets_to_resolve:
            return []

        if self.console:
            self.console.print(
                f"[bold yellow]Attempting to auto-resolve {len(tickets_to_resolve)} lint issues...[/]"
            )

        results: list[IssueResolutionOutput] = []
        for ticket in tickets_to_resolve:
            issue = issue_lookup.get(ticket.issue_id)
            if issue is None:
                continue

            result = await self._resolve_ticket(tracker, ticket, issue)
            if result is not None:
                results.append(result)

        return results

    async def _resolve_ticket(
        self,
        tracker: IssueTracker,
        ticket: LintIssueTicket,
        issue: LintIssue,
    ) -> IssueResolutionOutput | None:
        """Invoke a heuristic or agent to resolve a single ticket and return the proposed action."""
        ticket.retries += 1
        object_state_json = None
        if ticket.object_id:
            target = next(
                (obj for obj in (self.state.room.objects or []) if obj.id == ticket.object_id),
                None,
            )
            if target is not None:
                object_state_json = target.model_dump_json(indent=2)

        heuristic = HEURISTIC_RESOLVERS.get(issue.code)
        if heuristic is not None:
            result = heuristic(self.state, ticket, issue)
            if result is not None:
                if result.object_id:
                    ticket.object_id = result.object_id
                ticket.status = "resolved"
                tracker.append_action(ticket, result.action_desc, result.rationale)
                result.ticket_id = ticket.issue_id
                return result

        prompt_parts = [
            "Resolve the following lint issue in the 3D room design.",
            f"Room id: {self.state.room.id}",
            f"Issue code: {issue.code}",
            f"Issue message: {issue.message}",
        ]
        if issue.hint:
            prompt_parts.append(f"Hint: {issue.hint}")
        prompt_parts.append(f"Attempts so far: {ticket.retries - 1}")
        visuals = self._render_issue_visuals(issue)
        if object_state_json:
            prompt_parts.append("Current object state:")
            prompt_parts.append(f"```json\n{object_state_json}\n```")
        else:
            prompt_parts.append("The issue applies to the overall room context.")
        if visuals:
            prompt_parts.append("Relevant visuals:")
            prompt_parts.extend(visuals)
        if ticket.actions:
            prompt_parts.append("Recent actions:")
            prompt_parts.extend(f"- {action}" for action in ticket.actions[-3:])
        prompt_parts.extend(
            [
                "Respond with JSON that matches the IssueResolutionOutput schema:",
                '{"resolved": bool, "action_desc": str, "rationale": str,',
                ' "object_id": str | null, "adjustment": {',
                '   "id": str | null, "position": Vector3 | null,',
                '   "rotation": Vector3 | null, "scale": Vector3 | null,',
                '   "remove": bool',
                " }}",
            ]
        )

        response = await issue_resolution_agent.run(
            tuple(prompt_parts),
            output_type=IssueResolutionOutput,
        )
        result = response.output
        if result.object_id:
            ticket.object_id = result.object_id
        if result.resolved:
            ticket.status = "resolved"

        tracker.append_action(ticket, result.action_desc, result.rationale)

        # Check if agent spoofed an arbitrary `ticket_id`
        if result.ticket_id and result.ticket_id != ticket.issue_id:
            logger.warning(
                "Issue resolver received mismatched ticket_id from agent (agent=%s, tracker=%s)",
                result.ticket_id,
                ticket.issue_id,
            )
        # Ensure the ticket_id is supplied by us, not the agent.
        result.ticket_id = ticket.issue_id

        return result

    def _render_issue_visuals(self, issue: LintIssue) -> list[object]:
        """
        Render object-focused visuals (optionally with augmentations) to guide the resolver.
        Returns a list of BinaryContent or similar media-friendly payloads.
        """
        object_id = issue.object_id
        if object_id is None:
            return []

        targets = [oid for oid in re.split(r"[;,\s]+", object_id) if oid]
        output_dir = Path("test_output/auto_resolver") / self.state.room.id
        output_dir.mkdir(parents=True, exist_ok=True)
        augmentations = issue.data.get("requested_augmentations") if issue.data else None
        augmentations += ["highlight", "show_id"]  # DEBUG?

        # blender.parse_room_definition(self.state.room, with_walls="translucent")
        render_path = blender.create_object_visualization(
            scene=self.state.room.id,
            output_dir=str(output_dir),
            target_objects=targets,
            augmentations=augmentations or [],
            view="egocentric",
            show_grid=True,
        )

        if render_path is None:
            return []

        return transform_paths_to_binary([render_path])
