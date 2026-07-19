# PYD002 positive: @root_validator imported from pydantic
from pydantic import BaseModel, root_validator


class AddressModel(BaseModel):
    street: str
    city: str

    @root_validator
    def check_address(cls, values):
        if not values.get("city"):
            raise ValueError("city is required")
        return values

    @root_validator(pre=True)
    def normalize(cls, values):
        return values
