# PYD022 positive: GetterDict imported from pydantic.utils
from pydantic import BaseModel
from pydantic.utils import GetterDict


class OrmModel(BaseModel):
    id: int
    name: str

    class Config:
        orm_mode = True
        getter_dict = GetterDict
