import base64
import requests
from typing import Any

from pydantic import TypeAdapter, ValidationError
from pydantic_ai import BinaryContent

from graphics_db_server.logging import logger
from graphics_db_server.schemas.asset import Asset

from scene_builder.config import GDB_API_BASE_URL
from scene_builder.definition.scene import ObjectBlueprint
from scene_builder.utils.pai import transform_markdown_to_messages


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
            f"{GDB_API_BASE_URL}/v0/objects/search",
            params={"query": query,
                    "top_k": top_k,
                    "validate_scale": True},
            timeout=90,
        )
        try:
            response.raise_for_status()
            assets = AssetListAdapter.validate_json(response.text)
            # assets = AssetListAdapter.validate_json(response.text.replace("uid", "source_id"))
            thumbnails = requests.post(
                f"{GDB_API_BASE_URL}/v0/objects/thumbnails",
                json={"uids": [asset.uid for asset in assets]},
            ).json()
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
                        extra_info={
                            "tags": asset.tags,
                            "thumbnails": [thumbnails[asset.uid]],
                        },
                    )
                )
            logger.debug(
                f"ObjectDatabase.query returning {len(results)} object blueprints"
            )
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
        logger.debug(
            f"ObjectDatabase.get_asset_thumbnails called with {len(asset_uids)} asset_uids: {asset_uids}"
        )
        try:
            response = requests.post(
                f"{GDB_API_BASE_URL}/v0/objects/thumbnails",
                json={"uids": asset_uids},
                timeout=30
            )
            response.raise_for_status()

            thumbnails = response.json()
            logger.debug(
                f"ObjectDatabase.get_asset_thumbnails returning {len(thumbnails)} thumbnails"
            )
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
        logger.debug(
            f"ObjectDatabase.get_asset_thumbnail called with asset_uid='{asset_uid}'"
        )
        thumbnails = self.get_asset_thumbnails([asset_uid])
        if asset_uid in thumbnails:
            base64_data = thumbnails[asset_uid]
            try:
                image_data = base64.b64decode(base64_data)
                # NOTE could be enhanced with proper content detection
                logger.debug(
                    f"ObjectDatabase.get_asset_thumbnail returning BinaryContent for asset_uid='{asset_uid}'"
                )
                return BinaryContent(data=image_data, media_type="image/png")
            except Exception as e:
                raise ValueError(
                    f"Failed to decode thumbnail for asset {asset_uid}: {e}"
                )
        else:
            raise ValueError(f"Thumbnail not found for asset {asset_uid}")

    # def generate_report(query_text, output_dir: Path = "logs") -> str:  # TEMP TODO: import dir from config
    def search(
        self, query_text: str, for_vlm=True
    ) -> str | list[str | BinaryContent]:  # TEMP TODO: import dir from config
        """
        Searches the object database with given query and returns a report with
        object id, thumbnails, and metadata of candidates, for downstream selection.
        """
        # Search for assets
        assets_response = requests.get(
            f"{GDB_API_BASE_URL}/v0/objects/search",
            params={"query": query_text},
        )
        # logger.debug(f"Query: {query_text}. Response: {assets_response}")
        assets = assets_response.json()

        # Create report (with thumbnails and metadata to help VLM's decision making)
        report_response = requests.get(
            f"{GDB_API_BASE_URL}/v0/objects/report",
            params={"uids": [asset["uid"] for asset in assets],
                    "image_format": "path"},  # this probably renders `flatten_markdown_images()` useless
        )
        report = report_response.json()
        
        # Handle case where API returns dict instead of string
        if isinstance(report, dict):
            report = report.get('report', str(report))
        
        # logger.debug("Generated search report in markdown")

        # # Transform thumbnail URLs into local paths
        # report = flatten_markdown_images(report, output_dir)
        # print("Transformed thumbnail URLs into local paths")  # TODO: → logger
        if for_vlm:
            return transform_markdown_to_messages(report)
        else:
            return report

    def pack(
        self, uids: list[str]
    ) -> list[
        ObjectBlueprint
    ]:  # or export(), or finalize(), or *_objects(), or *_object_blueprints()
        """
        Returns a list of `ObjectBlueprint`s given a list of uids.
        """
        logger.debug(f"ObjectDatabase.pack called with {len(uids)} uids: {uids}")

        if not uids:
            return []

        try:
            # WARN: the by_uids endpoint does not exist in `graphics-db`.
            # response = requests.post(
            #     f"{API_BASE_URL}/v0/objects/by_uids",
            #     json={"uids": uids},
            #     timeout=30
            # )
            # response.raise_for_status()
            # assets = AssetListAdapter.validate_json(response.text)

            results = []
            # for asset in assets:  # ORIG
            #     results.append(
            #         ObjectBlueprint(
            #             name=asset.uid,  # TEMP HACK
            #             source_id=asset.uid,
            #             source="objaverse",  # TEMP HACK
            #             description="",  # TODO: use VLM to add desc, or source from DB?
            #             extra_info={"tags": asset.tags},
            #         )
            #     )
            for uid in uids:  # TEMP HACK
                results.append(
                    ObjectBlueprint(
                        name=uid,  # TEMP HACK
                        source_id=uid,
                        source="objaverse",  # TEMP HACK
                        description="",  # TODO: use VLM to add desc, or source from DB?
                        extra_info={"tags": []},  # TEMP HACK
                    )
                )
            # logger.debug(
            #     f"ObjectDatabase.pack returning {len(results)} object blueprints: {[r.name for r in results]}"
            # )
            # return results

        except requests.exceptions.RequestException as e:
            print(f"Request failed: {e}")
            return []
        except ValidationError as e:
            print(f"Data validation failed: {e}")
            return []
