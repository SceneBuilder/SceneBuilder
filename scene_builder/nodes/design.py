from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_graph import BaseNode, End, Graph, GraphRunContext
from rich.console import Console

from scene_builder.config import DEBUG
from scene_builder.database.object import ObjectDatabase
from scene_builder.decoder import blender
# from scene_builder.definition.scene import Object, Room, Vector3
from scene_builder.definition.scene import Object, Room, Scene, Vector3
# from scene_builder.nodes.feedback import VisualFeedback
# from scene_builder.nodes.placement import PlacementNode, VisualFeedback
from scene_builder.nodes.placement import PlacementNode, PlacementVisualFeedback, placement_graph
# from scene_builder.nodes.routing import DesignLoopRouter
from scene_builder.workflow.agents import room_design_agent, shopping_agent
# from scene_builder.workflow.graphs import placement_graph # hopefully no circular import... -> BRUH.
# from scene_builder.workflow.states import PlacementState, RoomDesignState
from scene_builder.workflow.states import PlacementState, RoomDesignState, MainState

console = Console()
obj_db = ObjectDatabase()


class DesignLoopRouter(BaseNode[MainState]):
    async def run(self, ctx: GraphRunContext[MainState]) -> End[Scene]:
        console.print("[bold yellow]Entering room design loop...[/]")
        if ctx.state.current_room_index < len(ctx.state.scene_definition.rooms):
            console.print("[magenta]Decision:[/] Design next room.")
            subgraph_result = await room_design_graph.run(
                RoomDesignNode(ctx.state.initial_number)
            )
            ctx.state.scene_definition.rooms.append(subgraph_result)
        else:
            console.print("[magenta]Decision:[/] Finish.")
            return End(ctx.state.scene_definition)
        # TODO: use VisualFeedback to decide if there are rooms that still need designing.
        # TODO:


class RoomDesignNode(BaseNode[RoomDesignState]):
    async def run(
        self, ctx: GraphRunContext[RoomDesignState]
    ) -> RoomDesignVisualFeedback | End[Room]:
        console.print("[bold cyan]Executing Node:[/] RoomDesignNode")
        room = ctx.state.room
        response = await room_design_agent.run(deps=ctx.state)

        if DEBUG:
            print(f"[RoomDesignNode]: {response.output.decision}")
            print(f"[RoomDesignNode]: {response.output.reasoning}")
        if response.output.decision == "finalize":
            return End(ctx.state.room)

        # else:
        shopping_user_prompt = (
            f"Room id: '{room.id}'.",
            f"Room category: '{room.category}'.",
            f"Room plan: {ctx.state.room_plan}.",
            f"Existing items in the shopping cart: {ctx.state.shopping_cart}",
        )
        # NOTE: It may be beneficial to add a state variable to control whether shopping_agent can / should be invoked,
        #       to allow for "waterfall"-style selection → placement sequence.
        # NOTE: For example, it can be beneficial to think of "design" and "build" separately,
        #       where design consists of shopping and planning, and building consists of going back-and-forth
        #       between the placement node/agent, doing quality checks via visual feedback (potentially giving
        #       the PlacementNode some advice, although it has feedback of its own), or re-initiating motion
        #       of certain already-place items, and then finalizing the room to end the process.
        #       What this ultimately means is that there are probably certain parts that are to be invoked once,
        #       and certain parts that are meant to run repetitively. It's useful to model the human design process.

        shopping_agent_response = await shopping_agent.run(shopping_user_prompt)
        shopping_cart = shopping_agent_response.output
        console.print(
            f"[bold cyan]Added Objects:[/] {[obj.name for obj in shopping_cart]}"
        )
        ctx.state.shopping_cart.extend(shopping_cart)
        # NOTE: may need to diff the shopping cart content or something, if shopping
        #       is anything other than shopping a singular object that is immediately needed.
        # NOTE: not sure if VLM is going to repeat existing stuff in the ShoppingCart
        #       or skip them. (probably need to explicitly prompt to "pin" this behavior.)

        # TODO: ask VLM what to deliberately think about what to place first
        # (in general, larger "anchor" objects first, so that other objects can
        # be placed relative to it.)
        # "Please choose what to place next."
        # what_to_place = NotImplementedError()

        # TEMP: choose the first item in the shopping cart
        what_to_place = shopping_cart[0]

        # NOTE: It would be interesting if the room design agent can "think" of
        #       certain opinions and feed it to PlacementNode as text guidance.
        placement_state = PlacementState(
            room=room,
            room_plan=ctx.state.room_plan,
            what_to_place=what_to_place,
        )

        placement_subgraph_response = await placement_graph.run(
            PlacementNode(), state=placement_state
        )
        updated_room: Room = placement_subgraph_response.output
        ctx.state.room = updated_room
        # ctx.state.room_history += new_placement_state.room_history

        # TODO: use VisualFeedback and ShoppingCart to decide if room needs more objects or end
        # NOTE: the logic should be: the room is fed to a visual feedback agent, along with information
        #       such as the remaining items in the shopping cart (that is "explorable" in terms of detail,
        #       meaning it can be as simple as how many objects are left and their names, or their thumbnails & sizes),

        return RoomDesignVisualFeedback()

        # TODO: decide whether to finalize the scene, or to continue designing.
        # TODO: if deciding to continue, choose what to place next.

        # NOTE: don't return `UpdateScene` directly; return a room to caller (DesignLoopRouter)
        #       and let it take care of coalescing it with the entire Scene.

        # IDEA: It would be cool to visualize the conversations and back-and-forths between the different "agents"
        #       in the time-lapse scene building video, along with locations (just randomized movements around the room/
        #       object of interest, probably). Think: cute minimal robot blob characters with chat bubbles, sounds, and motions.

        # IDEA: Using a conditioned image diffusion model to "imagine" different layouts, based on the current room image
        #       and thumbnails of the assets. So that diverse layouts can be efficiently "explored", without having to repetitively
        #       call VLMs and building in Blender. This is a cool idea with questionable practicality, but just for the sake of
        #       modeling the human design process with VLMs/AI agents, it is *very* interesting.
        #       Honestly, can be a cool part of the paper.

        # return UpdateScene()


class RoomDesignVisualFeedback(BaseNode[RoomDesignState]):
    # NOTE: see PlacementVisualFeedback in `placement.py` for notes and design decisions.
    async def run(self, ctx: GraphRunContext[RoomDesignState]) -> RoomDesignNode:
        blender.parse_room_definition(ctx.state.room)
        top_down_render = blender.create_scene_visualization(output_dir="test_output")
        isometric_render = blender.create_scene_visualization(
            output_dir="test_output", view="isometric"
        )
        ctx.state.viz.append([top_down_render, isometric_render])
        return RoomDesignNode()


room_design_graph = Graph(
    nodes=[
        DesignLoopRouter,  # TEMP
        RoomDesignNode,
        RoomDesignVisualFeedback,
    ],
    state_type=Room,
)

# NOTES
"""
There are two models of the room design process that can be thought of, as of now:

1) The RoomDesignNode selects a single object to add into the room (using ShoppingAgent), and calls
   PlacementNode to place the object. This simple loop is repeated, along with VisualFeedback and
   RoomPlan as a reference, so that RoomDesignNode can find a stopping point, when it finds it satisfactory.

2) The RoomDesignNode selects what objects to add into the room (using ShoppingAgent), and then calls
   RoomBuildNode, which interactively commands the PlacementNode along with VisualFeedback and RoomPlan,
   and is capable of invoking edits of existing object placements, and generating multiple room layout candidates,
   to be fed into a quantitative scorer for score-based winner-takes-all pooling. 
   
   The RoomBuildNode can ask to "go back to the drawing board", giving back control to the design node to invite
   additional objects into the ShoppingCart, or do so when it empties the given ShoppingCart, or finds the room
   sufficiently occupied where placement of more objects is not necessary. 
   
   The RoomDesignNode can perform additional tasks, such as generating GenAI-based candidate layout generation
   in the form of images, to effectively serve as the inspiration ("inspo") of downstream designers/placers. 
   
   This suggests to allow a more organic flow of placement, editing, designing, and imagining, and
   may yield a higher quality scene overall. 

"""
