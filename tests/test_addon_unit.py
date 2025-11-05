# addon_manager.py controller, 

import os
from pathlib import Path
from scene_builder.config import DOOR_ADDON_ZIP_PATH, WINDOW_ADDON_ZIP_PATH
from scene_builder.decoder.blender.addons import BlenderAddonManager


if __name__ == "__main__":
    script_dir = Path(os.path.dirname(os.path.realpath(__file__)))
    output_dir = script_dir.parent / "test_output"
    
    # Test Door It! addon
    door_tester = BlenderAddonManager(
        addon_path=str(DOOR_ADDON_ZIP_PATH),
        addon_module="DoorItInterior",
        output_dir=output_dir
    )
    
    door_controller_script = (script_dir / "../scene_builder/decoder/blender/controllers/interior_door.py").resolve()
    door_output_file = door_tester.run_test(door_controller_script, "door_output.blend")
    print(f"Door It! test completed: {door_output_file}")
    
    # Test Window It! addon
    window_tester = BlenderAddonManager(
        addon_path=str(WINDOW_ADDON_ZIP_PATH),
        addon_module="WindowIt",
        output_dir=output_dir
    )
    
    # Update this path if you have a window controller script
    # window_controller_script = (script_dir / "../scene_builder/decoder/blender/controllers/window.py").resolve()
    # window_output_file = window_tester.run_test(window_controller_script, "window_output.blend")
    # print(f"Window It! test completed: {window_output_file}")
