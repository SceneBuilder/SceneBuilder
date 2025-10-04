"""
Material database for querying and downloading materials.
Similar to ObjectDatabase - provides search interface without Blender dependencies.
"""

from typing import List, Optional, Dict, Any

from scene_builder.database.graphics_db_client import GraphicsDBClient


class MaterialDatabase:
    """
    A wrapper for a material database (Graphics-DB) that can
    query and download materials without Blender dependencies.
    """

    def __init__(self, graphics_db_url: str = "http://localhost:2692/api/v0"):
        """
        Initialize the MaterialDatabase.

        Args:
            graphics_db_url: URL for the Graphics-DB API
        """
        self.client = GraphicsDBClient(graphics_db_url)

    def query(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Query the material database.

        Args:
            query: Natural language description (e.g., "wood floor parquet")
            top_k: Number of top results to return (default: 5)

        Returns:
            List of material dictionaries with uid, tags, etc.
        """
        return self.client.search_materials(query, top_k=top_k)

    def download_texture(self, material_uid: str) -> Optional[str]:
        """
        Download diffuse texture for a material.

        Args:
            material_uid: Unique identifier for the material

        Returns:
            Local file path to downloaded texture, or None if failed
        """
        return self.client.download_diffuse_texture(material_uid)

    def get_metadata(self, material_uid: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a material.

        Args:
            material_uid: Unique identifier for the material

        Returns:
            Material metadata dictionary or None if failed
        """
        return self.client.get_material_metadata(material_uid)
