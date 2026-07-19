# PYD014 positive: parse_obj_as imported from pydantic
from typing import List

from pydantic import parse_obj_as


def parse_list(data) -> List[int]:
    return parse_obj_as(List[int], data)
