"""Rule that detects footprints intersecting room boundaries."""

from __future__ import annotations

from collections.abc import Iterable

from scene_builder.validation.context import LintContext, LintingOptions
from scene_builder.validation.models import LintIssue, LintSeverity
from scene_builder.validation.rules.base import LintRule


class WallOverlapRule(LintRule):
    """Detect footprints that intersect the room boundary."""

    code = "wall_overlap"
    description = "Object footprint intersects the room boundary."

    def apply(self, context: LintContext, options: LintingOptions) -> Iterable[LintIssue]:
        polygon = context.room.footprint

        boundary_payload = (
            [{"x": vertex.x, "y": vertex.y} for vertex in context.room.definition.boundary]
            if context.room.definition.boundary
            else None
        )

        for lint_obj in context.objects:
            footprint = lint_obj.footprint
            inside = polygon.contains(footprint)
            clearance = options.wall_clearance
            distance_to_boundary = polygon.boundary.distance(footprint)
            if inside and (clearance <= 0.0 or distance_to_boundary >= clearance):
                continue

            message = f"Object {lint_obj.id}'s footprint intersects the room boundary by {distance_to_boundary:.3f} m."
            hint = f"Move {lint_obj.id} inward by {(distance_to_boundary):.3f} m."
            min_x, min_y, max_x, max_y = lint_obj.footprint.bounds
            data: dict[str, object] = {
                "footprint_bounds": (min_x, min_y, max_x, max_y),
                "wall_clearance": clearance,
                "min_distance": distance_to_boundary,
            }
            if boundary_payload is not None:
                data["room_boundary"] = boundary_payload

            yield LintIssue(
                code=self.code,
                severity=LintSeverity.WARNING,
                object_id=lint_obj.id,
                message=message,
                hint=hint,
                data=data,
            )
