from typing import Any, Literal

from pydantic import BaseModel, Field
from PIL import Image


class Config(BaseModel):
    """Global configuration for the generation process."""

    debug: bool = False
    previewAfterAction: bool = False


class GenericPlan(BaseModel):
    pass


class Vector2(BaseModel):
    """Represents a 2D vector."""

    x: float
    y: float


class Vector3(BaseModel):
    """Represents a 3D vector."""

    x: float
    y: float
    z: float


class ObjectBlueprint(BaseModel):
    id: str
    source: str
    description: str
    extra_info: Any  # NOTE: useful informative things like size, default orientation, thumbnail, ...


class Object(BaseModel):
    """Represents a 3D object in the scene."""

    name: str
    id: str
    source: str
    sourceId: str | None = None
    description: str
    position: Vector3
    rotation: Vector3
    scale: Vector3


class Section(BaseModel):
    # NOTE: not sure whether to allow recursive sections (e.g., section of sections)
    """Represents a repeatable group of objects."""

    id: str
    position: Vector3
    rotation: Vector3
    # scale: Vector3  # ?
    children: list[Object] = Field(default_factory=list)


class Room(BaseModel):
    """Represents a single room in the scene."""

    id: str
    category: str
    tags: list[str]
    plan: GenericPlan | None = None
    boundary: list[Vector2] | None = None
    viz: list[Image.Image] | None = None
    objects: list[Object | Section] = Field(default_factory=list)
#     NOTE: don't delete!
#     type: str | None = None
#     tags: list[str] | None = None


class Scene(BaseModel):
    """Represents the entire 3D scene."""

    category: str
    tags: list[str]
    floorType: Literal["single", "multi"]
    rooms: list[Room] = Field(default_factory=list)
