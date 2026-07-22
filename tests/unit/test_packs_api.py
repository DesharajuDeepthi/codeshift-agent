"""Unit tests for GET /packs endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

from upgradepilot.api.main import create_app


class TestPacksEndpoint:
    def setup_method(self) -> None:
        self.client = TestClient(create_app())

    def test_list_packs_returns_200(self) -> None:
        response = self.client.get("/packs")
        assert response.status_code == 200

    def test_list_packs_response_structure(self) -> None:
        data = self.client.get("/packs").json()
        assert "packs" in data
        assert isinstance(data["packs"], list)
        assert len(data["packs"]) >= 1

    def test_each_pack_has_required_fields(self) -> None:
        packs = self.client.get("/packs").json()["packs"]
        required = {
            "pack_id", "display_name", "language", "analyzer_kind", "version", "description"
        }
        for pack in packs:
            missing = required - pack.keys()
            assert not missing, f"Pack {pack.get('pack_id')} missing fields: {missing}"

    def test_pydantic_pack_present(self) -> None:
        ids = [p["pack_id"] for p in self.client.get("/packs").json()["packs"]]
        assert "pydantic-v1-to-v2" in ids

    def test_django_pack_present(self) -> None:
        ids = [p["pack_id"] for p in self.client.get("/packs").json()["packs"]]
        assert "django-v3-to-v4" in ids

    def test_pack_language_field_is_lowercase(self) -> None:
        packs = self.client.get("/packs").json()["packs"]
        for pack in packs:
            assert pack["language"] == pack["language"].lower()

    def test_pydantic_pack_metadata(self) -> None:
        packs = {p["pack_id"]: p for p in self.client.get("/packs").json()["packs"]}
        p = packs["pydantic-v1-to-v2"]
        assert p["language"] == "python"
        assert p["analyzer_kind"] == "python-ast"
        assert p["source_major"] == 1
        assert p["target_major"] == 2

    def test_django_pack_metadata(self) -> None:
        packs = {p["pack_id"]: p for p in self.client.get("/packs").json()["packs"]}
        p = packs["django-v3-to-v4"]
        assert p["language"] == "python"
        assert p["analyzer_kind"] == "regex"
        assert p["source_major"] == 3
        assert p["target_major"] == 4
