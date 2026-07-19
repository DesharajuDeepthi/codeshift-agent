# Configuration

Model configuration in pydantic v2 is set with `model_config`.
The old inner `class Config` style should be migrated to the new configuration form.
`ConfigDict` can be used to make configuration explicit and typed.

# Renamed config keys

`orm_mode` is now `from_attributes`.
`allow_population_by_field_name` is now `populate_by_name`.
`validate_all` is now `validate_default`.
Removed or changed keys should be reviewed rather than blindly rewritten.

