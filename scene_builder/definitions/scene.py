from dataclasses import dataclass, field
from typing import List, Literal

@dataclass
class GlobalConfig:
    """Global configuration for the scene generation process."""
    previewAfterAction: bool = False

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
class Room:
    """Represents a single room in the scene."""
    id: str
    category: str
    tags: List[str]
    objects: List[Object] = field(default_factory=list)

@dataclass
class Scene:
    """Represents the entire 3D scene."""
    category: str
    tags: List[str]
    floorType: Literal["single", "multi"]
    rooms: List[Room] = field(default_factory=list)