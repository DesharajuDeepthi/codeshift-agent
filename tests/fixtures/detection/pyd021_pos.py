# PYD021 positive: pydantic.v1 compatibility shim imports
from pydantic.v1 import BaseModel, validator
from pydantic.v1.fields import Field


class LegacyModel(BaseModel):
    name: str

    @validator("name")
    def validate_name(cls, v):
        return v
