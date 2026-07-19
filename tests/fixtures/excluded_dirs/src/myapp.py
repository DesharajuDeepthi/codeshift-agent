from pydantic import BaseModel


class App(BaseModel):
    name: str
