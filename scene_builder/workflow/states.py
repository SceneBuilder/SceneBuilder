from pathlib import Path
from typing import Literal

from graphics_db_server.schemas.asset import Asset
from pydantic import BaseModel, Field
from pydantic_ai.messages import ModelMessage


from scene_builder.definition.scene import (
    GlobalConfig,
    Object,
    ObjectBlueprint,
    Room,
    Section,
    Scene,
)
from scene_builder.definition.plan import RoomPlan


class MainState(BaseModel):
    user_input: str
    scene_definition: Scene | None = None
    plan: str | None = None
    messages: list[ModelMessage] = Field(default_factory=list)
    current_room_index: int = 0
    global_config: GlobalConfig | None = None


class KeepEditingOrFinalize(BaseModel):
    decision: Literal["keep_editing", "finalize"]


class PlacementState(BaseModel):
    room: Room
    room_plan: RoomPlan
    what_to_place: (
        Object | ObjectBlueprint | Section
    )  # NOTE: maybe rename to `placeable`
    room_history: list[Room] = []  # NOTE: maybe rename to `history`


class PlacementAction(BaseModel):
    updated_room: Room


class PlacementResponse(BaseModel):
    placement_action: PlacementAction
    decision: KeepEditingOrFinalize
    reasoning: str


class RoomDesignState(BaseModel):
    room: Room
    room_plan: RoomPlan
    shopping_cart: list[ObjectBlueprint] = []
    viz: list[Path] = []
    # NOTE: It's possible to put room_history here as well...
    # TODO (yunho-c): make a decision on ^.


# class RoomDesignAction(BaseModel):
#     updated_room: Room


class RoomDesignResponse(BaseModel):
    # room_design_action: RoomDesignAction
    decision: KeepEditingOrFinalize
    reasoning: str


class RoomUpdateState(BaseModel):
    updated_room: Room
