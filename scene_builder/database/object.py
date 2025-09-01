import base64
import requests
from typing import Any

from pydantic import TypeAdapter, ValidationError
from pydantic_ai import BinaryContent

from graphics_db_server.logging import logger
from graphics_db_server.schemas.asset import Asset

from scene_builder import API_BASE_URL
from scene_builder.definition.scene import ObjectBlueprint
# from scene_builder.utils.conversions import rename_key


AssetListAdapter = TypeAdapter(list[Asset])


class ObjectDatabase:
    """
    A wrapper for a 3D object database (e.g., Objaverse) that can
    operate in either debug (mock data) or production (real data) mode.
    """

    def __init__(self):
        """
        Initializes the ObjectDatabase.
        """
        pass

    def query(self, query: str, top_k: int = 5) -> list[ObjectBlueprint]:
        """
        Queries the 3D object database.

        Args:
            query: The search query (e.g., "a red sofa").
            top_k: Number of top results to return (default: 5).

        Returns:
            A list object blueprints.
        """
        logger.debug(f"ObjectDatabase.query called with query='{query}', top_k={top_k}")
        response = requests.get(
            f"{API_BASE_URL}/v0/assets/search",
            params={"query": query,
                    "top_k": top_k,
                    "validate_scale": True},
            timeout=90,
        )
        try:
            response.raise_for_status()
            assets = AssetListAdapter.validate_json(response.text)
            # assets = AssetListAdapter.validate_json(response.text.replace("uid", "source_id"))
            results = []
            for asset in assets:
                results.append(
                    ObjectBlueprint(
                        # name=None,
                        name=asset.uid,  # TEMP HACK
                        source_id=asset.uid,
                        # source=asset.source,
                        source="objaverse",  # TEMP HACK
                        description="",  # TODO: use VLM to add desc, or source from DB?
                        extra_info={"tags": asset.tags},
                    )
                )
            logger.debug(f"ObjectDatabase.query returning {len(results)} object blueprints")
            return results
        # TODO: replace exception messages with logger calls
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            return []
        except ValidationError as e:
            print(f"Data validation failed: {e}")
            return []

    def get_asset_thumbnails(self, asset_uids: list[str]) -> dict[str, str]:
        """
        Get thumbnails for a list of asset UIDs from the graphics database.
        
        Args:
            asset_uids: List of asset UIDs to fetch thumbnails for
        
        Returns:
            Dictionary mapping asset UIDs to base64-encoded thumbnail images
        """
        logger.debug(f"ObjectDatabase.get_asset_thumbnails called with {len(asset_uids)} asset_uids: {asset_uids}")
        try:
            response = requests.post(
                f"{API_BASE_URL}/v0/assets/thumbnails",
                json={"asset_uids": asset_uids},
                timeout=30
            )
            response.raise_for_status()
            
            thumbnails = response.json()
            logger.debug(f"ObjectDatabase.get_asset_thumbnails returning {len(thumbnails)} thumbnails")
            return thumbnails
            
        except requests.exceptions.RequestException as e:
            print(f"Error fetching thumbnails: {e}")
            return {}
        except Exception as e:
            print(f"Unexpected error: {e}")
            return {}

    def get_asset_thumbnail(self, asset_uid: str) -> BinaryContent:
        """
        Get thumbnail for a single asset and return as BinaryContent object for viewing.
        
        Args:
            asset_uid: The UID of the asset to get thumbnail for
        
        Returns:
            BinaryContent object containing the thumbnail image data
        """
        logger.debug(f"ObjectDatabase.get_asset_thumbnail called with asset_uid='{asset_uid}'")
        thumbnails = self.get_asset_thumbnails([asset_uid])
        if asset_uid in thumbnails:
            base64_data = thumbnails[asset_uid]
            try:
                image_data = base64.b64decode(base64_data)
                # NOTE could be enhanced with proper content detection
                logger.debug(f"ObjectDatabase.get_asset_thumbnail returning BinaryContent for asset_uid='{asset_uid}'")
                return BinaryContent(data=image_data, media_type="image/png")
            except Exception as e:
                raise ValueError(f"Failed to decode thumbnail for asset {asset_uid}: {e}")
        else:
            raise ValueError(f"Thumbnail not found for asset {asset_uid}")
