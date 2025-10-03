"""Pydantic utility functions for easy file I/O operations."""

import json
from pathlib import Path
from typing import Union, Any

import yaml
from pydantic import BaseModel


def save_model(
    model: BaseModel,
    file_path: Union[str, Path],
    format: str = "auto",
    indent: int = 2,
    **kwargs: Any
) -> None:
    """
    Save a Pydantic model instance to a file in JSON or YAML format.

    Args:
        model: The Pydantic model instance to save
        file_path: Path to the output file
        format: Output format ('json', 'yaml', or 'auto' to detect from extension)
        indent: Indentation level for pretty formatting
        **kwargs: Additional arguments passed to json.dump() or yaml.dump()

    Example:
        >>> from pydantic import BaseModel
        >>> class User(BaseModel):
        ...     id: int
        ...     name: str
        >>> user = User(id=123, name="John Doe")
        >>> save_model(user, "user.yaml")  # Auto-detects YAML format
        >>> save_model(user, "user.json", format="json")  # Explicit JSON format
    """
    file_path = Path(file_path)

    # Auto-detect format from file extension
    if format == "auto":
        extension = file_path.suffix.lower()
        if extension in ['.yaml', '.yml']:
            format = "yaml"
        elif extension == '.json':
            format = "json"
        else:
            # Default to JSON if unknown extension
            format = "json"

    # Convert model to dictionary
    model_dict = model.model_dump()

    # Create parent directories if they don't exist
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Save to file
    with open(file_path, 'w', encoding='utf-8') as f:
        if format.lower() == "yaml":
            yaml.dump(model_dict, f, indent=indent, default_flow_style=False, **kwargs)
        else:  # JSON
            json.dump(model_dict, f, indent=indent, ensure_ascii=False, **kwargs)


def save_json(model: BaseModel, file_path: Union[str, Path], indent: int = 2, **kwargs: Any) -> None:
    """
    Save a Pydantic model instance to a JSON file.

    Args:
        model: The Pydantic model instance to save
        file_path: Path to the output JSON file
        indent: Indentation level for pretty formatting
        **kwargs: Additional arguments passed to json.dump()

    Example:
        >>> user = User(id=123, name="John Doe")
        >>> save_json(user, "user.json")
    """
    save_model(model, file_path, format="json", indent=indent, **kwargs)


def save_yaml(model: BaseModel, file_path: Union[str, Path], indent: int = 2, **kwargs: Any) -> None:
    """
    Save a Pydantic model instance to a YAML file.

    Args:
        model: The Pydantic model instance to save
        file_path: Path to the output YAML file
        indent: Indentation level for pretty formatting
        **kwargs: Additional arguments passed to yaml.dump()

    Example:
        >>> user = User(id=123, name="John Doe")
        >>> save_yaml(user, "user.yaml")
    """
    save_model(model, file_path, format="yaml", indent=indent, **kwargs)