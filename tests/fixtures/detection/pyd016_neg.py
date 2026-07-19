# PYD016 negative: model_json_schema (v2 style) — must NOT trigger PYD016/PYD017
from pydantic import BaseModel
import json


class ItemModel(BaseModel):
    name: str


def get_schema():
    return ItemModel.model_json_schema()


def get_schema_json():
    return json.dumps(ItemModel.model_json_schema())
