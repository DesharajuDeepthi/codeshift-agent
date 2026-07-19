# PYD001 negative: @validator not from pydantic (false-positive resistance)
from pydantic import BaseModel, field_validator  # v2 style


def validator(field_name):
    """Custom validator decorator — not pydantic's."""
    def decorator(fn):
        return fn
    return decorator


class UserModel(BaseModel):
    name: str

    @field_validator("name")  # v2 style — should NOT trigger PYD001
    @classmethod
    def validate_name(cls, v: str) -> str:
        return v.strip()


class OtherClass:
    @validator("field")  # local validator, not from pydantic
    def check(cls, v):
        return v
