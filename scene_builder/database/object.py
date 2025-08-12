import objaverse
from typing import Any

from scene_builder.importer.test_asset_importer import TEST_ASSETS


class ObjectDatabase:
    """
    A wrapper for a 3D object database (e.g., Objaverse) that can
    operate in either debug (mock data) or production (real data) mode.
    """

    def __init__(self, debug: bool = False):
        """
        Initializes the ObjectDatabase.
        Args:
            debug: If True, the database will return mock data.
        """
        self.debug = debug
        self._lvis_annotations = None
        if not self.debug:
            print("Initializing ObjectDatabase in production mode...")
            self._lvis_annotations = objaverse.load_lvis_annotations()
            print("LVIS annotations loaded.")

    def query(self, query: str) -> list[dict[str, Any]]:
        """
        Queries the 3D object database.

        Args:
            query: The search query (e.g., "a red sofa").

        Returns:
            A list of dictionaries, where each dictionary represents a found object.
        """
        if self.debug:
            return self._query_mock(query)
        else:
            return self._query_real(query)

    def _query_mock(self, query: str) -> list[dict[str, Any]]:
        """
        Simulates querying a 3D object database and returns mock data.
        """
        print(f"Simulating database query for: '{query}'")
        for key, results in TEST_ASSETS.items():
            if key in query:
                return results
        return []

    def _query_real(self, query: str) -> list[dict[str, Any]]:
        """
        Performs a real query to the Objaverse database.
        """
        print(f"Performing real database query for: '{query}'")
        matching_uids = []
        for category, uids in self._lvis_annotations.items():
            if query in category:
                matching_uids.extend(uids)

        # Limit the number of results to avoid overwhelming the user
        matching_uids = matching_uids[:5]

        results = []
        for uid in matching_uids:
            results.append(
                {
                    "id": uid,
                    "name": f"Object: {uid}",
                    "description": "Description not available in LVIS annotations.",
                    "source": "objaverse",
                    "tags": [query],
                }
            )
        return results
