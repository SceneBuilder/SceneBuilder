"""Rule that detects objects whose origins sit below the floor."""

from __future__ import annotations

from collections.abc import Iterable

from scene_builder.lint.context import LintContext, LintingOptions
from scene_builder.lint.models import LintIssue, LintSeverity
from scene_builder.lint.rules.base import LintRule


class FloorOriginRule(LintRule):
    """Detect objects whose origins sit below the configured floor height."""

    code = "floor_overlap"
    description = "Object origin is below the configured floor height."

    def apply(self, context: LintContext, options: LintingOptions) -> Iterable[LintIssue]:
        floor = options.floor_height
        tolerance = options.floor_tolerance

        for lint_obj in context.objects:
            obj = lint_obj.object
            delta = floor - obj.position.z
            if delta <= tolerance:
                continue

            message = (
                f"Object {obj.id}'s origin is {delta:.3f} m below the floor height "
                f"({floor:.3f} m)."
            )
            hint = f"Translate {obj.id} upward (+z) by at least {delta:.3f} m."
            yield LintIssue(
                code=self.code,
                severity=LintSeverity.ERROR,
                object_id=obj.id,
                message=message,
                hint=hint,
                data={"origin_z": obj.position.z, "floor_height": floor, "delta": delta},
            )

