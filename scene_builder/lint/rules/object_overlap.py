"""Rule that detects object-object overlaps on the floor plane."""

from __future__ import annotations

from collections.abc import Iterable
from itertools import combinations

from scene_builder.lint.context import LintContext, LintingOptions
from scene_builder.lint.models import LintIssue, LintSeverity
from scene_builder.lint.rules.base import LintRule


class ObjectOverlapRule(LintRule):
    """Detect object-object overlaps on the floor plane."""

    code = "object_overlap"
    description = "Two objects overlap on the floor plane."

    def apply(self, context: LintContext, options: LintingOptions) -> Iterable[LintIssue]:
        issues: list[LintIssue] = []
        for obj_a, obj_b in combinations(context.objects, 2):
            area = obj_a.footprint.intersection(obj_b.footprint).area
            if area <= options.overlap_tolerance:
                continue

            overlap_area = float(area)
            message = (
                f"Objects {obj_a.id} and {obj_b.id} overlap on the floor plane."
            )
            hint = (
                f"Separate {obj_a.id} and {obj_b.id} laterally to remove the "
                f"{overlap_area:.3f} m² overlap."
            )
            issues.append(
                LintIssue(
                    code=self.code,
                    severity=LintSeverity.ERROR,
                    object_id=f"{obj_a.id},{obj_b.id}",
                    message=message,
                    hint=hint,
                    data={"overlap_area": overlap_area},
                )
            )
        return issues

