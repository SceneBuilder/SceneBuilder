from dataclasses import dataclass
from typing import Any


@dataclass
class RoomPlan:
    room_description: str
    room_inspiration: list[Any]

