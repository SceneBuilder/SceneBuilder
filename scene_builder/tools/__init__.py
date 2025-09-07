"""
SceneBuilder tools for material workflow and texturing.

This module provides a complete workflow for searching materials using Graphics-DB
and applying them to Blender floor meshes created by SceneBuilder.
"""

from .graphics_db_client import GraphicsDBClient, search_and_download_materials
from .material_applicator import (
    create_diffuse_material,
    apply_material_to_object,
    texture_floor_mesh,
    find_floor_objects,
)
from .material_workflow import (
    MaterialWorkflow,
    apply_floor_material,
    texture_floor_with_material,
)

__all__ = [
    # Graphics-DB client
    "GraphicsDBClient",
    "search_and_download_materials",
    # Material applicator utilities
    "create_diffuse_material",
    "apply_material_to_object",
    "texture_floor_mesh",
    "find_floor_objects",
    # Complete workflow
    "MaterialWorkflow",
    "apply_floor_material",
    "texture_floor_with_material",
]
