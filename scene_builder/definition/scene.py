from dataclasses import dataclass, field
from typing import Any, Literal

from PIL import Image


@dataclass
class Config:
    """Global configuration for the generation process."""

    debug: bool = False
    previewAfterAction: bool = False


@dataclass
class GenericPlan:
    pass


@dataclass
class Vector2:
    """Represents a 2D vector."""

    x: float
    y: float


@dataclass
class Vector3:
    """Represents a 3D vector."""

    x: float
    y: float
    z: float


@dataclass
class Object:
    """Represents a 3D object in the scene."""

    id: str
    name: str
    description: str
    source: str
    sourceId: str
    position: Vector3
    rotation: Vector3
    scale: Vector3


@dataclass
class Section:
    # NOTE: not sure whether to allow recursive sections (e.g., section of sections)
    """Represents a repeatable group of objects."""

    id: str
    position: Vector3
    rotation: Vector3
    # scale: Vector3  # ?
    children: list[Object]


@dataclass
class Room:
    """Represents a single room in the scene."""

    id: str
    # category: str  # ?
    tags: list[str]
    plan: GenericPlan | None = None
    boundary: list[Vector2] | None = None
    viz: list[Image.Image] | None = None
    # objects: list[Object] = field(default_factory=list)  # TODO: figure out how field / default_factory works!
    children: list[Object | Section] = []


# @dataclass
# class RoomState: # NOTE: don't delete!
#     # type: str | None = None
#     tags: list[str] | None = None


@dataclass
class Scene:
    """Represents the entire 3D scene."""

    category: str
    tags: list[str]
    floorType: Literal["single", "multi"]
    rooms: list[Room] = field(default_factory=list)
