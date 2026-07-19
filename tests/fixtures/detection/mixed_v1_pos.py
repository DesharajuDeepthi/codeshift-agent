# Mixed positive fixture: realistic v1 codebase hitting many rules
from pydantic import BaseModel, validator, root_validator
from pydantic.generics import GenericModel
from typing import TypeVar, Generic, Any, Dict

T = TypeVar("T")


class UserModel(BaseModel):
    username: str
    email: str

    class Config:
        orm_mode = True
        allow_population_by_field_name = True
        json_encoders = {str: lambda v: v.lower()}

    @validator("username")
    def validate_username(cls, v):
        return v.strip()

    @root_validator(pre=True)
    def check_required(cls, values):
        return values


def process_user(user: UserModel):
    data: Dict[str, Any] = user.dict()
    raw_json: str = user.json()
    copy = user.copy(update={"username": "new"})
    return data, raw_json, copy


def load_user(data: dict) -> UserModel:
    return UserModel.parse_obj(data)


class ResponseModel(GenericModel, Generic[T]):
    data: T
    ok: bool


def inspect(model: UserModel):
    return list(model.__fields__.keys())
