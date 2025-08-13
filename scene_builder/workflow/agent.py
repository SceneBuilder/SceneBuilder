from pydantic_ai import Agent

from scene_builder.definition.scene import Room
from scene_builder.workflow.prompt import (
    BUILDING_PLAN_AGENT_PROMPT,
    FLOOR_PLAN_AGENT_PROMPT,
    PLACEMENT_AGENT_PROMPT,
)
from scene_builder.workflow.state import PlacementState, PlacementAction, PlacementResponse

# VLM_MODEL = "openai:gpt-4o"
VLM_MODEL = "gemini:gemini-flash-2.5"

floor_plan_agent = Agent(
    VLM_MODEL,
    system_prompt=FLOOR_PLAN_AGENT_PROMPT,
    output_type=list[Room],
)

placement_agent = Agent(
    VLM_MODEL,
    deps_type=PlacementState,
    system_prompt=PLACEMENT_AGENT_PROMPT,
    output_type=PlacementResponse,
)

planning_agent = Agent(
    VLM_MODEL,
    system_prompt=BUILDING_PLAN_AGENT_PROMPT,
)
