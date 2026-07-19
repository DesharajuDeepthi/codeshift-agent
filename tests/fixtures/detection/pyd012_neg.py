# PYD012 negative: model_validate (v2 style) — must NOT trigger PYD012/PYD013/PYD015
from pydantic import BaseModel


class UserModel(BaseModel):
    id: int
    name: str


def load(data: dict) -> UserModel:
    return UserModel.model_validate(data)


def load_json(raw: str) -> UserModel:
    return UserModel.model_validate_json(raw)
