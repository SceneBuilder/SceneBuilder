import os
from pathlib import Path

from scene_builder.workflow.graph import app, MetadataAgent
from scene_builder.utils.markdown import wrap_in_code_block

SAVE_DIR = "assets"


def test_visualize_main_graph():
    mermaid_string = app.mermaid_code(start_node=MetadataAgent)
    assert mermaid_string is not None
    assert len(mermaid_string) > 0

    with open(f"{SAVE_DIR}/main_graph.md", "w") as f:
        f.write(wrap_in_code_block(mermaid_string, "mermaid"))

    assert os.path.exists(f"{SAVE_DIR}/main_graph.md")
