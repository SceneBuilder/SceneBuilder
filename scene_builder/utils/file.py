from pathlib import Path


def get_filename(
    output_dir: Path | str, base_name: str, extension: str, strategy="increment"
) -> str:
    """
    Generates a unique filename in the output directory.

    Args:
        output_dir: The directory where the file will be saved.
        base_name: The base name of the file.
        extension: The file extension.
        strategy: The strategy to use for generating a unique name.
                  Currently, only 'increment' is supported.

    Returns:
        A unique file path as a string.

    Raises:
        FileExistsError: If a unique filename cannot be found after 1000 attempts.
        NotImplementedError: If an unsupported strategy is provided.
    """
    output_dir = Path(output_dir)
    assert output_dir.exists(), f"Output directory does not exist: {output_dir}"

    if strategy == "increment":
        for i in range(1000):
            candidate = output_dir / f"{base_name}_{i}.{extension}"
            if not candidate.exists():
                return str(candidate)

        raise FileExistsError(
            f"Could not find a unique filename for '{base_name}' after 1000 attempts."
        )
    else:
        raise NotImplementedError(f"Strategy '{strategy}' is not implemented.")
