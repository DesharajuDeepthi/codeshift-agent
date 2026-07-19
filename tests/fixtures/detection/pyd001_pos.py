# PYD001 positive: @validator imported from pydantic
from pydantic import BaseModel, validator


class UserModel(BaseModel):
    name: str
    age: int

    @validator("name")
    def name_must_be_string(cls, v):
        return v.strip()

    @validator("age")
    def age_must_be_positive(cls, v):
        if v < 0:
            raise ValueError("age must be positive")
        return v
