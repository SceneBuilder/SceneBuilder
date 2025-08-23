from pydantic_ai import Agent, RunContext, BinaryContent
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.google import GoogleProvider

from scene_builder.definition.scene import Room, Object
from scene_builder.tools.read_file import read_media_file
from scene_builder.tools.asset_search import search_assets
from scene_builder.utils.pai import transform_paths_to_binary
from scene_builder.workflow.prompt import (
    BUILDING_PLAN_AGENT_PROMPT,
    FLOOR_PLAN_AGENT_PROMPT,
    PLACEMENT_AGENT_PROMPT,
)
from scene_builder.workflow.state import (
    PlacementState,
    PlacementAction,
    PlacementResponse,
)


model = GoogleModel("gemini-2.5-flash")
# model = OpenAIModel("gpt-5-mini")
# model = OpenAIModel("gpt-5-nano")
# model = "openai:gpt-4o"

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
    tools=[read_media_file]
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

# Shopping agent for finding 3D assets from graphics database
shopping_agent = Agent(
    model,
    system_prompt="You are a shopping assistant for 3D assets. Your goal is to help find the most appropriate 3D objects from the graphics database based on the user's description. Use the search_assets tool to find relevant assets. When returning objects, convert Asset data to Object format: use Asset.uid for Object.sourceId, Asset.url for Object.source, and generate appropriate names and descriptions based on the asset tags and metadata. Set initial position, rotation, and scale to default values (position: x=0,y=0,z=0; rotation: x=0,y=0,z=0; scale: x=1,y=1,z=1).",
    tools=[search_assets],
    response_model=list[Object],  # Return Object instances for scene placement
)
