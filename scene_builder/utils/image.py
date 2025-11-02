from pathlib import Path

import numpy as np
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


def compose_image_grid(images: list[np.ndarray], output_path: Path):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    pil_images: list[Image.Image] = []

    if len(images) > 4:
        raise ValueError("`compose_iamge_grid()` can handle only up to 2x2 grid (for now)")

    # Convert up to 4 arrays into PIL images (uniform RGBA)
    for i, array in enumerate(images[:4]):
        if array.dtype.kind == "f":  # handle float arrays
            array = (np.clip(array, 0.0, 1.0) * 255).astype(np.uint8)

        try:
            img = Image.fromarray(array)
            pil_images.append(img.convert("RGBA"))

        except Exception as e:
            logger.warning(f"Skipping image {i} due to conversion error: {e}")

    # if not pil_images:
    #     logger.warning("No valid images to compose; skipping grid creation.")
    #     return

    # Use size of the first image as the tile size
    tile_width, tile_height = pil_images[0].size

    # Create the 2x2 grid canvas (always RGBA for safe pasting)
    grid_image = Image.new("RGBA", (tile_width * 2, tile_height * 2), (0, 0, 0, 0))

    for index, image in enumerate(pil_images):
        # Resize if needed
        if image.size != (tile_width, tile_height):
            image = image.resize((tile_width, tile_height), Image.Resampling.LANCZOS)

        x_offset = (index % 2) * tile_width
        y_offset = (index // 2) * tile_height

        # Paste the image
        grid_image.paste(image, (x_offset, y_offset), mask=image)

    if output_path.suffix in {".jpg", ".jpeg"}:
        grid_image = grid_image.convert("RGB")

    # Save final image
    grid_image.save(output_path)


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
