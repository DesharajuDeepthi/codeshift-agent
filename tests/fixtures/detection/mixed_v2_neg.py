# Mixed negative: pure pydantic v2 codebase — must produce zero findings
from typing import TypeVar, Generic, Any
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

T = TypeVar("T")


class UserModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
    username: str
    email: str

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        return v.strip()

    @model_validator(mode="after")
    def check_required(self) -> "UserModel":
        return self


def process_user(user: UserModel) -> dict[str, Any]:
    data = user.model_dump()
    raw_json = user.model_dump_json()
    copy = user.model_copy(update={"username": "new"})
    return {"data": data, "json": raw_json, "copy": copy}


def load_user(data: dict) -> UserModel:
    return UserModel.model_validate(data)


class ResponseModel(BaseModel, Generic[T]):
    data: T
    ok: bool


def inspect(model: UserModel) -> list[str]:
    return list(model.model_fields.keys())
