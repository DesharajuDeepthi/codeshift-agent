# Model serialization

Pydantic v2 uses `model_dump()` to produce Python data from a model.
Pydantic v2 uses `model_dump_json()` to produce JSON data from a model.
These replace common v1 calls to `.dict()` and `.json()`.

# Custom serializers

Pydantic v2 adds field and model serializer decorators for custom serialization.
Projects using `json_encoders` should be reviewed for serializer migration.
Serialization of subclasses nested in model fields changed in v2.

