"""Rule that detects footprints dominating the room area."""

from __future__ import annotations

from collections.abc import Iterable

from scene_builder.validation.context import LintContext, LintingOptions
from scene_builder.validation.models import LintIssue, LintSeverity
from scene_builder.validation.rules.base import LintRule


class DominatesRoomRule(LintRule):
    """Detect objects that dominate the room's walkable area."""

    code = "dominates_room"
    description = "Object footprint dominates the room area."

    def apply(self, context: LintContext, options: LintingOptions) -> Iterable[LintIssue]:
        room_area = context.room.area
        if room_area <= 0.0:
            return []

        threshold = 0.6 * room_area
        for lint_obj in context.objects:
            area = lint_obj.footprint_area
            if area <= threshold:
                continue

            coverage = area / room_area
            message = (
                f"Object {lint_obj.id} covers {coverage:.0%} of the room's area, which may "
                "limit walkable space."
            )
            hint = f"Consider a smaller asset or reposition {lint_obj.id} to free space."
            yield LintIssue(
                code=self.code,
                severity=LintSeverity.HINT,
                object_id=lint_obj.id,
                message=message,
                hint=hint,
                data={
                    "footprint_area": area,
                    "room_area": room_area,
                    "coverage": coverage,
                },
            )

