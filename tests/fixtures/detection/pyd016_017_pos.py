# PYD016, PYD017 positive: .schema() and .schema_json() calls
from pydantic import BaseModel


class ItemModel(BaseModel):
    name: str
    price: float


def get_schema():
    return ItemModel.schema()


def get_schema_json():
    return ItemModel.schema_json()
