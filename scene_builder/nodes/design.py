from pydantic import BaseModel, Field
from pydantic_graph import BaseNode, End, Graph, GraphRunContext
from rich.console import Console

from scene_builder.database.object import ObjectDatabase
# from scene_builder.definition.scene import Object, Room, Vector3
from scene_builder.definition.scene import Object, Room, Scene, Vector3
# from scene_builder.nodes.feedback import VisualFeedback
# from scene_builder.nodes.placement import PlacementNode, VisualFeedback
from scene_builder.nodes.placement import PlacementNode, VisualFeedback, placement_graph
# from scene_builder.nodes.routing import DesignLoopRouter
from scene_builder.workflow.agents import room_design_agent, shopping_agent
# from scene_builder.workflow.graphs import placement_graph # hopefully no circular import... -> BRUH.
# from scene_builder.workflow.states import PlacementState, RoomDesignState
from scene_builder.workflow.states import PlacementState, RoomDesignState, MainState


console = Console()


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
    ) -> VisualFeedback | End[Room]:
        console.print("[bold cyan]Executing Node:[/] RoomDesignNode")
        is_debug = ctx.state.global_config and ctx.state.global_config.debug
        db = ObjectDatabase(debug=is_debug)

        room = ctx.state.room

        if is_debug:  # mock data
            console.print("[bold yellow]Debug mode: Using hardcoded object data.[/]")
            sofa_data = db.query("a modern sofa")[0]
            new_object = Object(
                id=sofa_data["id"],
                name=sofa_data["name"],
                description=sofa_data["description"],
                source=sofa_data["source"],
                source_id=sofa_data["id"],
                position=Vector3(x=0, y=0, z=0),
                rotation=Vector3(x=0, y=0, z=0),
                scale=Vector3(x=1, y=1, z=1),
            )
            room.objects.append(new_object)
        else:  # prod: real data
            # NOTE: It may be beneficial to add a state variable to control whether shopping_agent can / should be invoked,
            #       to allow for "waterfall"-style selection → placement sequence.
            shopping_prompt = f"You are part of a system that is designing the room '{room.category}' with id '{room.id}'. The overall user request is: '{ctx.state.user_input}'. The scene plan is: {ctx.state.plan}. Use the search_assets tool to find appropriate 3D objects from the graphics database."
            # NOTE: For example, it can be beneficial to think of "design" and "build" separately,
            #       where design consists of shopping and planning, and building consists of going back-and-forth
            #       between the placement node/agent, doing quality checks via visual feedback (potentially giving the PlacementNode some advice,
            #       although it has feedback of its own), or re-initiating motion of certain already-place items,
            #       and then finalizing the room to end the process.

            #       What this ultimately means is that there are probably certain parts that are to be invoked once,
            #       and certain parts that are meant to run repetitively. It's useful to model the human design process.

            shopping_cart = await shopping_agent.run(shopping_prompt)
            console.print(
                f"[bold cyan]Added Objects:[/] {[obj.name for obj in shopping_cart]}"
            )
            # NOTE: may need to diff the shopping cart content or something

            # TODO: ask VLM what to deliberately think about what to place first
            # (in general, larger "anchor" objects first, so that other objects can
            # be placed relative to it.)
            "Please choose what to place next."
            what_to_place = NotImplementedError()

            # NOTE: It would be interesting if the room design agent can "think" of
            #       certain opinions and feed it to PlacementNode as text guidance.
            placement_state = PlacementState(
                room=room,
                room_plan=ctx.state.room_plan,
                what_to_place=what_to_place,
            )

            # TODO: invoke placement_graph to place object
            placement_subgraph_result = await placement_graph.run(
                PlacementNode(), state=placement_state
            )

            # room.objects.extend(shopping_cart)
            # TODO: use VisualFeedback and ShoppingCart to decide if room needs more objects or end
            # NOTE: the logic should be: the room is fed to a visual feedback agent, along with information
            #       such as the remaining items in the shopping cart (that is "explorable" in terms of detail,
            #       meaning it can be as simple as how many objects are left and their names, or their thumbnails & sizes),
            #

            return VisualFeedback

            # TODO: don't return `UpdateScene` directly; return a room to caller (DesignLoopRouter)
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


room_design_graph = Graph(
    nodes=[
        DesignLoopRouter,  # TEMP
        RoomDesignNode,
        VisualFeedback,  # TEMP
        PlacementNode,  # TEMP
    ],
    state_type=Room,
)
