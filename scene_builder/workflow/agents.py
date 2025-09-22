from pydantic_ai import Agent, RunContext
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from scene_builder.definition.scene import Room, Object, ObjectBlueprint, FloorDimensions
from scene_builder.tools.read_file import read_media_file
from scene_builder.tools.asset_search import search_assets, get_asset_thumbnail
from scene_builder.workflow.prompts import (
    BUILDING_PLAN_AGENT_PROMPT,
    FLOOR_PLAN_AGENT_PROMPT,
    PLACEMENT_AGENT_PROMPT,
    FLOOR_SIZE_AGENT_PROMPT,
)
from scene_builder.workflow.states import (
    PlacementState,
    PlacementResponse,
)
import os

# Configure Google Gemini model
# Prefer explicit API key from env var if provided; otherwise rely on provider defaults
api_key = os.getenv("GOOGLE_API_KEY")
provider = GoogleProvider(api_key=api_key) if api_key else GoogleProvider()
model = GoogleModel("gemini-2.5-flash", provider=provider)
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


# Shopping agent for finding 3D assets from graphics database
shopping_agent = Agent(
    model,
    system_prompt="You are a shopping assistant for 3D assets. Your goal is to help find the most appropriate 3D objects from the graphics database based on the user's description. Use the search_assets tool to find relevant assets. You can use get_asset_thumbnail to view thumbnails of assets and read_media_file to view any other media files. When returning objects, convert Asset data to Object format: use Asset.uid for Object.source_id, Asset.url for Object.source, and generate appropriate names and descriptions based on the asset tags and metadata. Set initial position, rotation, and scale to default values (position: x=0,y=0,z=0; rotation: x=0,y=0,z=0; scale: x=1,y=1,z=1).",
    tools=[search_assets, get_asset_thumbnail],
    output_type=list[ObjectBlueprint],
)


room_design_agent = Agent(
    "openai:gpt-4o",
    system_prompt="You are a room designer. Your goal is to add objects to the room based on the plan. Please utilize `PlacementAgent` to populate the room with objects from the `ShoppingCart`, until you are satisfied with the room.",
    tools=[],
    output_type=list[Object],
)
