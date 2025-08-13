from typing import Any

from pydantic import BaseModel


class RoomPlan(BaseModel):
    room_description: str = None
    room_inspiration: list[Any] = None
