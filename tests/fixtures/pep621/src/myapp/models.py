from pydantic import BaseModel, field_validator


class User(BaseModel):
    model_config = {"frozen": True}
    name: str
    age: int

    @field_validator("age")
    @classmethod
    def age_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("age must be positive")
        return v
