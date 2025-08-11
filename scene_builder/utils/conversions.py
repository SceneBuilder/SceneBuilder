from dataclasses import is_dataclass, asdict


def dataclass_to_dict(obj):
    if is_dataclass(obj):
        return asdict(obj)
    elif isinstance(obj, list):
        return [dataclass_to_dict(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: dataclass_to_dict(v) for k, v in obj.items()}
    else:
        return obj
