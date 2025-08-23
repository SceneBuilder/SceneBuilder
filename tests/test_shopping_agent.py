import pytest
import requests
from pydantic_ai import BinaryContent
from graphics_db_server.schemas.asset import Asset

from scene_builder.workflow.agent import shopping_agent
from scene_builder.definition.scene import Object, Vector3


API_BASE_URL = "http://localhost:2692/api/v0"


def is_graphics_db_available():
    """Check if the graphics database server is available."""
    try:
        response = requests.get(
            f"{API_BASE_URL}/assets/search?query=test&top_k=1", timeout=5
        )
        return response.status_code == 200
    except (requests.exceptions.RequestException, ConnectionError):
        return False


@pytest.mark.skipif(
    not is_graphics_db_available(), reason="Graphics database server not available"
)
@pytest.mark.asyncio
async def test_shopping_agent_real_api():
    """Test ShoppingAgent with real graphics database API calls."""
    # Run the agent with a simple query
    result = await shopping_agent.run("Find a modern sofa for the living room")

    objects = result.output

    # Verify the result is a list of Object instances
    assert isinstance(objects, list)
    assert all(isinstance(obj, Object) for obj in objects)

    # Verify objects have proper structure
    for obj in objects:
        assert hasattr(obj, "name")
        assert hasattr(obj, "id")
        assert hasattr(obj, "source")
        assert hasattr(obj, "sourceId")
        assert hasattr(obj, "description")
        assert hasattr(obj, "position")
        assert hasattr(obj, "rotation")
        assert hasattr(obj, "scale")

        # Verify default values for position, rotation, scale
        assert obj.position == Vector3(x=0, y=0, z=0)
        assert obj.rotation == Vector3(x=0, y=0, z=0)
        assert obj.scale == Vector3(x=1, y=1, z=1)


@pytest.mark.skipif(not is_graphics_db_available())
@pytest.mark.asyncio
async def test_shopping_agent_with_thumbnails():
    """Test ShoppingAgent with thumbnail viewing capabilities."""
    # Run the agent with a query that might trigger thumbnail viewing
    result = await shopping_agent.run("Find a wooden table and show me thumbnails")
    
    objects = result.output

    # Verify the result is a list of Object instances
    assert isinstance(objects, list)
    assert all(isinstance(obj, Object) for obj in objects)

    # The agent should have accessed the graphics database
    # (We can't easily verify thumbnail viewing without mocking, but the test ensures the flow works)


@pytest.mark.skipif(not is_graphics_db_available())
def test_asset_search_tool_directly():
    """Test the search_assets tool directly with real API."""
    from scene_builder.tools.asset_search import search_assets

    # Test basic search
    assets = search_assets("chair", top_k=3)

    # Verify the result
    assert isinstance(assets, list)
    if assets:  # If we got results
        assert all(isinstance(asset, Asset) for asset in assets)
        for asset in assets:
            assert hasattr(asset, "uid")
            assert hasattr(asset, "url")
            assert hasattr(asset, "tags")


@pytest.mark.skipif(
    not is_graphics_db_available(), reason="Graphics database server not available"
)
def test_asset_thumbnail_tool_directly():
    """Test the get_asset_thumbnail tool directly with real API."""
    from scene_builder.tools.asset_search import get_asset_thumbnail, search_assets

    # First search for some assets to get UIDs
    assets = search_assets("chair", top_k=1)
    if not assets:
        pytest.skip("No assets found to test thumbnails")

    # Test thumbnail retrieval for the first asset
    thumbnail = get_asset_thumbnail(assets[0].uid)

    # Verify the result is BinaryContent
    assert isinstance(thumbnail, BinaryContent)
    assert hasattr(thumbnail, "data")
    assert hasattr(thumbnail, "media_type")
    assert thumbnail.media_type.startswith("image/")


# def test_shopping_agent_tools_available():
#     """Test that all required tools are available to the ShoppingAgent."""
#     tool_names = [tool.__name__ for tool in shopping_agent.tools]
#     assert "search_assets" in tool_names
#     assert "get_asset_thumbnail" in tool_names
#     assert "read_media_file" in tool_names


if __name__ == "__main__":
    # Run tests directly if graphics database is available
    if is_graphics_db_available():
        import asyncio

        # Run async tests
        async def run_async_tests():
            await test_shopping_agent_real_api()
            await test_shopping_agent_with_thumbnails()
            print("All async tests passed!")

        asyncio.run(run_async_tests())

        # Run sync tests
        test_asset_search_tool_directly()
        test_asset_thumbnail_tool_directly()
        # test_shopping_agent_tools_available()
        print("All sync tests passed!")
    else:
        print("Graphics database server not available. Skipping real API tests.")
        print(
            "Run the graphics database server on localhost:8000 to enable these tests."
        )
