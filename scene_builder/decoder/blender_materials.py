"""
TODO: Add docstring

TODO: refactor decoder/blender into a module (folder) instead of a single script,
      and make this file a submodule of it.
"""

import bpy

from scene_builder.logging import logger


def create_translucent_material(
    name="Translucent Material", color=(1.0, 1.0, 1.0, 1.0), alpha=0.01, roughness=0.0
):
    """
    Creates or retrieves a translucent material compatible with glTF export.
    If a material with the given name already exists, it will be returned.

    Args:
        name (str): The name of the material.
        color (tuple): The RGBA base color for the material.
        alpha (float): The transparency level (0.0 = fully transparent, 1.0 = fully opaque).
        roughness (float): The material roughness (0.0 = smooth/shiny, 1.0 = rough/matte).

    Returns:
        bpy.types.Material: The created or existing material.
    """
    # Check if the material already exists to avoid duplicates
    if name in bpy.data.materials:
        logger.debug(f"Material '{name}' already exists. Returning existing material.")
        return bpy.data.materials[name]

    # Create a new material data-block
    mat = bpy.data.materials.new(name=name)

    # Enable 'Use Nodes' for the material
    mat.use_nodes = True

    # Get a reference to the Principled BSDF shader node
    principled_bsdf = mat.node_tree.nodes.get("Principled BSDF")

    if principled_bsdf:
        # Set the material's visual properties
        principled_bsdf.inputs["Base Color"].default_value = color
        principled_bsdf.inputs["Roughness"].default_value = roughness
        principled_bsdf.inputs["Alpha"].default_value = alpha
    else:
        logger.warning(f"Could not find Principled BSDF node for material '{name}'.")
        return mat  # Return material without node changes

    # Set the blend mode (crucial for transparency to work)
    # 'BLEND' corresponds to "Alpha Blend" in the UI
    mat.blend_method = "BLEND"

    # # Optional: Set shadow mode for better-looking shadows in Eevee
    # mat.shadow_method = "HASHED"

    logger.debug(f"Successfully created translucent material: '{name}'")
    return mat
