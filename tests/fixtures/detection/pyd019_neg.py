# PYD019 negative: generic model using v2 style (plain BaseModel + Generic)
from typing import TypeVar, Generic

from pydantic import BaseModel

T = TypeVar("T")


class ResponseModel(BaseModel, Generic[T]):
    data: T
    success: bool
