from __future__ import annotations

from pydantic_graph import BaseNode, GraphRunContext

from scene_builder.decoder.blender import blender
from scene_builder.nodes.placement import PlacementNode
from scene_builder.utils.conversions import pydantic_to_dict
from scene_builder.workflow.states import PlacementState


# NOTE: The Feedback nodes have moved to files with respective nodes to deal with
#       circular dependency.