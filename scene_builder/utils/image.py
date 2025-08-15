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


if __name__ == "__main__":
    import argparse
    import glob
    from natsort import natsorted

    parser = argparse.ArgumentParser(
        description="Create a GIF from a folder of images."
    )
    parser.add_argument(
        "image_folder", type=Path, help="Path to the folder containing images."
    )
    parser.add_argument(
        "-o",
        "--output_path",
        type=Path,
        default=None,
        help="Path to save the generated GIF.",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=100,
        help="Duration for each frame in milliseconds.",
    )
    parser.add_argument(
        "--loop",
        type=int,
        default=0,
        help="Number of times the animation repeats (0 for infinite loop).",
    )
    args = parser.parse_args()

    image_extensions = ["*.png", "*.jpg", "*.jpeg"]
    image_paths = []
    for ext in image_extensions:
        image_paths.extend(args.image_folder.glob(ext))

    if not image_paths:
        logger.error(f"No images found in {args.image_folder}")
    else:
        sorted_paths = natsorted(image_paths, key=lambda p: p.as_posix())
        output_path = args.output_path or args.image_folder.joinpath("output.gif")
        create_gif_from_images(
            sorted_paths, output_path, duration=args.duration, loop=args.loop
        )
