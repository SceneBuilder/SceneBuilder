import os
from pathlib import Path

# from scene_builder.nodes.general import MetadataNode
from scene_builder.nodes.placement import PlacementNode, placement_graph
# from scene_builder.nodes.design import room_design_graph
from scene_builder.nodes.design import room_design_graph, DesignLoopRouter
# from scene_builder.nodes.routing import DesignLoopRouter
from scene_builder.workflow.graphs import (
    app,
    # placement_graph,
    # room_design_graph,
)
from scene_builder.utils.markdown import wrap_in_code_block

SAVE_DIR = "assets"


# def test_visualize_main_graph():
#     mermaid_string = app.mermaid_code(start_node=MetadataNode)
#     assert mermaid_string is not None
#     assert len(mermaid_string) > 0

#     with open(f"{SAVE_DIR}/main_graph.md", "w") as f:
#         f.write(wrap_in_code_block(mermaid_string, "mermaid"))

#     assert os.path.exists(f"{SAVE_DIR}/main_graph.md")


def test_visualize_placement_graph():
    mermaid_string = placement_graph.mermaid_code(start_node=PlacementNode)
    assert mermaid_string is not None
    assert len(mermaid_string) > 0

    with open(f"{SAVE_DIR}/placement_graph.md", "w") as f:
        f.write(wrap_in_code_block(mermaid_string, "mermaid"))

    assert os.path.exists(f"{SAVE_DIR}/placement_graph.md")


def test_visualize_room_design_graph():
    mermaid_string = room_design_graph.mermaid_code(start_node=DesignLoopRouter)
    assert mermaid_string is not None
    assert len(mermaid_string) > 0

    with open(f"{SAVE_DIR}/room_design_graph.md", "w") as f:
        f.write(wrap_in_code_block(mermaid_string, "mermaid"))

    assert os.path.exists(f"{SAVE_DIR}/room_design_graph.md")

if __name__ == "__main__":
    # test_visualize_main_graph()
    test_visualize_placement_graph()
    test_visualize_room_design_graph()
