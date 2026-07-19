# PYD019 positive: GenericModel imported from pydantic
from typing import TypeVar, Generic

from pydantic import BaseModel
from pydantic.generics import GenericModel

T = TypeVar("T")


class ResponseModel(GenericModel, Generic[T]):
    data: T
    success: bool
