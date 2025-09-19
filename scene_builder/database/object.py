import requests
from typing import Any

from pydantic import TypeAdapter, ValidationError
from graphics_db_server.schemas.asset import Asset

from scene_builder import API_BASE_URL
from scene_builder.definition.scene import ObjectBlueprint
from scene_builder.utils.conversions import rename_key


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

    def query(self, query: str) -> list[ObjectBlueprint]:
        """
        Queries the 3D object database.

        Args:
            query: The search query (e.g., "a red sofa").

        Returns:
            A list object blueprints.
        """
        response = requests.get(
            f"{API_BASE_URL}/v0/assets/search",
            params={"query": query,
                    "validate_scale": True},
        )
        try:
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
        # TODO: replace exception messages with logger calls
        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
        except ValidationError as e:
            print(f"Data validation failed: {e}")

        return results
