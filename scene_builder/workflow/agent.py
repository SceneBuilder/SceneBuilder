from pydantic_ai import Agent, RunContext
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from scene_builder.definition.scene import Room, FloorDimensions
from scene_builder.workflow.prompt import (
    BUILDING_PLAN_AGENT_PROMPT,
    FLOOR_PLAN_AGENT_PROMPT,
    PLACEMENT_AGENT_PROMPT,
    FLOOR_SIZE_AGENT_PROMPT,
)
from scene_builder.workflow.state import (
    PlacementState,
    PlacementAction,
    PlacementResponse,
)
import os


# Configure Google Gemini model
# Prefer explicit API key from env var if provided; otherwise rely on provider defaults
api_key = os.getenv("GOOGLE_API_KEY")
provider = GoogleProvider(api_key=api_key) if api_key else GoogleProvider()
model = GoogleModel("gemini-2.5-flash", provider=provider)
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
)


@placement_agent.system_prompt
async def add_placement_state(ctx: RunContext[PlacementState]) -> str:
    placement_state = ctx.deps
    return f"The current placement state:\n {placement_state}"


planning_agent = Agent(
    model,
    system_prompt=BUILDING_PLAN_AGENT_PROMPT,
)

floor_size_agent = Agent(
    model,
    system_prompt=FLOOR_SIZE_AGENT_PROMPT,
    output_type=FloorDimensions,
)
