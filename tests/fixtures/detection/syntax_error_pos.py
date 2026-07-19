# This file has a syntax error — scanner must fall back to text mode
from pydantic import BaseModel, validator

class BrokenModel(BaseModel
    name: str  # missing closing paren — syntax error

    @validator("name")
    def check(cls, v):
        return v
