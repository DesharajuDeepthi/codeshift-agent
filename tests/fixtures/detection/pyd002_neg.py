# PYD002 negative: model_validator (v2 style) — must NOT trigger PYD002
from pydantic import BaseModel, model_validator


class AddressModel(BaseModel):
    street: str
    city: str

    @model_validator(mode="after")
    def check_address(self):
        if not self.city:
            raise ValueError("city is required")
        return self
