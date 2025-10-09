import bpy

from scene_builder.logging import logger


class SceneSwitcher:
    """
    A context manager to switch the active scene.

    NOTE: Becomes no-op if `scene_name = None`.
    """

    def __init__(self, scene_name):
        self.scene_name = scene_name

        if scene_name:
            if scene_name in bpy.data.scenes:
                self.scene = bpy.data.scenes[scene_name]
            else:  # create scene if it doesn't exist
                self.scene = bpy.data.scenes.new(name=scene_name)
        else:
            self.scene = None

    def __enter__(self):
        if self.scene_name:
            # Store the original scene and switch to the new one
            self.original_scene = bpy.context.window.scene
            bpy.context.window.scene = self.scene
            # logger.debug(f"--> Switched scene to '{self.scene.name}'")
        return self.scene

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.scene_name:
            # Switch back to the original scene
            # logger.debug(f"<-- Switched back to '{self.original_scene.name}'")
            bpy.context.window.scene = self.original_scene
