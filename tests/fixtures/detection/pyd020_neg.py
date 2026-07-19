# PYD020 negative: stdlib dataclasses — must NOT trigger PYD020
from dataclasses import dataclass


@dataclass
class Point:
    x: float
    y: float
