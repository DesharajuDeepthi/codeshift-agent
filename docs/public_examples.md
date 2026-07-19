# Pinned Public Examples

These examples are pinned for repeatable portfolio demonstrations. They are not claims
that the migrations were completed or that repository tests passed.

| Repository | Ref | Pinned Commit SHA | Why Included |
|---|---|---|---|
| `https://github.com/pydantic/pydantic` | `v1.10.15` | `5476a758c8ac59887dbfa3aa1c3481d0a0e20837` | Pydantic v1 release line for pack applicability demonstrations. |
| `https://github.com/fastapi/fastapi` | `0.95.2` | `8cc967a7605d3883bd04ceb5d25cc94ae079612f` | Public framework release from the Pydantic v1 era. |

## Demo Command Shape

Use the Streamlit UI or API with these refs. The UI shows the resolved commit SHA in
the Facts tab.

```bash
curl -X POST http://localhost:8000/analyses \
  -H 'content-type: application/json' \
  -d '{
    "repository_url": "https://github.com/pydantic/pydantic",
    "ref": "v1.10.15",
    "migration_pack": "pydantic-v1-to-v2",
    "analysis_mode": "standard"
  }'
```

For no-network portfolio walkthroughs, use `analysis_mode: "fixture"` with any public
GitHub URL to exercise the UI, exports, validation, and observability surfaces.
