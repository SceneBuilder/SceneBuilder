from pathlib import Path

import bpy
import addon_utils

from scene_builder.config import DOOR_ADDON_ZIP_PATH, WINDOW_ADDON_ZIP_PATH
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


def install_door_it_addon(addon_path: str = DOOR_ADDON_ZIP_PATH) -> bool:
    """Install and enable Door It! Interior addon.

    Args:
        addon_path: Path to the Door It! Interior addon zip file

    Returns:
        True if successfully installed and enabled, False otherwise
    """
    addon_module = "DoorItInterior"

    # Check if already enabled
    if addon_utils.check(addon_module)[1]:
        logger.info(f"✓ {addon_module} addon already enabled")
        return True

    # Check if addon file exists
    addon_file = Path(addon_path)
    if not addon_file.exists():
        logger.warning(f"Door It! Interior addon not found at: {addon_path}\n")
        return False

    try:
        # Install addon
        bpy.ops.preferences.addon_install(filepath=str(addon_path))
        logger.info(f"✓ Installed Door It! Interior from {addon_path}")

        # Enable addon
        bpy.ops.preferences.addon_enable(module=addon_module)
        bpy.ops.wm.save_userpref()
        addon_utils.modules_refresh()
        logger.info(f"✓ Enabled {addon_module} addon")
        return True

    except Exception as e:
        logger.error(f"Failed to install/enable Door It! Interior addon: {e}")
        return False


def enable_door_it_addon() -> bool:
    """Enable Door It! Interior addon if already installed.

    Returns:
        True if addon is enabled, False otherwise
    """
    addon_module = "DoorItInterior"

    # Check if already enabled
    if addon_utils.check(addon_module)[1]:
        return True

    # Try to enable it
    try:
        bpy.ops.preferences.addon_enable(module=addon_module)
        addon_utils.modules_refresh()
        logger.info(f"✓ Enabled {addon_module} addon")
        return True
    except Exception as e:
        logger.debug(f"Door It! Interior addon not available: {e}")
        return False


def install_window_it_addon(addon_path: str = WINDOW_ADDON_ZIP_PATH) -> bool:
    """Install and enable Window It! addon.

    Args:
        addon_path: Path to the Window It! addon zip file

    Returns:
        True if successfully installed and enabled, False otherwise
    """
    addon_module = "WindowIt"

    # Check if already enabled
    if addon_utils.check(addon_module)[1]:
        logger.info(f"✓ {addon_module} addon already enabled")
        return True

    # Check if addon file exists
    addon_file = Path(addon_path)
    if not addon_file.exists():
        logger.warning(f"Window It! addon not found at: {addon_path}\n")
        return False

    try:
        # Install addon
        bpy.ops.preferences.addon_install(filepath=str(addon_path))
        logger.info(f"✓ Installed Window It! from {addon_path}")

        # Enable addon
        bpy.ops.preferences.addon_enable(module=addon_module)
        bpy.ops.wm.save_userpref()
        addon_utils.modules_refresh()
        logger.info(f"✓ Enabled {addon_module} addon")
        return True

    except Exception as e:
        logger.error(f"Failed to install/enable Window It! addon: {e}")
        return False


def enable_window_it_addon() -> bool:
    """Enable Window It! addon if already installed.

    Returns:
        True if addon is enabled, False otherwise
    """
    addon_module = "WindowIt"

    # Check if already enabled
    if addon_utils.check(addon_module)[1]:
        return True

    # Try to enable it
    try:
        bpy.ops.preferences.addon_enable(module=addon_module)
        addon_utils.modules_refresh()
        logger.info(f"✓ Enabled {addon_module} addon")
        return True
    except Exception as e:
        logger.debug(f"Window It! addon not available: {e}")
        return False


def configure_gpu_backend(backend="OPTIX"):
    """
    Configures Blender's system preferences to use a specific GPU backend.

    This function enables the specified backend (e.g., 'OPTIX', 'HIP', 'CUDA')
    and activates all corresponding GPU devices, while disabling the CPU.

    Args:
        backend (str): The Cycles compute device type to use.
                       One of: 'OPTIX', 'HIP', 'CUDA', 'METAL', 'NONE'.
                       Defaults to 'OPTIX'.
    """
    logger.info(f"Configuring System Preferences for {backend}")

    # Get Cycles preferences
    prefs = bpy.context.preferences.addons["cycles"].preferences

    # Set the compute device type
    prefs.compute_device_type = backend

    # Force a device list update
    prefs.get_devices()

    # Loop over devices and enable GPUs, disable CPU
    enabled_gpus = 0
    for device in prefs.devices:
        if device.type == backend:
            device.use = True
            logger.info(f"Enabling GPU: {device.name}")
            enabled_gpus += 1
        else:
            # Disable all other devices (including CPU)
            device.use = False
            if device.type == "CPU":
                logger.info(f"Disabling CPU: {device.name}")

    logger.info(f"Successfully enabled {enabled_gpus} {backend} device(s).")


def optimize_scene_for_gpu(scene=None, noise_threshold=0.05, max_bounces=8):
    """
    Optimizes the current scene's Cycles settings for fast GPU rendering.

    This function sets the device to 'GPU Compute' and tunes sampling,
    light paths, and performance settings for a good speed/quality balance.

    Args:
        scene (bpy.types.Scene, optional): The scene to modify.
            If None, defaults to bpy.context.scene.
        noise_threshold (float, optional): The target noise level.
            Lower is cleaner but slower. Defaults to 0.05.
        max_bounces (int, optional): The total max light bounces.
            Defaults to 8.
    """
    logger.info("Optimizing Scene for Fast GPU Rendering")

    if scene is None:
        scene = bpy.context.scene

    # Set render engine to Cycles and device to GPU
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"

    cycles = scene.cycles

    # Sampling
    cycles.use_adaptive_sampling = True
    cycles.noise_threshold = noise_threshold
    cycles.samples = 4096  # High max samples, letting noise threshold stop it

    # Denoising
    cycles.use_denoising = True

    # Smartly select the best denoiser
    # OptiX denoiser is fastest *if* OptiX is the system backend
    system_backend = bpy.context.preferences.addons["cycles"].preferences.compute_device_type
    if system_backend == "OPTIX":
        cycles.denoiser = "OPTIX"
    else:
        # OpenImageDenoise is the best universal fallback
        cycles.denoiser = "OPENIMAGEDENOISE"

    logger.info(f"Set denoiser to: {cycles.denoiser}")

    # Light Paths
    cycles.max_bounces = max_bounces
    cycles.glossy_bounces = 4  # Good default
    cycles.transmission_bounces = 4  # Good default

    # Disable caustics for a big speedup
    cycles.caustics_reflective = False
    cycles.caustics_refractive = False

    # Performance
    cycles.use_tiling = False  # Faster for modern GPUs
    cycles.persistent_data = True  # Good for rendering animations

    logger.info(f"Scene '{scene.name}' optimized with {noise_threshold} noise threshold.")
