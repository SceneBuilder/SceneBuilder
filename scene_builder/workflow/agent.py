from pydantic_ai import Agent
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from scene_builder.definition.scene import Room
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

planning_agent = Agent(
    model,
    system_prompt=BUILDING_PLAN_AGENT_PROMPT,
)
