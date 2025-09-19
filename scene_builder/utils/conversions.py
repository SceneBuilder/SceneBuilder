from pathlib import Path
from typing import Type, TypeVar

import yaml
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def pydantic_to_dict(obj):
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    elif isinstance(obj, list):
        return [pydantic_to_dict(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: pydantic_to_dict(v) for k, v in obj.items()}
    else:
        return obj


def pydantic_from_yaml(file_path: Path | str, model_class: Type[T]) -> T:
    """
    Loads a Pydantic model from a YAML file.

    Args:
        file_path: The path to the YAML file.
        model_class: The Pydantic model class to instantiate.

    Returns:
        An instance of the Pydantic model.
    """
    with open(file_path, "r") as f:
        data = yaml.safe_load(f)
    return model_class(**data)
