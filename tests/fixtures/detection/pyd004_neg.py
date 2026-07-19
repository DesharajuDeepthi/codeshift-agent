# PYD004 negative: from_attributes (v2 style) — must NOT trigger PYD004
from pydantic import BaseModel, ConfigDict


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
