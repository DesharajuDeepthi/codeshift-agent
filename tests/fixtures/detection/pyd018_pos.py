# PYD018 positive: __fields__ access on a pydantic model
from pydantic import BaseModel


class MyModel(BaseModel):
    name: str
    value: int


def inspect_model():
    fields = MyModel.__fields__
    return list(fields.keys())


def get_field_names(model):
    return list(model.__fields__.keys())
