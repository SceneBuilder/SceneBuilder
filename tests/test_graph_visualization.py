import os
from pathlib import Path

from scene_builder.workflow.graph import app, MetadataAgent

SAVE_DIR = "assets"


def test_visualize_main_graph():
    mermaid_string = app.mermaid_code(start_node=MetadataAgent)
    assert mermaid_string is not None
    assert len(mermaid_string) > 0

    with open(f"{SAVE_DIR}/main_graph.md", "w") as f:
        f.write(mermaid_string)

    assert os.path.exists(f"{SAVE_DIR}/main_graph.md")
