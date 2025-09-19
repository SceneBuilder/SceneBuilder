from pydantic_graph import BaseNode, GraphRunContext
from rich.console import Console

from scene_builder.definition.scene import Scene
from scene_builder.nodes.planning import BuildingPlanNode
# from scene_builder.nodes.routing import DesignLoopRouter
from scene_builder.nodes.design import DesignLoopRouter
from scene_builder.workflow.states import MainState


console = Console()


class MetadataNode(BaseNode[MainState]):
    async def run(self, ctx: GraphRunContext[MainState]) -> BuildingPlanNode:
        console.print("[bold cyan]Executing Node:[/] Metadata Node")
        initial_scene = Scene(
            category="residential",
            tags=["modern", "minimalist"],
            floorType="single",
            rooms=[],
        )
        ctx.state.scene_definition = initial_scene
        return BuildingPlanNode()


class UpdateScene(BaseNode[MainState]):
    async def run(self, ctx: GraphRunContext[MainState]) -> DesignLoopRouter:
        """Merges the result from the room design subgraph back into the main state."""
        console.print("[bold cyan]Executing Node:[/] update_main_state_after_design")
        # The room has already been modified in place by RoomDesignNode
        # Just increment the counter to move to the next room
        ctx.state.current_room_index += 1
        return DesignLoopRouter()
