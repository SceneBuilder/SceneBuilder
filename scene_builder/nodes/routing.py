import asyncio

from pydantic_graph import BaseNode, End, Graph, GraphRunContext
# from rich.console import Console

from scene_builder.definition.scene import Scene, Room
# # from scene_builder.nodes.design import RoomDesignNode
from scene_builder.nodes.design import RoomDesignNode, room_design_graph
# from scene_builder.nodes.placement import PlacementNode, VisualFeedback
from scene_builder.utils.room import recenter_room, restore_origin
# # from scene_builder.workflow.graphs import room_design_graph
from scene_builder.workflow.states import RoomDesignState


# console = Console()


# NOTE: The routers (for now, RoomDesignRouter) has moved to files with respective
#       nodes to deal with circular dependency.

# class MultiRoomDesignOrchestrator(BaseNode[list[Room]]):
#     async def run(self, ctx: GraphRunContext[list[Room]]) -> End[list[Room]]:
class MultiRoomDesignOrchestrator(BaseNode[list[RoomDesignState]]):
    # async def run(self, ctx: GraphRunContext[list[RoomDesignState]]) -> End[list[RoomDesignState]]:
    async def run(self, ctx: GraphRunContext[list[RoomDesignState]]) -> End[list[Room]]:
        # Perform origin normalization, design in parallel, then restore origins
        # centered_rooms = [recenter_room(room) for room in ctx.state]
        # centered_rooms = [recenter_room(rds.room) for rds in ctx.state]
        centered_room_design_state = [
            rds.model_copy(update={"room": recenter_room(rds.room)}) for rds in ctx.state
        ]
        results = await asyncio.gather(
            # *[room_design_graph.run(RoomDesignNode(), state=room) for room in centered_rooms]
            *[room_design_graph.run(RoomDesignNode(), state=room) for room in centered_room_design_state]
        )
        designed_rooms = [restore_origin(result.output) for result in results]

        return End(designed_rooms)
