# PYD021 negative: imports from pydantic v2 core — must NOT trigger PYD021
from pydantic import BaseModel, Field, field_validator


class ModernModel(BaseModel):
    name: str = Field(default="world")

    @field_validator("name")
    @classmethod
    def check_name(cls, v: str) -> str:
        return v
