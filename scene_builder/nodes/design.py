from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_graph import BaseNode, End, Graph, GraphRunContext
from rich.console import Console

from scene_builder.config import DEBUG
from scene_builder.database.object import ObjectDatabase
from scene_builder.decoder import blender
# from scene_builder.definition.scene import Object, Room, Vector3
from scene_builder.definition.scene import Object, ObjectBlueprint, Room, Scene, Vector3
# from scene_builder.nodes.feedback import VisualFeedback
# from scene_builder.nodes.placement import PlacementNode, VisualFeedback
from scene_builder.utils.pai import transform_paths_to_binary
from scene_builder.nodes.placement import (
    PlacementNode,
    PlacementVisualFeedback,
    placement_graph,
)
# from scene_builder.nodes.routing import DesignLoopRouter
from scene_builder.workflow.agents import (
    room_design_agent,
    sequencing_agent,
    shopping_agent,
)
# from scene_builder.workflow.graphs import placement_graph # hopefully no circular import... -> BRUH.
# from scene_builder.workflow.states import PlacementState, RoomDesignState
from scene_builder.workflow.states import CritiqueAction, PlacementState, RoomDesignState, MainState
from scene_builder.workflow.toolsets import shopping_toolset

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
    # ) -> RoomDesignVisualFeedback | End[Room]:
    ) -> RoomDesignNode | End[Room]:
        console.print("[bold cyan]Executing Node:[/] RoomDesignNode")
        room = ctx.state.room
        blender.parse_room_definition(room)
        top_down_render = blender.create_scene_visualization(output_dir="test_output", show_grid=True)
        isometric_render = blender.create_scene_visualization(
            output_dir="test_output", view="isometric", show_grid=True
        )
        renders = transform_paths_to_binary([top_down_render, isometric_render])
        room_plan = transform_paths_to_binary(ctx.state.room_plan)
        rda_user_prompt = (
            f"This is design iteration {ctx.state.run_count}.\n",
            "Please look at the following information:\n",
            f"- Room State: \n\n```json\n{room}\n```\n",
            "- Renders (top-down and isometric):",
            *renders,
            f"- Concept: {room_plan}\n" if ctx.state.run_count == 0 else "",
            # "Please decide whether to continue designing the room, or if you are satisfied with the current state of the room.",
            "Please write a detailed design plan that may include details on areas or sections of the room, what kind of objects and furnitures you plan to place, and how you plan to place them." if ctx.state.run_count == 0 else\
            # "Please write a detailed design plan." if ctx.state.run_count == 0 else\  # ALT
            "Do you want to continue designing the room, or are you complete with the design?",
        )
        response = await room_design_agent.run(
            rda_user_prompt,
            # deps=ctx.state,  # I don't think this means anything anymore (it's just for tool calling)
            # output_type=str
        )
        # NOTE: design termination is not handled. 
        #       one idea is to conditionally specify output type based on run count. 

        if DEBUG:
        #     print(f"[RoomDesignNode]: {response.output.decision}")
        #     print(f"[RoomDesignNode]: {response.output.reasoning}")
            print(f"[RoomDesignNode]: {response.output}")
        # if response.output.decision == "finalize":
        #     return End(ctx.state.room)

        shopping_user_prompt = (
            "Please explore the object database to choose the objects that you would like to use for designing the room.",
            "The `search` tool provides information about potential candidates including ids, thumbnails, and dimensions.",
            "You can then use the `pack` tool to transform uids into a list of `ObjectBlueprint` instances.",
            "Please use the top_k parameter generously to explore different options and choose your favorite ones.",
            "(NOTE: If you feel like everything is added already, there is no need to add more objects every time!)",
            f"Existing items in the shopping cart: {ctx.state.shopping_cart}",
        )
        shopping_response = await room_design_agent.run(
            shopping_user_prompt,
            # deps=ctx.state,
            message_history=response.all_messages(),
            output_type=list[ObjectBlueprint],
            toolsets=[shopping_toolset],
        )
        items_to_add = shopping_response.output
        console.print(
            f"[bold cyan]Added Objects:[/] {[obj.name for obj in items_to_add]}"
        )
        ctx.state.shopping_cart.extend(items_to_add)
        # NOTE: I think it would be nice if the shopping cart thumbnails are visible even after the initial markdown report search.
        #       let's try to cook something up with either paths or binarycontent, so that the VLM can still see what they look like later.

        # NOTE: this simple implementation lacks the possibility of shop-once, place-multiple-times workflow.
        #       the above two prompts (and LLM calls) need to repeat. i think actually, pydantic_graph *is* needed to properly implement
        #       conditional routing of this sort. 
        feedback = None
        placement_run_count = 0
        while True:
            placement_user_prompt = (
                "Please design the room by placing objects into the room, by writing the `object` data with position, rotation, and scale.",
                "You don't need to place all objects at once (although you can!).",
                "Once you are done, you will be given updated renders so that you can review and refine the placements.",
                "(NOTE: A right-handed z-up coordinate system is used. All units are in meters. Rotations are in degrees!)",
                "(NOTE: Please retain the original `uid` property of the ObjectBlueprint — it's used later for retrieving the 3D model file.",
                "(NOTE: Please assign a unique id for each object. If you want to modify the placement of an existing object, you can do so by overwriting the pos/rot/scl, while re-using the same id.)",
                # f"The shopping cart: {ctx.state.shopping_cart}"  # NOTE: not sure if needed
            ) if placement_run_count == 0 else (
                f"Placement Feedback (reason for rejection): {feedback}"
            )
            placement_response = await room_design_agent.run(
                placement_user_prompt,
                message_history=shopping_response.all_messages(),
                output_type=list[Object],
            )
            ctx.state.room.objects = placement_response.output
            
            # post-placement render
            blender.parse_room_definition(room)
            top_down_render = blender.visualize(scene=room.id, output_dir="test_output", show_grid=True)
            isometric_render = blender.visualize(
                scene=room.id, output_dir="test_output", view="isometric", show_grid=True
            )
            renders = transform_paths_to_binary([top_down_render, isometric_render])

            critique_user_prompt = (
                "Updated renders:",
                *renders,
                "Do you approve of the previous placement result?",
                "If so, please provide a rationale, and if not, please provide feedback for the PlacementAgent,", 
                "so it can address the issues in the upcoming design step.",
            )
            critique_response = await room_design_agent.run(
                critique_user_prompt,
                message_history=placement_response.all_messages(),
                output_type=CritiqueAction,
            )
            critique = critique_response.output
            if DEBUG:
                print(f"{critique.result=}")
                print(f"{critique.explanation=}")
            if critique.result == "rejected":
                feedback = critique.explanation
            elif critique.result == "approved":
                break
            placement_run_count += 1
        

        ### Inter-Agent Collaboration Logic v1 (old) ###
        # # rda2sha_prompt = "Please tell the `ShoppingAgent` what you would like to achieve in the next design step."
        # # rda2sha_prompt = "Please communicate with the `ShoppingAgent` what you would like to achieve in the next design step."
        # rda2sha_prompt = (
        #     "Please request the `ShoppingAgent` if you would like it to find specific objects from the object database.",
        #     "Your next response will be passed along to the `ShoppingAgent`.",
        # )
        # rda2sha_response = await room_design_agent.run(
        #     rda2sha_prompt, message_history=response.all_messages(), output_type=str
        # )
        # shopping_user_prompt = (
        #     f"Message from `RoomDesignAgent`: {rda2sha_response.output}"
        #     f"Room id: '{room.id}'.",
        #     f"Room category: '{room.category}'.",
        #     f"Room plan: {ctx.state.room_plan}.",
        #     f"Existing items in the shopping cart: {ctx.state.shopping_cart}",
        # )
        # # NOTE: It may be beneficial to add a state variable to control whether shopping_agent can / should be invoked,
        # #       to allow for "waterfall"-style selection → placement sequence.
        # # NOTE: For example, it can be beneficial to think of "design" and "build" separately,
        # #       where design consists of shopping and planning, and building consists of going back-and-forth
        # #       between the placement node/agent, doing quality checks via visual feedback (potentially giving
        # #       the PlacementNode some advice, although it has feedback of its own), or re-initiating motion
        # #       of certain already-place items, and then finalizing the room to end the process.
        # #       What this ultimately means is that there are probably certain parts that are to be invoked once,
        # #       and certain parts that are meant to run repetitively. It's useful to model the human design process.

        # shopping_agent_response = await shopping_agent.run(shopping_user_prompt)
        # shopping_cart = shopping_agent_response.output
        # console.print(
        #     f"[bold cyan]Added Objects:[/] {[obj.name for obj in shopping_cart]}"
        # )
        # ctx.state.shopping_cart.extend(shopping_cart)
        # # NOTE: may need to diff the shopping cart content or something, if shopping
        # #       is anything other than shopping a singular object that is immediately needed.
        # # NOTE: not sure if VLM is going to repeat existing stuff in the ShoppingCart
        # #       or skip them. (probably need to explicitly prompt to "pin" this behavior.)

        # # TEMP: choose the first item in the shopping cart
        # what_to_place = ctx.state.shopping_cart[0]

        # rda2sea_prompt = (
        #     # "Please communicate with the `SequencingAgent` what you would like to achieve in the next design step.",
        #     "Please communicate with the `SequencingAgent` what you would like to achieve (e.g., which objects to place first) in the next design step.",
        #     # "Your next response will be passed along to the `SequencingAgent`.",
        #     "Your next response will be passed along to the `SequencingAgent`. (Just respond in natural language this time!)",
        # )
        # rda2sea_response = await room_design_agent.run(
        #     rda2sea_prompt,
        #     message_history=rda2sha_response.all_messages(),
        #     output_type=str,
        # )
        # if DEBUG:
        #     print(f"[RoomDesignAgent → SequencingAgent] {rda2sea_response.output}")
        # sequencing_user_prompt = (
        #     f"Message from `RoomDesignAgent`: {rda2sea_response.output}",
        #     f"Shopping Cart: {str(ctx.state.shopping_cart)}",
        # )  # stuff to include:
        # # shopping cart content: names, thumbnails, metadata
        # # scene vizs that show room evolution history (?),
        # # ^ maybe some text that describe what was changed (like a commmit msg) is helpful?
        # # probably the room plan,
        # # probably the visual feedback content (text) from prev iter
        # sequencing_response = await sequencing_agent.run(sequencing_user_prompt)
        # sequence = sequencing_response.output
        # what_to_place = sequence[0]
        # # NOTE: if it gives a multi-length sequence, maybe let's consume it all before consulting it again
        # #       (as long as it's not unreasonable - like it specifies the whole damn shopping cart. we can do sanity checks.)
        # console.print(f"[bold cyan]Placing Next:[/] {what_to_place}")
        # # Remove the object (blueprint) from shopping cart to prevent excessive repeats
        # # NOTE: since the shopping cart does not have a quantity property, we assume quantity=1 for now
        # idx = next(
        #     (
        #         i
        #         for i, obj in enumerate(ctx.state.shopping_cart)
        #         if obj == what_to_place
        #     ),
        #     None,
        # )
        # if idx is not None:
        #     ctx.state.shopping_cart.pop(idx)

        # NOTE: It would be interesting if the room design agent can "think" of
        #       certain opinions and feed it to PlacementNode as text guidance.
        #       Like describing what it wants in natural language, based on contexts.
        #         (Then, why doesn't it do everything itself, since it knows the context already? Hmm...)

        # NOTE: Or lowkey PlacementAgent can take care of what to do (altho language comm prolly is useful & better)
        #       and we just do termination management by measuring the number of objects it add and terminating @ 1? Idk.

        # rda2pla_prompt = (
        #     "Please request the `PlacementAgent` what you would like to achieve in the next design step.",
        #     # "Your next response will be passed along to the `PlacementAgent`.",
        #     "Your next response will be passed along to the `PlacementAgent`. (Just respond in natural language this time!)",
        # )
        # rda2pla_response = await room_design_agent.run(
        #     rda2pla_prompt,
        #     message_history=rda2sea_response.all_messages(),
        #     output_type=str,
        # )
        # if DEBUG:
        #     print(f"[RoomDesignAgent → PlacementAgent] {rda2pla_response.output}")
        # placement_state = PlacementState(
        #     room=room,
        #     room_plan=ctx.state.room_plan,
        #     what_to_place=what_to_place,
        #     user_prompt=f"Message from `RoomDesignAgent`: {rda2pla_response}",
        # )

        # # PROBLEM(?): placement_graph runs for extended periods and places multiple objects.

        # placement_subgraph_response = await placement_graph.run(
        #     PlacementNode(), state=placement_state
        # )
        # updated_room: Room = placement_subgraph_response.output
        # ctx.state.room = updated_room
        # # ctx.state.room_history += new_placement_state.room_history

        # TODO: use VisualFeedback and ShoppingCart to decide if room needs more objects or end
        # NOTE: the logic should be: the room is fed to a visual feedback agent, along with information
        #       such as the remaining items in the shopping cart (that is "explorable" in terms of detail,
        #       meaning it can be as simple as how many objects are left and their names, or their thumbnails & sizes),

        # TODO: decide whether to finalize the scene, or to continue designing.
        # TODO: if deciding to continue, choose what to place next.
        ### END ###

        ### Return ###
        # TODO: if DEBUG, make it dump (latest) state & .blend to a file at every turn. or maybe all turns. for web viz.
        ctx.state.run_count += 1  # (TEMP?)
        ctx.state.message_history = critique_response.all_messages()  # TODO: confirm this is correct
        return RoomDesignNode()  # maybe this is the issue? self-returning function?
    
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


# class RoomDesignVisualFeedback(BaseNode[RoomDesignState]):
#     # NOTE: see PlacementVisualFeedback in `placement.py` for notes and design decisions.
#     # NOTE: I think this node must take care of room design termination management (e.g., invoking it).
#     async def run(self, ctx: GraphRunContext[RoomDesignState]) -> RoomDesignNode:
#         blender.parse_room_definition(ctx.state.room)
#         top_down_render = blender.create_scene_visualization(output_dir="test_output")
#         isometric_render = blender.create_scene_visualization(
#             output_dir="test_output", view="isometric"
#         )
#         ctx.state.viz.append(top_down_render)
#         ctx.state.viz.append(isometric_render)
#         return RoomDesignNode()


room_design_graph = Graph(
    nodes=[
        DesignLoopRouter,  # TEMP
        RoomDesignNode,
        # RoomDesignVisualFeedback,
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
