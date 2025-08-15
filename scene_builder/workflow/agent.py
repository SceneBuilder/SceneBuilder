from pydantic_ai import Agent, RunContext, BinaryContent
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.google import GoogleProvider

from scene_builder.definition.scene import Room
from scene_builder.tools.read_file import read_media_file
from scene_builder.utils.pai_utils import transform_paths_to_binary
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
