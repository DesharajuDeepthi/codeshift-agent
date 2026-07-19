# Changes to pydantic.BaseModel

Pydantic v2 renames many BaseModel methods to `model_*` names.
`dict()` maps to `model_dump()`, `json()` maps to `model_dump_json()`,
`copy()` maps to `model_copy()`, `parse_obj()` maps to `model_validate()`,
and `schema()` maps to `model_json_schema()`.
`parse_raw` is deprecated; validate JSON data with `model_validate_json()`.
`from_orm` is deprecated; use `model_validate` with `from_attributes=True`.
`__fields__` is replaced by `model_fields`.

# Changes to config

Pydantic v2 replaces inner `class Config` with `model_config`.
`orm_mode` is renamed to `from_attributes`.
`allow_population_by_field_name` is renamed to `populate_by_name`.
`validate_all` is renamed to `validate_default`.
`smart_union` has been removed because union handling changed in v2.
`json_encoders` is deprecated in favor of custom serializers.

# Changes to validators

Pydantic v1 `@validator` and `@root_validator` are deprecated in v2.
Use `@field_validator` for field-level validation.
Use `@model_validator` for validation that needs the whole model.
Validator signatures changed, so migration requires reviewing arguments.

# GenericModel and pydantic.v1

`pydantic.generics.GenericModel` is no longer needed in v2.
Generic models can inherit from `BaseModel` and `typing.Generic`.
The `pydantic.v1` namespace is available as a compatibility bridge.
Code that still imports `pydantic.v1` has not completed migration to native v2 APIs.

# Dataclasses and GetterDict

Pydantic dataclasses remain available, but behavior changed in v2.
`GetterDict` was an implementation detail of `orm_mode` and has been removed.

# TypeAdapter

Pydantic v2 introduces `TypeAdapter` for validation and serialization with arbitrary types.
Use it for patterns that previously relied on `parse_obj_as`.

