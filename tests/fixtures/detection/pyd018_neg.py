# PYD018 negative: model_fields (v2 style) — must NOT trigger PYD018
from pydantic import BaseModel


class MyModel(BaseModel):
    name: str


def inspect_model():
    # v2 style
    fields = MyModel.model_fields
    return list(fields.keys())
