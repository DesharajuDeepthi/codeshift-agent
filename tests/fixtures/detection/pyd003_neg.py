# PYD003 negative: class Config NOT inside a BaseModel subclass
class Settings:
    """Pure non-pydantic class — Config here is not a pydantic Config."""

    class Config:
        env_prefix = "APP_"

    def __init__(self):
        pass


class DatabaseConfig:
    """Another non-pydantic Config holder."""

    class Config:
        debug = False
