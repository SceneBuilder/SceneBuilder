"""
Blender material application utilities for floor texturing.
Provides diffuse material application to mesh objects.
"""

import bpy
from pathlib import Path
from typing import Optional, Dict, Any


def create_diffuse_material(
    material_name: str, texture_path: str, scale: float = 1.0
) -> Optional[str]:
    """
    Create a diffuse material in Blender.

    Args:
        material_name: Name for the material
        texture_path: Path to the diffuse texture image
        scale: UV scaling factor for texture tiling

    Returns:
        Material name if successful, None otherwise
    """
    try:
        # Check if texture file exists and try alternative paths
        original_path = Path(texture_path)
        if not original_path.exists():
            print(f"Original texture file not found: {texture_path}")

            # Try relative path in current directory
            filename = original_path.name
            relative_path = Path(filename)
            if relative_path.exists():
                texture_path = str(relative_path.absolute())
                print(f"Using relative path: {texture_path}")
            else:
                # Try in tests directory
                tests_path = Path(__file__).parent.parent.parent / "tests" / filename
                if tests_path.exists():
                    texture_path = str(tests_path.absolute())
                    print(f"Using tests directory path: {texture_path}")
                else:
                    print(f"Texture file not found in any location: {filename}")
                    return None

        # Sanitize material name (Blender has limits on material names)
        clean_name = material_name[:63]  # Blender material name limit
        clean_name = clean_name.replace(" ", "_")

        # Check if material already exists and remove it
        existing_material = bpy.data.materials.get(clean_name)
        if existing_material:
            bpy.data.materials.remove(existing_material)
            print(f"Removed existing material: {clean_name}")

        # Create material
        material = bpy.data.materials.new(name=clean_name)
        material.use_nodes = True

        # Clear default nodes
        material.node_tree.nodes.clear()

        # Add principled BSDF
        bsdf = material.node_tree.nodes.new(type="ShaderNodeBsdfPrincipled")
        bsdf.location = (0, 0)

        # Add material output
        output = material.node_tree.nodes.new(type="ShaderNodeOutputMaterial")
        output.location = (300, 0)

        # Add image texture node
        tex_image = material.node_tree.nodes.new(type="ShaderNodeTexImage")
        tex_image.location = (-300, 0)

        # Load image with error checking and absolute path conversion
        try:
            # Ensure absolute path for Blender
            abs_texture_path = str(Path(texture_path).resolve())
            print(f"Attempting to load image: {abs_texture_path}")

            # Check if image is already loaded in Blender
            existing_image = None
            for img in bpy.data.images:
                if (
                    img.filepath == abs_texture_path
                    or img.name == Path(abs_texture_path).name
                ):
                    existing_image = img
                    print(f"Found existing image in Blender: {img.name}")
                    break

            if existing_image:
                image = existing_image
            else:
                image = bpy.data.images.load(abs_texture_path)
                print(f"Loaded new image: {abs_texture_path}")

            tex_image.image = image

            # Pack the image into the blend file to ensure it's saved
            try:
                image.pack()
                print(f"Packed image into .blend file: {image.name}")
            except Exception as pack_error:
                print(f"⚠️  Warning: Could not pack image: {pack_error}")

            print(f"Successfully assigned image to texture node")
            print(f"Image size: {image.size[0]}x{image.size[1]}")
            print(f"Image format: {image.file_format}")
            print(f"Image colorspace: {image.colorspace_settings.name}")
            print(f"Image filepath: {image.filepath}")
            print(f"Image packed: {image.packed_file is not None}")
        except Exception as e:
            print(f"ERROR loading image {texture_path}: {e}")
            print(f"Attempted absolute path: {abs_texture_path}")
            return None

        # Add UV mapping 
        tex_coord = material.node_tree.nodes.new(type="ShaderNodeTexCoord")
        tex_coord.location = (-800, 0)

        if scale != 1.0:
            # Add mapping node for scaling
            mapping = material.node_tree.nodes.new(type="ShaderNodeMapping")
            mapping.location = (-600, 0)
            mapping.inputs["Scale"].default_value = (scale, scale, 1.0)

            # Connect: TexCoord UV -> Mapping -> Image Texture
            material.node_tree.links.new(
                tex_coord.outputs["UV"], mapping.inputs["Vector"]
            )
            material.node_tree.links.new(
                mapping.outputs["Vector"], tex_image.inputs["Vector"]
            )
        else:
            # Direct connection without scaling
            material.node_tree.links.new(
                tex_coord.outputs["UV"], tex_image.inputs["Vector"]
            )

        # Connect nodes with error checking
        try:
            material.node_tree.links.new(
                tex_image.outputs["Color"], bsdf.inputs["Base Color"]
            )
            material.node_tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
            print(f"Successfully connected shader nodes for material: {clean_name}")
        except Exception as e:
            print(f"ERROR connecting shader nodes: {e}")
            print(
                f"Available tex_image outputs: {[out.name for out in tex_image.outputs]}"
            )
            print(f"Available bsdf inputs: {[inp.name for inp in bsdf.inputs]}")
            return None

        # viewport to show materials properly
        try:
            # Set all 3D viewports to Material Preview mode
            for window in bpy.context.window_manager.windows:
                screen = window.screen
                for area in screen.areas:
                    if area.type == "VIEW_3D":
                        for space in area.spaces:
                            if space.type == "VIEW_3D":
                                space.shading.type = "MATERIAL"
                                # Ensure we're using the correct color mode for materials
                                if hasattr(space.shading, "color_type"):
                                    space.shading.color_type = "MATERIAL"
                                print(f"Set viewport shading to Material Preview mode")
                                break
        except Exception as e:
            print(f"Warning: Could not set viewport shading: {e}")

        print(f"Created material: {clean_name}")
        return clean_name

    except Exception as e:
        print(f"Error creating material {material_name}: {e}")
        return None


def apply_material_to_object(object_name: str, material_name: str) -> bool:
    """
    Apply a material to a Blender object.

    Args:
        object_name: Name of the Blender object
        material_name: Name of the material to apply

    Returns:
        True if successful, False otherwise
    """
    try:
        # Get object
        obj = bpy.data.objects.get(object_name)
        if not obj:
            print(f"Object not found: {object_name}")
            return False

        # Get material
        material = bpy.data.materials.get(material_name)
        if not material:
            print(f"Material not found: {material_name}")
            # Debug: show available materials
            available_materials = [mat.name for mat in bpy.data.materials]
            print(f"Available materials: {available_materials}")
            return False

        # Apply material
        if obj.data.materials:
            obj.data.materials[0] = material
        else:
            obj.data.materials.append(material)

        print(f"Applied material '{material_name}' to object '{object_name}'")
        return True

    except Exception as e:
        print(f"Error applying material to {object_name}: {e}")
        return False


def texture_floor_mesh(
    floor_object_name: str,
    texture_path: str,
    material_name: Optional[str] = None,
    uv_scale: float = 2.0,
) -> bool:
    """
    Apply a diffuse texture to a floor mesh object.

    Args:
        floor_object_name: Name of the floor object in Blender
        texture_path: Path to the texture image file
        material_name: Custom material name (auto-generated if None)
        uv_scale: UV scaling for texture tiling (higher = more repetitions)

    Returns:
        True if successful, False otherwise
    """
    try:
        # Generate material name if not provided
        if material_name is None:
            texture_name = Path(texture_path).stem
            # Create shorter, cleaner material name
            clean_floor_name = floor_object_name.replace("Floor_", "").split("_")[0]
            material_name = f"Mat_{texture_name}_{clean_floor_name}"

        # Create material
        created_material = create_diffuse_material(
            material_name, texture_path, uv_scale
        )
        if not created_material:
            return False

        # Apply to object
        success = apply_material_to_object(floor_object_name, created_material)

        if success:
            print(
                f"Successfully textured floor '{floor_object_name}' with '{texture_path}'"
            )

        return success

    except Exception as e:
        print(f"Error texturing floor mesh: {e}")
        return False


def find_floor_objects() -> list[str]:
    """
    Find all floor objects in the current Blender scene.

    Returns:
        List of floor object names
    """
    floor_objects = []

    # Look for objects in Floor collection
    floors_collection = bpy.data.collections.get("Floor")
    if floors_collection:
        for obj in floors_collection.objects:
            if obj.type == "MESH":
                floor_objects.append(obj.name)

    # Also look for objects with "Floor" in the name
    for obj in bpy.data.objects:
        if obj.type == "MESH" and "Floor" in obj.name and obj.name not in floor_objects:
            floor_objects.append(obj.name)

    return floor_objects
