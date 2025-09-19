from pydantic_graph import BaseNode, GraphRunContext
from rich.console import Console

from scene_builder.definition.scene import Room
# from scene_builder.nodes.routing import DesignLoopRouter
from scene_builder.nodes.design import DesignLoopRouter
from scene_builder.workflow.agents import floor_plan_agent, planning_agent
from scene_builder.workflow.states import MainState

console = Console()


class FloorPlanNode(BaseNode[MainState]):
    async def run(self, ctx: GraphRunContext[MainState]) -> DesignLoopRouter:
        console.print("[bold cyan]Executing Node:[/] Floor Plan Node")
        is_debug = ctx.state.global_config and ctx.state.global_config.debug

        if is_debug:
            console.print("[bold yellow]Debug mode: Using hardcoded floor plan.[/]")
            living_room = Room(
                id="living_room_1", category="living_room", tags=["main"], objects=[]
            )
            ctx.state.scene_definition.rooms.append(living_room)
        else:
            console.print(
                "[bold green]Production mode: Generating floor plan via LLM.[/]"
            )
            generated_rooms = await floor_plan_agent.run(
                f"Create rooms for the following plan: {ctx.state.plan}"
            )
            ctx.state.scene_definition.rooms.extend(generated_rooms)
            console.print(
                f"[bold cyan]Generated Rooms:[/] {[room.id for room in generated_rooms]}"
            )

        return DesignLoopRouter()


class BuildingPlanNode(BaseNode[MainState]):
    async def run(self, ctx: GraphRunContext[MainState]) -> FloorPlanNode:
        console.print("[bold cyan]Executing Node:[/] Scene Planning Node")
        is_debug = ctx.state.global_config and ctx.state.global_config.debug

        if is_debug:
            console.print("[bold yellow]Debug mode: Using hardcoded scene plan.[/]")
            ctx.state.plan = "1. Create a living room.\n2. Add a sofa."
        else:
            console.print(
                "[bold green]Production mode: Generating scene plan via LLM.[/]"
            )
            response = await planning_agent.run(ctx.state.user_input)
            ctx.state.plan = response.content
            console.print(f"[bold cyan]Generated Plan:[/] {ctx.state.plan}")

        return FloorPlanNode()
