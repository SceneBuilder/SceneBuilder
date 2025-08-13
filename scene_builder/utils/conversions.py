from pydantic import BaseModel


def pydantic_to_dict(obj):
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    elif isinstance(obj, list):
        return [pydantic_to_dict(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: pydantic_to_dict(v) for k, v in obj.items()}
    else:
        return obj