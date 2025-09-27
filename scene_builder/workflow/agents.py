from pydantic_ai import Agent, RunContext
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider
from pydantic_ai.models.openai import OpenAIChatModel

from scene_builder.definition.scene import Room, Object, ObjectBlueprint, FloorDimensions
from scene_builder.tools.read_file import read_media_file
from scene_builder.database.object import ObjectDatabase
from scene_builder.utils.pai import transform_paths_to_binary
from scene_builder.workflow.prompts import (
    BUILDING_PLAN_AGENT_PROMPT,
    FLOOR_PLAN_AGENT_PROMPT,
    PLACEMENT_AGENT_PROMPT,
    FLOOR_SIZE_AGENT_PROMPT,
    ROOM_DESIGN_AGENT_PROMPT,
    SEQUENCING_AGENT_PROMPT,
    SHOPPING_AGENT_PROMPT,
)
from scene_builder.workflow.states import (
    PlacementState,
    PlacementResponse,
    RoomDesignState,
    RoomDesignResponse,
)
import os


# model = GoogleModel("gemini-2.5-pro")
model = GoogleModel("gemini-2.5-flash")
# model = OpenAIChatModel("gpt-5-mini")
# model = OpenAIChatModel("gpt-5-nano")
# model = OpenAIChatModel(
#     'x-ai/grok-4-fast:free',
#     provider=OpenRouterProvider(api_key=os.getenv("OPENROUTER_API_KEY")),
# )
obj_db = ObjectDatabase()

floor_plan_agent = Agent(
    model,
    system_prompt=FLOOR_PLAN_AGENT_PROMPT,
    output_type=list[Room],
)

placement_agent = Agent(
    model,
    deps_type=PlacementState,
    system_prompt=PLACEMENT_AGENT_PROMPT,
    output_type=PlacementResponse,
    tools=[read_media_file],
)


@placement_agent.system_prompt
async def add_placement_state(ctx: RunContext[PlacementState]) -> str:
    placement_state = ctx.deps
    return f"The current placement state:\n {placement_state}"
    # return (
    #     f"The current placement state:\n {transform_paths_to_binary(placement_state)}"
    # )  # NOTE: `binary_content` part of system_prompt doesn't seem to undergo
    #            media handling. instead, it is sent as tokenized plain text.


planning_agent = Agent(
    model,
    system_prompt=BUILDING_PLAN_AGENT_PROMPT,
)

floor_size_agent = Agent(
    model,
    system_prompt=FLOOR_SIZE_AGENT_PROMPT,
    output_type=FloorDimensions,
)


sequencing_agent = Agent(
    model,
    system_prompt=SEQUENCING_AGENT_PROMPT,
    output_type=list[ObjectBlueprint]
)

# Shopping agent for finding 3D assets from graphics database
shopping_agent = Agent(
    model,
    system_prompt=SHOPPING_AGENT_PROMPT,
    # tools=[obj_db.query, obj_db.get_asset_thumbnail],  # old
    tools=[obj_db.search, obj_db.pack],  # new(?) - candidate
    # output_type=list[ObjectBlueprint],
    output_type=list[ObjectBlueprint],  # TEMP - only for tests
)
# TODO(?): implement a logic to filter / boil down what assets to choose out of returned *candidates*
# TODO: make sure that the markdown report generated from `obj_db.search()` undergoes proper processing
#       of multimedia data - in other words, make sure that the VLM is able to *see* the thumbnails.
#       This is because multimedia content within user prompt seems to undergo proper processing, but 
#       those within system prompt does not seem to. The tool call result probably will have a separate
#       channel of communication (how it is stored in the conversation history, and how that conversation history
#       transforms into LLM API calls). This can be seen by debugging thru PydAI's source code and inspecting Logfire. 

room_design_agent = Agent(
    model,
    deps_type=RoomDesignState,
    system_prompt=ROOM_DESIGN_AGENT_PROMPT,
    output_type=RoomDesignResponse,
    tools=[read_media_file],
)

@room_design_agent.system_prompt
async def add_room_design_state(ctx: RunContext[RoomDesignState]) -> str:
    room_design_state = ctx.deps
    return f"The current placement state:\n {room_design_state}"
    # NOTE: see note in `add_placement_state()`
