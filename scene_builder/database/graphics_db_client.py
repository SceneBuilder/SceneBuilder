"""
Graphics-DB API client for material search and download.
Provides a simple interface to the Graphics-DB material search API.
"""

import requests
from pathlib import Path
from typing import Dict, List, Optional, Any


class GraphicsDBClient:
    """Client for interacting with Graphics-DB material search API."""

    def __init__(self, base_url: str = "http://localhost:2692/api/v0"):
        """
        Initialize the Graphics-DB client.

        Args:
            base_url: Base URL for the Graphics-DB API
        """
        self.base_url = base_url.rstrip("/")
        self.cache_dir = Path.home() / ".scenebuilder_materials"
        self.cache_dir.mkdir(exist_ok=True)

    def search_materials(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Search for materials using natural language query.

        Args:
            query: Natural language description (e.g., "wood floor parquet")
            top_k: Number of results to return

        Returns:
            List of material dictionaries with uid, tags, etc.
        """
        try:
            url = f"{self.base_url}/materials/search"
            params = {"query": query, "top_k": top_k}

            response = requests.get(url, params=params)
            response.raise_for_status()

            materials = response.json()
            print(f"Found {len(materials)} materials for query: '{query}'")

            return materials

        except requests.RequestException as e:
            print(f"Error searching materials: {e}")
            return []

    def download_diffuse_texture(self, material_uid: str) -> Optional[str]:
        """
        Download diffuse texture for a material UID.

        Args:
            material_uid: Unique identifier for the material

        Returns:
            Local file path to the downloaded texture, or None if failed
        """
        try:
            # Check if already cached
            cached_path = self.cache_dir / f"{material_uid}_diffuse.jpg"
            if cached_path.exists():
                print(f"Using cached texture: {cached_path}")
                return str(cached_path)

            # Download from API
            url = f"{self.base_url}/materials/download/{material_uid}/diffuse"
            response = requests.get(url)
            response.raise_for_status()

            # Save to cache
            with open(cached_path, "wb") as f:
                f.write(response.content)

            print(f"Downloaded texture: {cached_path}")
            return str(cached_path)

        except requests.RequestException as e:
            print(f"Error downloading texture for {material_uid}: {e}")
            return None

    def get_material_metadata(self, material_uid: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a material.

        Args:
            material_uid: Unique identifier for the material

        Returns:
            Material metadata dictionary or None if failed
        """
        try:
            url = f"{self.base_url}/materials/{material_uid}/metadata"
            response = requests.get(url)
            response.raise_for_status()

            return response.json()

        except requests.RequestException as e:
            print(f"Error getting metadata for {material_uid}: {e}")
            return None


def search_and_download_materials(query: str, top_k: int = 3) -> List[Dict[str, str]]:
    """
    Convenience function to search and download materials in one step.

    Args:
        query: Natural language material description
        top_k: Number of materials to download

    Returns:
        List of dictionaries with 'uid' and 'texture_path' keys
    """
    client = GraphicsDBClient()

    # Search for materials
    materials = client.search_materials(query, top_k)
    if not materials:
        print(f"No materials found for query: '{query}'")
        return []

    # Download textures
    results = []
    for material in materials:
        material_uid = material["uid"]
        texture_path = client.download_diffuse_texture(material_uid)

        if texture_path:
            results.append(
                {
                    "uid": material_uid,
                    "texture_path": texture_path,
                    "tags": material.get("tags", []),
                    "source": material.get("source", "unknown"),
                }
            )

    print(f"Successfully downloaded {len(results)} textures")
    return results
