import requests
from typing import List

from graphics_db_server.schemas.asset import Asset

# Assuming the graphics database server runs locally on port 8000
API_BASE_URL = "http://localhost:8000/api/v0"


def search_assets(query: str, top_k: int = 5) -> List[Asset]:
    """
    Search for 3D assets in the graphics database using a text query.

    Args:
        query: Text description of the asset to search for
        top_k: Number of top results to return (default: 5)

    Returns:
        List of Asset objects containing asset information from the graphics database
    """
    try:
        response = requests.get(
            f"{API_BASE_URL}/assets/search",
            params={"query": query, "top_k": top_k},
            timeout=30,
        )
        response.raise_for_status()

        assets_data = response.json()
        return [Asset(**asset) for asset in assets_data]

    except requests.exceptions.RequestException as e:
        print(f"Error searching assets: {e}")
        return []
    except Exception as e:
        print(f"Unexpected error: {e}")
        return []
