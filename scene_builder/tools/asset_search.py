import base64
import requests
from typing import List, Dict

from pydantic_ai import BinaryContent

from graphics_db_server.logging import logger
from graphics_db_server.schemas.asset import Asset


API_BASE_URL = "http://localhost:2692/api/v0"


def search_assets(query: str, top_k: int = 5) -> List[Asset]:
    """
    Search for 3D assets in the graphics database using a text query.

    Args:
        query: Text description of the asset to search for
        top_k: Number of top results to return (default: 5)

    Returns:
        List of Asset objects containing asset information from the graphics database
    """
    logger.debug(f"search_assets called with query='{query}', top_k={top_k}")
    try:
        response = requests.get(
            f"{API_BASE_URL}/assets/search",
            params={"query": query, "top_k": top_k},
            timeout=30,
        )
        response.raise_for_status()

        assets_data = response.json()
        assets = [Asset(**asset) for asset in assets_data]
        logger.debug(f"search_assets returning {len(assets)} assets")
        return assets

    except requests.exceptions.RequestException as e:
        print(f"Error searching assets: {e}")
        return []
    except Exception as e:
        print(f"Unexpected error: {e}")
        return []


def get_asset_thumbnails(asset_uids: list[str]) -> dict[str, str]:
    """
    Get thumbnails for a list of asset UIDs from the graphics database.
    
    Args:
        asset_uids: List of asset UIDs to fetch thumbnails for
    
    Returns:
        Dictionary mapping asset UIDs to base64-encoded thumbnail images
    """
    logger.debug(f"get_asset_thumbnails called with {len(asset_uids)} asset_uids: {asset_uids}")
    try:
        response = requests.post(
            f"{API_BASE_URL}/assets/thumbnails",
            json={"asset_uids": asset_uids},
            timeout=30
        )
        response.raise_for_status()
        
        thumbnails = response.json()
        logger.debug(f"get_asset_thumbnails returning {len(thumbnails)} thumbnails")
        return thumbnails
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching thumbnails: {e}")
        return {}
    except Exception as e:
        print(f"Unexpected error: {e}")
        return {}


def get_asset_thumbnail(asset_uid: str) -> BinaryContent:
    """
    Get thumbnail for a single asset and return as BinaryContent object for viewing.
    
    Args:
        asset_uid: The UID of the asset to get thumbnail for
    
    Returns:
        BinaryContent object containing the thumbnail image data
    """
    logger.debug(f"get_asset_thumbnail called with asset_uid='{asset_uid}'")
    thumbnails = get_asset_thumbnails([asset_uid])
    if asset_uid in thumbnails:
        base64_data = thumbnails[asset_uid]
        try:
            image_data = base64.b64decode(base64_data)
            # NOTE could be enhanced with proper content detection
            logger.debug(f"get_asset_thumbnail returning BinaryContent for asset_uid='{asset_uid}'")
            return BinaryContent(data=image_data, media_type="image/png")
        except Exception as e:
            raise ValueError(f"Failed to decode thumbnail for asset {asset_uid}: {e}")
    else:
        raise ValueError(f"Thumbnail not found for asset {asset_uid}")
