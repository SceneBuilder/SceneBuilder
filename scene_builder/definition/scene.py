from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


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
    name: str | None = None
    source_id: str
    source: str
    description: str
    extra_info: Any | None = (
        None  # NOTE: useful informative things like size, default orientation, thumbnail, ...
    )


class Object(BaseModel):
    """Represents a 3D object in the scene."""

    name: str
    id: str
    source: str
    # source_id: str | None = None
    source_id: str  # TEMP: to resolve ObjectBlueprint → Object adapter mistake
    description: str
    position: Vector3
    rotation: Vector3
    scale: Vector3
    tags: list[str] | None = None

    @classmethod
    def from_blueprint(
        cls,
        blueprint: "ObjectBlueprint",
        id: str,
        position: Vector3,
        rotation: Vector3,
        scale: Vector3,
        tags: list[str] | None = None,
        name: str | None = None,
    ) -> "Object":
        """Create an Object from an ObjectBlueprint with additional required properties."""
        return cls(
            name=name or blueprint.name or "Unnamed Object",
            id=id,
            source=blueprint.source,
            source_id=blueprint.source_id,
            description=blueprint.description,
            position=position,
            rotation=rotation,
            scale=scale,
            tags=tags,
        )


class Section(BaseModel):
    # NOTE: not sure whether to allow recursive sections (e.g., section of sections)
    """Represents a repeatable group of objects."""

    id: str
    position: Vector3
    rotation: Vector3
    # scale: Vector3  # ?
    children: list[Object] = Field(default_factory=list)


class FloorDimensions(BaseModel):
    """Represents floor dimensions and metadata from LLM analysis."""
    
    width: float  # Floor width in meters (x-axis)
    length: float  # Floor length/depth in meters (y-axis)
    ceiling_height: float = 2.7  # Room height in meters (z-axis), default standard height
    area_sqm: float | None = None
    shape: str | None = None  # rectangular, L-shaped, irregular, etc.
    confidence: float | None = None  # LLM confidence score
    llm_analysis: str | None = None  # Raw LLM description


class Room(BaseModel):
    """Represents a single room in the scene."""

    id: str
    category: str | None = None
    tags: list[str] | None = None
    plan: GenericPlan | None = None
    boundary: list[Vector2] | None = None
    floor_dimensions: FloorDimensions | None = None
    viz: list[Path] = []
    objects: list[Object] = []
    # objects: list[Object] = Field(default_factory=list)
    # objects: list[Object | Section] = Field(default_factory=list)


#     NOTE: don't delete!
#     type: str | None = None
#     tags: list[str] | None = None


class Scene(BaseModel):
    """Represents the entire 3D scene."""

    category: str | None
    tags: list[str] | None
    floorType: Literal["single", "multi"]
    rooms: list[Room] = Field(default_factory=list)
