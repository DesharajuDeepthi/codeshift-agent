# PYD012-PYD015 positive: parsing / construction v1 patterns
from pydantic import BaseModel


class UserModel(BaseModel):
    id: int
    name: str


def load_from_dict(data: dict) -> UserModel:
    return UserModel.parse_obj(data)


def load_from_json(raw: str) -> UserModel:
    return UserModel.parse_raw(raw)


def load_from_orm(obj) -> UserModel:
    return UserModel.from_orm(obj)
