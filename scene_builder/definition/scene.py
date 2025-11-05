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


class Shell(BaseModel):
    """Represents a room shell surface such as a floor or wall."""

    type: Literal["wall", "floor"]
    material_id: str | None = None


class Structure(BaseModel):
    """Represents a structural element (e.g., door, window) excl. wall"""

    id: str
    type: Literal["door", "window"]
    boundary: list[Vector2] | None = None


class Room(BaseModel):
    """Represents a single room in the scene."""

    id: str
    category: str | None = None
    tags: list[str] = []
    # plan: GenericPlan | None = None
    boundary: list[Vector2] = []
    # floor_dimensions: FloorDimensions | None = None
    objects: list[Object] = []
    shells: list[Shell] = []
    structure: list[Structure] | None = None  # NOTE: try to make this invisible/immutable
    
    # NOTE: for origin normalization state tracking, for now
    extra_info: Any | None = None


# NOTE: Let's not have anything extraneous to the scene definition in the `Room` (or other scene-def-related) stuff.
#       For example: text, images, etc. 
#       One way to think about it is: it's a pure-data struct;
#       The fundamental, most-reduced set of information need to recreate a scene in Blender (or other decoders).
#       The rationale is that we don't want to have the LLM output those long texts at every design iteration — it lowers SNR.
#       Maybe there is another way to achieve it, though — like private attribute? Not sure how private attrs work in pydantic_ai. 

#     NOTE: don't delete!
#     type: str | None = None
#     tags: list[str] | None = None


class Scene(BaseModel):
    """Represents the entire 3D scene."""

    category: str | None
    height_class: Literal["single_story", "two_story", "multi_story", "high_rise", "skyscraper"]
    rooms: list[Room] = []
    tags: list[str] = []


def find_shell(
    room_or_data: Room | dict[str, Any],
    shell_type: Literal["wall", "floor"],
) -> Shell | None:
    """
    Returns the shell of the requested type from a Room or room dict, or None if not found.

    Accepts either a pydantic Room instance or a plain room dictionary.
    """
    if not isinstance(room_or_data, Room):
        room_or_data = Room(**room_or_data)

    shells = room_or_data.shells or []
    for s in shells:
        if s.type == shell_type:
            return s
    return None
