"""Core data structures shared by linting routines."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from shapely.geometry import Polygon

from scene_builder.definition.scene import Object, Room

from scene_builder.lint.models import AABB

if TYPE_CHECKING:  # pragma: no cover - typing support only
    from scene_builder.lint.rules.base import LintRule


@dataclass(slots=True)
class LintingOptions:
    """Configuration options for lint execution."""

    floor_height: float = 0.0
    wall_clearance: float = 0.05
    overlap_tolerance: float = 1e-3
    floor_tolerance: float = 0.01
    enabled_rules: set[str] | None = None
    rules: tuple["LintRule", ...] = field(default_factory=lambda: DEFAULT_RULES)


@dataclass(slots=True)
class LintableObjectData:
    """Normalized view of an object and its derived geometry."""

    object: Object
    bounds: AABB
    footprint: Polygon

    @property
    def id(self) -> str:
        return self.object.id

    @property
    def bottom(self) -> float:
        return self.bounds.bottom

    @property
    def footprint_area(self) -> float:
        return float(self.footprint.area)


@dataclass(slots=True)
class LintableRoomData:
    """Room-level geometry cached for lint rules."""

    definition: Room
    footprint: Polygon

    @property
    def area(self) -> float:
        return float(self.footprint.area)


@dataclass(slots=True)
class LintContext:
    """Shared context passed to lint rules."""

    room: LintableRoomData
    objects: list[LintableObjectData]


from scene_builder.lint.rules.dominates_room import DominatesRoomRule
from scene_builder.lint.rules.floor_origin import FloorOriginRule
from scene_builder.lint.rules.floor_penetration import FloorPenetrationRule
from scene_builder.lint.rules.object_overlap import ObjectOverlapRule
from scene_builder.lint.rules.wall_overlap import WallOverlapRule


DEFAULT_RULES: tuple["LintRule", ...] = (
    FloorOriginRule(),
    FloorPenetrationRule(),
    WallOverlapRule(),
    DominatesRoomRule(),
    ObjectOverlapRule(),
)

