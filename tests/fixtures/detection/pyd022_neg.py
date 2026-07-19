# PYD022 negative: no GetterDict — plain ORM model using v2 style
from pydantic import BaseModel, ConfigDict


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
