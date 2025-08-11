import os
from pathlib import Path

from scene_builder.workflow.graph import app, room_design_subgraph

SAVE_DIR = "assets"

def test_visualize_main_graph():
    mermaid_string = app.get_graph().draw_mermaid()
    assert mermaid_string is not None
    assert len(mermaid_string) > 0
    
    with open(f"{SAVE_DIR}/main_graph.md", "w") as f:
        f.write(mermaid_string)
    
    assert os.path.exists(f"{SAVE_DIR}/main_graph.md")
    # os.remove(f"{SAVE_DIR}/main_graph.md")

def test_visualize_room_design_subgraph():
    mermaid_string = room_design_subgraph.get_graph().draw_mermaid()
    assert mermaid_string is not None
    assert len(mermaid_string) > 0
    
    with open(f"{SAVE_DIR}/room_design_subgraph.md", "w") as f:
        f.write(mermaid_string)
    
    assert os.path.exists(f"{SAVE_DIR}/room_design_subgraph.md")
    # os.remove(f"{SAVE_DIR}/room_design_subgraph.md")
