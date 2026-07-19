# PYD020 positive: pydantic.dataclasses import
import pydantic.dataclasses
from pydantic.dataclasses import dataclass as pydantic_dataclass


@pydantic_dataclass
class Point:
    x: float
    y: float
