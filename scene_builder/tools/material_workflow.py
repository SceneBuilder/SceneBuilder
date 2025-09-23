"""
Complete material workflow for floor texturing.
Integrates Graphics-DB search with Blender material application.
"""

from typing import List, Optional, Dict, Any
from pathlib import Path

from .graphics_db_client import GraphicsDBClient, search_and_download_materials
from .material_applicator import texture_floor_mesh, find_floor_objects

BASE_UV_SCALE = 30.0  # reference target to use for textures (TEMP)


class MaterialWorkflow:
    """Complete workflow for searching and applying materials to floor meshes."""

    def __init__(self, graphics_db_url: str = "http://localhost:2692/api/v0"):
        """
        Initialize the material workflow.

        Args:
            graphics_db_url: URL for the Graphics-DB API
        """
        self.client = GraphicsDBClient(graphics_db_url)

    def texture_floors_with_query(
        self,
        query: str,
        floor_objects: Optional[List[str]] = None,
        uv_scale: float = 2.0,  # 변경해가면서
        material_index: int = 0,
    ) -> Dict[str, Any]:
        """
        Search for materials and apply to floor objects.

        Args:
            query: Natural language material description (e.g., "wood floor parquet")
            floor_objects: List of floor object names (auto-detected if None)
            uv_scale: UV scaling for texture tiling
            material_index: Which search result to use (0 = best match)

        Returns:
            Dictionary with results and status information
        """
        results = {
            "success": False,
            "query": query,
            "materials_found": 0,
            "floors_textured": 0,
            "textured_objects": [],
            "errors": [],
        }

        try:
            # Find floor objects if not provided
            if floor_objects is None:
                floor_objects = find_floor_objects()
                print(f"Auto-detected floor objects: {floor_objects}")

            if not floor_objects:
                results["errors"].append("No floor objects found in scene")
                return results

            # Search for materials
            materials = self.client.search_materials(query, top_k=5)
            results["materials_found"] = len(materials)

            if not materials:
                results["errors"].append(f"No materials found for query: '{query}'")
                return results

            # Use the specified material (default to best match)
            if material_index >= len(materials):
                material_index = 0

            selected_material = materials[material_index]
            material_uid = selected_material["uid"]

            print(
                f"Selected material: {material_uid} (tags: {selected_material.get('tags', [])})"
            )

            # Download texture
            texture_path = self.client.download_diffuse_texture(material_uid)
            if not texture_path:
                results["errors"].append(
                    f"Failed to download texture for material: {material_uid}"
                )
                return results

            # Apply texture to all floor objects
            for floor_name in floor_objects:
                success = texture_floor_mesh(
                    floor_object_name=floor_name,
                    texture_path=texture_path,
                    uv_scale=uv_scale,
                )

                if success:
                    results["textured_objects"].append(floor_name)
                    results["floors_textured"] += 1
                else:
                    results["errors"].append(f"Failed to texture floor: {floor_name}")

            results["success"] = results["floors_textured"] > 0
            results["material_uid"] = material_uid
            results["texture_path"] = texture_path

        except Exception as e:
            results["errors"].append(f"Workflow error: {str(e)}")

        return results

    def texture_specific_floor(
        self,
        floor_object_name: str,
        query: str,
        uv_scale: float = 2.0,
        material_index: int = 0,
    ) -> bool:
        """
        Texture a specific floor object with a material search query.

        Args:
            floor_object_name: Name of the floor object to texture
            query: Material search query
            uv_scale: UV scaling factor
            material_index: Which search result to use

        Returns:
            True if successful, False otherwise
        """
        result = self.texture_floors_with_query(
            query=query,
            floor_objects=[floor_object_name],
            uv_scale=uv_scale,
            material_index=material_index,
        )

        return result["success"]


def apply_floor_material(
    query: str,
    uv_scale: Optional[float] = None,
    boundary: Optional[List] = None
) -> Dict[str, Any]:
    """
    Function to search and apply a material to all floor objects.
    If boundary is provided, calculates appropriate UV scale automatically.

    Args:
        query: Material search query (e.g., "wood floor parquet")
        uv_scale: UV scaling for texture tiling (optional if boundary provided)
        boundary: List of Vector2 points for UV scale calculation

    Returns:
        Results dictionary with status information
    """
    from ..decoder import blender

    # Calculate UV scale from boundary if provided
    if boundary is not None and uv_scale is None:
        # Convert boundary points to tuples for _calculate_bounds
        boundary_tuples = []
        for point in boundary:
            if hasattr(point, "x"):  # Vector2 object
                boundary_tuples.append((point.x, point.y))
            else:  # Dictionary format
                boundary_tuples.append((point["x"], point["y"]))

        bounds = blender._calculate_bounds(boundary_tuples)
        current_size = max(bounds["width"], bounds["height"])
        reference_size = 10.0  # 10x10 room -> uv_scale=30.0 base
        reference_uv_scale = 30.0
        calculated_uv_scale = reference_uv_scale * (current_size / reference_size)
        uv_scale = calculated_uv_scale
    elif uv_scale is None:
        # Default UV scale if neither boundary nor uv_scale provided
        uv_scale = 2.0

    workflow = MaterialWorkflow()
    return workflow.texture_floors_with_query(query, uv_scale=uv_scale)


def texture_floor_with_material(
    floor_name: str, query: str, uv_scale: float = 2.0
) -> bool:
    """
    function to texture a specific floor with a material.

    Args:
        floor_name: Name of the floor object
        query: Material search query
        uv_scale: UV scaling factor

    Returns:
        True if successful, False otherwise
    """
    workflow = MaterialWorkflow()
    return workflow.texture_specific_floor(floor_name, query, uv_scale)
