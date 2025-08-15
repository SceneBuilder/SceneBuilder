from pathlib import Path

from PIL import Image

from scene_builder.logging import logger


def create_gif_from_images(image_paths: list[Path], output_path, duration=100, loop=0):
    """
    Creates an animated GIF from a folder of images.

    Args:
        image_paths (list[Path | str]): Path to image files.
        output_path (str): Path to save the generated GIF.
        duration (int): Duration for each frame in milliseconds (default: 100).
        loop (int): Number of times the animation repeats (0 for infinite loop, default: 0).
    """
    # Open all images
    frames = [Image.open(path) for path in image_paths]

    # Save the first image, appending the rest as frames
    frames[0].save(
        output_path,
        format="GIF",
        append_images=frames[1:],
        save_all=True,
        duration=duration,
        loop=loop,
    )
    logger.info(f"GIF created and saved at {output_path}")
