# PYD003-PYD008 positive: class Config with various v1 attributes
from pydantic import BaseModel


class ItemModel(BaseModel):
    name: str
    price: float

    class Config:
        orm_mode = True
        allow_population_by_field_name = True
        validate_all = True
        smart_union = True
        json_encoders = {float: str}


class ArticleModel(BaseModel):
    title: str
    content: str

    class Config:
        orm_mode = False
