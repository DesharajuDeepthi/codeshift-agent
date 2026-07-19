# PYD009 negative: .dict() call but no pydantic import in this file
# Should NOT trigger because pydantic is not imported here.

class NonPydanticModel:
    def __init__(self, name: str):
        self.name = name

    def dict(self):
        return {"name": self.name}


def to_dict(obj):
    return obj.dict()
