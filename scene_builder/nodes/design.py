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
            prompt = f"Design the room '{room.category}' with id '{room.id}'. The overall user request is: '{ctx.state.user_input}'. The scene plan is: {ctx.state.plan}. Use the search_assets tool to find appropriate 3D objects from the graphics database."
            "Please choose what to place next."

            shopping_cart = await shopping_agent.run(prompt)
            console.print(
                f"[bold cyan]Added Objects:[/] {[obj.name for obj in shopping_cart]}"
            )

            placement_state = PlacementState(
                room=room,
                room_plan=ctx.state.room_plan,
                what_to_place=what_to_place,
            )

            placement_subgraph_result = await placement_graph.run(
                PlacementNode(), state=placement_state
            )

            room.objects.extend(shopping_cart)
            # TODO: use VisualFeedback and ShoppingCart to decide if room needs more objects or end
            # TODO: invoke placement_graph to place object

            # TODO: don't return `UpdateScene` directly; return a room to caller (DesignLoopRouter)
            #       and let it take care of coalescing it with the entire Scene.

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
