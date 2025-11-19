"""Tracking utilities for lint issues and remediation actions."""

from __future__ import annotations

from pydantic import BaseModel, Field

from scene_builder.validation.models import LintActionTaken, LintIssue, LintIssueTicket, LintReport


class IssueTracker(BaseModel):
    """Manages lint tickets and their associated actions across iterations."""

    tickets: dict[str, LintIssueTicket] = Field(default_factory=dict)
    actions: list[LintActionTaken] = Field(default_factory=list)

    def compute_issue_id(self, issue: LintIssue) -> str:
        """
        Create a simple, prototype-level ID for a lint issue, assuming only one issue of a
        given code can exist per object.
        """
        object_id = issue.object_id or "room"  # Use 'room' for room-level issues
        return f"{object_id}_{issue.code}"

    def sync(self, lint_report: LintReport) -> None:
        """Update the tracker with the latest lint report."""
        seen: set[str] = set()
        for issue in lint_report.issues:
            issue_id = self.compute_issue_id(issue)
            seen.add(issue_id)
            ticket = self.tickets.get(issue_id)
            if ticket is None:
                self.tickets[issue_id] = LintIssueTicket(
                    issue_id=issue_id,
                    object_id=issue.object_id,
                    code=issue.code,
                    message=issue.message,
                    hint=issue.hint,
                )
            else:
                ticket.status = "open"
                ticket.object_id = issue.object_id
                ticket.code = issue.code
                ticket.message = issue.message
                ticket.hint = issue.hint

        for issue_id, ticket in self.tickets.items():
            if issue_id not in seen:
                ticket.status = "resolved"

    def append_action(
        self,
        ticket: LintIssueTicket,
        summary: str,
        rationale: str,
    ) -> None:
        """Log an action taken for a ticket and persist it to the tracker."""
        action = LintActionTaken(
            issue_id=ticket.issue_id,
            object_id=ticket.object_id,
            summary=summary,
            rationale=rationale,
        )
        self.actions.append(action)
        ticket.actions.append(summary)

    def consume_feedback(self) -> str:
        """Compile any new actions or open issues into a message for the next agent."""
        lines: list[str] = []
        new_actions = [action for action in self.actions if not action.delivered]

        if new_actions:
            lines.append("Actions taken since last turn:")
            for action in new_actions:
                lines.append(
                    f"- [{action.issue_id}] {action.summary} (rationale: {action.rationale})"
                )
                action.delivered = True

        open_tickets = [ticket for ticket in self.tickets.values() if ticket.status == "open"]
        if open_tickets:
            lines.append("Outstanding lint issues:")
            for ticket in open_tickets:
                target = ticket.object_id or "room"
                lines.append(
                    f"- ({ticket.code}) {target}: {ticket.message} (retries: {ticket.retries})"
                )

        return "\n".join(lines)
