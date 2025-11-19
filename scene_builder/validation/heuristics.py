"""Deterministic (non-agent) lint resolution helpers."""

from __future__ import annotations

from collections.abc import Callable

from scene_builder.definition.scene import Vector3
from scene_builder.validation.models import (
    IssueResolutionOutput,
    LintIssue,
    LintIssueTicket,
    ObjectAdjustment,
)
from scene_builder.workflow.states import RoomDesignState


def resolve_floor_penetration(
    state: RoomDesignState,
    ticket: LintIssueTicket,
    issue: LintIssue,
) -> IssueResolutionOutput | None:
    """Deterministic fix: raise the object by the reported penetration depth."""
    obj_id = issue.object_id
    if obj_id is None:
        return None

    obj = next((item for item in (state.room.objects or []) if item.id == obj_id), None)
    if obj is None:
        return None

    data = issue.data or {}
    penetration = data.get("penetration")
    if penetration is None:
        bottom = data.get("bottom")
        floor_height = data.get("floor_height")
        if bottom is None or floor_height is None:
            return None
        penetration = float(floor_height) - float(bottom)

    if penetration <= 0.0:
        return None

    dz = float(penetration)
    new_position = Vector3(
        x=obj.position.x,
        y=obj.position.y,
        z=obj.position.z + dz,
    )

    return IssueResolutionOutput(
        resolved=True,
        action_desc=f"Raise {obj.id} by {dz:.3f} m to clear floor penetration",
        rationale="Deterministic floor-penetration fix from lint data (no margin).",
        object_id=obj.id,
        adjustment=ObjectAdjustment(id=obj.id, position=new_position),
    )


HEURISTIC_RESOLVERS: dict[str, Callable] = {
    "floor_penetration": resolve_floor_penetration,
}
