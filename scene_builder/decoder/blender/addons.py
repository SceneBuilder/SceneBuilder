import bpy
import addon_utils
from pathlib import Path


class BlenderAddonManager:
    """Test harness for Blender addons with door randomization."""
    
    def __init__(self, addon_path: str, addon_module: str, output_dir: Path):
        self.addon_path = addon_path
        self.addon_module = addon_module
        self.output_dir = output_dir
        
    def install_addon(self) -> None:
        """Install the addon from the specified path."""
        bpy.ops.preferences.addon_install(filepath=self.addon_path)
        
    def enable_addon(self) -> None:
        """Enable the addon and refresh addon modules."""
        bpy.ops.preferences.addon_enable(module=self.addon_module)
        bpy.ops.wm.save_userpref()
        addon_utils.modules_refresh()
        
    def execute_script(self, script_path: Path) -> None:
        """Execute a Python script with __name__ set to __main__."""
        exec(compile(script_path.read_text(), str(script_path), "exec"), {
            "__file__": str(script_path),
            "__name__": "__main__"
        })
        
    def save_blend_file(self, filename: str) -> Path:
        """Save the current Blender scene to a .blend file."""
        output_path = self.output_dir / filename
        bpy.ops.wm.save_as_mainfile(filepath=str(output_path))
        return output_path
        
    def run_test(self, script_path: Path, output_filename: str = "output.blend") -> Path:
        """Run the complete test workflow."""
        self.install_addon()
        self.enable_addon()
        self.execute_script(script_path)
        return self.save_blend_file(output_filename)
