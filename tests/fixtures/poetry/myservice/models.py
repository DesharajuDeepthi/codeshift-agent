from pydantic import BaseModel, validator


class Config(BaseModel):
    host: str
    port: int = 8080

    @validator("port")
    @classmethod
    def port_range(cls, v: int) -> int:
        if not 1 <= v <= 65535:
            raise ValueError("invalid port")
        return v

    class Config:
        orm_mode = True
