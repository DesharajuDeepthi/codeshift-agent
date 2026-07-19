# TypeAdapter

`TypeAdapter` validates, serializes, and emits JSON schema for arbitrary Python types.
It is useful when there is no `BaseModel` wrapper around the target type.
Migration from `parse_obj_as` should consider `TypeAdapter(T).validate_python(value)`.

# JSON schema

`TypeAdapter` can also produce JSON schema for the adapted type.
This is useful when replacing v1 helper functions that worked outside a model.

