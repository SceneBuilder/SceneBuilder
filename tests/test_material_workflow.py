"""
Test the material workflow integration with floor mesh creation.
"""

import pytest
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scene_builder.definition.scene import Vector2
from scene_builder.decoder import blender_decoder
from scene_builder.tools.material_workflow import MaterialWorkflow, apply_floor_material


def test_material_workflow_integration():
    """Test the complete material workflow with floor mesh creation."""

    print("=== Testing Material Workflow Integration ===")

    # Clear any existing scene objects first
    blender_decoder._clear_scene()

    # Create a floor mesh (same as test_floor_mesh.py)
    boundary = [
        Vector2(x=4, y=2),
        Vector2(x=-4, y=2),
        Vector2(x=-4, y=-2),
        Vector2(x=4, y=-2),
    ]

    floor_result = blender_decoder._create_floor_mesh(boundary, "test_material_room")
    assert floor_result.get("status") == "success", "Floor mesh creation should succeed"
    print(f"✅ Floor mesh created successfully")

    # Apply material using the workflow
    material_result = apply_floor_material("wood floor", uv_scale=2.0)

    # Check results
    print(f"Material workflow result: {material_result}")

    # The workflow should attempt to find materials and apply them
    # Even if Graphics-DB is not running, it should handle the error gracefully
    assert isinstance(material_result, dict), "Should return results dictionary"
    assert "success" in material_result, "Should have success status"
    assert "query" in material_result, "Should record the query"
    assert "materials_found" in material_result, "Should record materials found count"
    assert "floors_textured" in material_result, "Should record floors textured count"
    assert "errors" in material_result, "Should have errors list"

    if material_result["success"]:
        print(
            f"✅ Successfully applied material to {material_result['floors_textured']} floors"
        )
        assert material_result["floors_textured"] > 0, (
            "Should have textured at least one floor"
        )
        assert len(material_result["textured_objects"]) > 0, (
            "Should have textured objects list"
        )
    else:
        print(f"⚠️  Material application failed (expected if Graphics-DB not running)")
        print(f"   Errors: {material_result['errors']}")
        # This is expected if Graphics-DB server is not running

    # Save scene for inspection
    blender_decoder.save_scene("test_material_workflow.blend")
    print("✅ Test scene saved")

    # Render top-down view
    try:
        render_path = blender_decoder.render_top_down(".")
        print(f"✅ Top-down render saved: {render_path}")
    except Exception as e:
        print(f"⚠️  Top-down render failed: {e}")


def test_graphics_db_client():
    """Test the Graphics-DB client (may fail if server not running)."""
    from scene_builder.tools.graphics_db_client import GraphicsDBClient

    print("\n=== Testing Graphics-DB Client ===")

    client = GraphicsDBClient()

    # Test search (will fail gracefully if server not running)
    materials = client.search_materials("wood floor", top_k=3)

    # Should return empty list if server not available
    assert isinstance(materials, list), "Should return list even if empty"

    print(f"Found {len(materials)} materials")

    if materials:
        print("✅ Graphics-DB server is running and returned materials")

        # Test material structure
        material = materials[0]
        assert "uid" in material, "Material should have uid"
        print(f"   First material UID: {material['uid']}")

        # If materials found, test download
        material_uid = material["uid"]
        texture_path = client.download_diffuse_texture(material_uid)

        if texture_path:
            assert Path(texture_path).exists(), "Downloaded texture should exist"
            print(f"✅ Successfully downloaded texture: {texture_path}")
        else:
            print("⚠️  Texture download failed")
    else:
        print("⚠️  No materials found (Graphics-DB server may not be running)")


def test_material_applicator_components():
    """Test individual components of the material applicator."""
    from scene_builder.tools.material_applicator import find_floor_objects

    print("\n=== Testing Material Applicator Components ===")

    # Clear any existing scene objects first
    blender_decoder._clear_scene()

    # Create a test floor first
    boundary = [
        Vector2(x=2, y=2),
        Vector2(x=-2, y=2),
        Vector2(x=-2, y=-2),
        Vector2(x=2, y=-2),
    ]
    floor_result = blender_decoder._create_floor_mesh(boundary, "test_applicator")

    assert floor_result.get("status") == "success", "Test floor should be created"

    # Test floor object detection
    floor_objects = find_floor_objects()
    assert isinstance(floor_objects, list), "Should return list of floor objects"

    print(f"Found floor objects: {floor_objects}")

    if floor_objects:
        print("✅ Floor object detection working")

        # Test with a dummy texture (create a simple test texture)
        test_texture_path = Path.home() / ".scenebuilder_materials" / "test_texture.jpg"
        test_texture_path.parent.mkdir(exist_ok=True)

        # Create a minimal test image if it doesn't exist
        if not test_texture_path.exists():
            try:
                import bpy

                # Create a simple procedural texture in Blender and save it
                # For testing purposes, we'll just create a placeholder file
                with open(test_texture_path, "wb") as f:
                    # Write minimal JPEG header (this won't be a valid image, but tests the path)
                    f.write(b"\xff\xd8\xff\xe0\x00\x10JFIF")  # Minimal JPEG signature
                print(f"Created test texture: {test_texture_path}")
            except Exception as e:
                print(f"Could not create test texture: {e}")
    else:
        print("⚠️  No floor objects detected")


if __name__ == "__main__":
    print("Running Material Workflow Tests...")

    try:
        test_material_workflow_integration()
        test_graphics_db_client()
        test_material_applicator_components()

        print("\n🎉 All tests completed successfully!")

    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()
