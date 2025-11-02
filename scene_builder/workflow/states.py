from pathlib import Path
from typing import Any, Literal

from graphics_db_server.schemas.asset import Asset
from pydantic import BaseModel, Field, ConfigDict
from pydantic_ai.messages import ModelMessage


from scene_builder.config import GenerationConfig
from scene_builder.definition.scene import (
    Object,
    ObjectBlueprint,
    Room,
    Section,
    Scene,
)
from scene_builder.validation.models import LintReport
from scene_builder.definition.plan import RoomPlan


class CritiqueAction(BaseModel):
    result: Literal["approved", "rejected"]
    explanation: str


class MainState(BaseModel):
    user_input: str
    scene_definition: Scene | None = None
    plan: str | None = None
    messages: list[ModelMessage] = Field(default_factory=list)
    current_room_index: int = 0
    generation_config: GenerationConfig | None = None


class KeepEditingOrFinalize(BaseModel):
    decision: Literal["keep_editing", "finalize"]


class PlacementState(BaseModel):
    model_config = ConfigDict(extra="allow")

    room: Room
    room_plan: RoomPlan
    what_to_place: (
        Object | ObjectBlueprint | Section
    )  # NOTE: maybe rename to `placeable`
    room_history: list[Room] = []  # NOTE: maybe rename to `history`
    run_count: int = 0  # DEBUG - track iterations


class PlacementAction(BaseModel):
    updated_room: Room


class PlacementResponse(BaseModel):
    placement_action: PlacementAction
    decision: KeepEditingOrFinalize
    reasoning: str


class RoomDesignStateBlueprint(BaseModel):
    room: Room
    # room_plan: RoomPlan
    room_plan: str


class RoomDesignState(BaseModel):
    room: Room
    room_plan: RoomPlan
    shopping_cart: list[ObjectBlueprint] = []
    message_history: Any = None
    run_count: int = 0  # track iterations (TEMP?)
    # viz: list[Path] = []
    # NOTE: It's possible to put room_history here as well...
    # TODO (yunho-c): make a decision on ^.

    extra_info: Any | None = None
    last_lint_report: LintReport | None = None


# class RoomDesignAction(BaseModel):
#     updated_room: Room


class RoomDesignResponse(BaseModel):
    # room_design_action: RoomDesignAction
    decision: KeepEditingOrFinalize
    reasoning: str


class RoomUpdateState(BaseModel):
    updated_room: Room
