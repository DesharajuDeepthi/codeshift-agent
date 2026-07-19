# PYD009, PYD010, PYD011 positive: .dict(), .json(), .copy() calls in pydantic file
from pydantic import BaseModel


class ProductModel(BaseModel):
    name: str
    price: float


def serialize_product(product: ProductModel) -> dict:
    data = product.dict()
    return data


def to_json(product: ProductModel) -> str:
    return product.json()


def clone_product(product: ProductModel) -> ProductModel:
    return product.copy(update={"price": 0.0})
