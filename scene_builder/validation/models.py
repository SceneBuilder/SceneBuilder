"""Data structures shared by linting utilities."""

from __future__ import annotations

from enum import Enum
from typing import Any, Iterable, Literal

from pydantic import BaseModel, Field

from scene_builder.definition.scene import Vector3


class LintSeverity(str, Enum):
    """Severity levels for lint findings."""

    HINT = "hint"
    WARNING = "warning"
    ERROR = "error"


class LintIssue(BaseModel):
    """A single linter finding."""

    code: str
    message: str
    severity: LintSeverity = LintSeverity.WARNING
    object_id: str | None = None
    hint: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class LintActionTaken(BaseModel):
    issue_id: str
    object_id: str | None = None
    summary: str
    rationale: str
    delivered: bool = False


class LintIssueTicket(BaseModel):
    issue_id: str
    object_id: str | None = None
    code: str
    message: str
    hint: str | None = None
    status: Literal["open", "resolved"] = "open"
    retries: int = 0
    actions: list[str] = Field(default_factory=list)


class LintReport(BaseModel):
    """Collection of linter findings for a room."""

    room_id: str
    issues: list[LintIssue] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)

    def add(self, issue: LintIssue) -> None:
        """Append an issue to the report."""

        self.issues.append(issue)


class AABB(BaseModel):
    """Axis-aligned bounding box defined by minimum and maximum corners."""

    min_corner: tuple[float, float, float]
    max_corner: tuple[float, float, float]

    @classmethod
    def from_center(
        cls, center: Iterable[float], half_extents: Iterable[float]
    ) -> "AABB":
        cx, cy, cz = (float(c) for c in center)
        hx, hy, hz = (float(h) for h in half_extents)
        return cls(
            min_corner=(cx - hx, cy - hy, cz - hz),
            max_corner=(cx + hx, cy + hy, cz + hz),
        )

    def translate(self, offset: Iterable[float]) -> "AABB":
        ox, oy, oz = (float(o) for o in offset)
        min_x, min_y, min_z = self.min_corner
        max_x, max_y, max_z = self.max_corner
        return AABB(
            min_corner=(min_x + ox, min_y + oy, min_z + oz),
            max_corner=(max_x + ox, max_y + oy, max_z + oz),
        )

    @property
    def width(self) -> float:
        return max(0.0, self.max_corner[0] - self.min_corner[0])

    @property
    def depth(self) -> float:
        return max(0.0, self.max_corner[1] - self.min_corner[1])

    @property
    def height(self) -> float:
        return max(0.0, self.max_corner[2] - self.min_corner[2])

    @property
    def bottom(self) -> float:
        return self.min_corner[2]


class ObjectAdjustment(BaseModel):
    """
    Patch-style edits for a single object.

    We ask the agent for a minimal diff instead of a full Object to avoid accidental
    clobbering of unchanged fields and to make destructive intents (e.g., removal)
    explicit. This keeps application logic simple and safer: if an attribute is absent,
    we leave it untouched.
    """

    id: str | None = None
    position: Vector3 | None = None
    rotation: Vector3 | None = None
    scale: Vector3 | None = None
    remove: bool = False


class IssueResolutionOutput(BaseModel):
    resolved: bool = False
    action_desc: str
    rationale: str
    object_id: str | None = None
    adjustment: ObjectAdjustment | None = None
    ticket_id: str | None = None

