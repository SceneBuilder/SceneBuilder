from pydantic_graph import Graph

from scene_builder.definition.scene import Room
from scene_builder.nodes.design import RoomDesignNode, RoomDesignVisualFeedback
# from scene_builder.nodes.feedback import VisualFeedback
from scene_builder.nodes.design import DesignLoopRouter  # TEMP
from scene_builder.nodes.general import MetadataNode, UpdateScene
from scene_builder.nodes.placement import PlacementNode, PlacementVisualFeedback
from scene_builder.nodes.planning import BuildingPlanNode, FloorPlanNode
# from scene_builder.nodes.routing import DesignLoopRouter
from scene_builder.workflow.states import MainState, PlacementState


# NOTE Code formatting: generally in sequential order

main_graph = Graph(
    nodes=[
        MetadataNode,
        BuildingPlanNode,
        FloorPlanNode,
        DesignLoopRouter,
        RoomDesignNode,
        RoomDesignVisualFeedback,  # TEMP?
        UpdateScene,
        PlacementVisualFeedback,  # TEMP
        PlacementNode,  # TEMP
    ],
    state_type=MainState,
)

# room_design_graph = Graph(
#     nodes=[
#         RoomDesignNode,
#         VisualFeedback,
#     ],
#     state_type=Room,
# )

# placement_graph = Graph(
#     nodes=[
#         PlacementNode,
#         VisualFeedback,
#     ],
#     state_type=PlacementState,  # hmm
# )
