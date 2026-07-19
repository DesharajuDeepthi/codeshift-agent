import pytest
from app import Item


def test_item():
    item = Item(name="widget", price=9.99)
    assert item.name == "widget"
