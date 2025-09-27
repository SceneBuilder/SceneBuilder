from __future__ import annotations

from pydantic_graph import BaseNode, End, Graph, GraphRunContext

from scene_builder.config import DEBUG, TEST_ASSET_DIR
from scene_builder.decoder import blender
from scene_builder.definition.scene import Room
from scene_builder.utils.conversions import pydantic_to_dict
from scene_builder.workflow.agents import placement_agent
from scene_builder.workflow.states import PlacementState


class PlacementNode(BaseNode[PlacementState]):
    # NOTE: It should be fine for`PlacementNode` to just return either a Object or list[Object].
    # TODO: clean it up.
    async def run(
        self, ctx: GraphRunContext[PlacementState]
    ) -> PlacementVisualFeedback | End[Room]:
        ctx.state.run_count += 1  # DEBUG

        # TEMP HACK: terminate after first (TEMP: second) execution
        if ctx.state.run_count >= 3:
            return End(ctx.state.room)

        if DEBUG:
            # user_prompt = "By the way, I have a quick question: are you able to read the deps (the PlacementState)?"
            # user_prompt = "Could you repeat exactly what was provided to you (in terms of the depedencies) into the 'reasoning' output?"
            # user_prompt = "Were you provided the current room boundaries (list[Vector2])? What is it?" # -> NO!
            user_prompt = "Are you able to see the visualized image of the room?"
            user_prompt = ""  # TEMP HACK
        else:
            user_prompt = ""

        # TODO: See if user_prompt is lost after the first iteration
        if ctx.state.user_prompt:
            user_prompt += ctx.state.user_prompt

        if user_prompt != "":
            response = await placement_agent.run(
                user_prompt=user_prompt, deps=ctx.state
            )
            # response = await placement_agent.run(ctx.state, user_prompt=user_prompt)
            # NOTE: when not using a kwarg, the first arg is understood as user prompt.
        else:
            response = await placement_agent.run(deps=ctx.state)

        if DEBUG:
            print(f"[PlacementNode]: {response.output.reasoning}")
            print(f"[PlacementNode]: {response.output.decision}")

        if response.output.decision.decision == "finalize":
            ctx.state.room = response.output.placement_action.updated_room
            return End(ctx.state.room)
        else:
            ctx.state.room = response.output.placement_action.updated_room
            return PlacementVisualFeedback()


class PlacementVisualFeedback(BaseNode[PlacementState]):
    # NOTE: moved from feedback.py to placement.py due to circular dependency.
    # NOTE: maybe we should refactor input/output state to `Feedbackable`, that can either
    #       be PlacementState, RoomDesignState, SceneState, etc., anything with a `history` field.
    # TODO: Either VisualFeedback must have variants, or accept/return multiple *State types appropriately.
    async def run(self, ctx: GraphRunContext[PlacementState]) -> PlacementNode:
        room_data = pydantic_to_dict(ctx.state.room)
        # blender.load_template(
        #     f"{TEST_ASSET_DIR}/scenes/classroom.blend", clear_scene=True
        # )  # TEMP HACK
        blender.parse_room_definition(room_data)
        top_down_render = blender.create_scene_visualization(output_dir="test_output", show_grid=True)
        isometric_render = blender.create_scene_visualization(output_dir="test_output", view="isometric", show_grid=True)
        prev_room = ctx.state.room
        prev_room.viz.append(top_down_render)
        prev_room.viz.append(isometric_render)
        ctx.state.room_history.append(prev_room)
        return PlacementNode()
        # NOTE: I think the feedback (in the form of text) should be generated here, not in the PlacementNode. 
        #       Even though the PlacementNode probably needs to see the same images as well


placement_graph = Graph(
    nodes=[
        PlacementNode,
        PlacementVisualFeedback,
    ],
    state_type=PlacementState,  # hmm
)
