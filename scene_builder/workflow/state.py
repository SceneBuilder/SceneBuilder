from typing import Literal

from pydantic import BaseModel

from scene_builder.definition.scene import Object, ObjectBlueprint, Room, Section
from scene_builder.definition.plan import RoomPlan


class PlacementState(BaseModel):
    room: Room
    room_plan: RoomPlan
    what_to_place: Object | ObjectBlueprint | Section
    room_history: list[Room] | None = None


class PlacementAction(BaseModel):
    updated_room: Room


class KeepEditingOrFinalize(BaseModel):
    decision: Literal["keep_editing", "finalize"]


class PlacementResponse(BaseModel):
    placement_action: PlacementAction
    decision: KeepEditingOrFinalize
