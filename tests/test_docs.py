"""A documentação é código: estes testes impedem que ela fique para trás dos endpoints e models."""

import json
import re
from pathlib import Path

import pytest
from flask.testing import FlaskClient

from app.extensions import db

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def _normalize(path: str) -> str:
    """``/x/{id}`` (OpenAPI) e ``/x/{{id}}`` (Postman) viram ``/x/{}``."""
    return re.sub(r"\{\{[^}]+\}\}|\{[^}]+\}", "{}", path)


def _openapi_operations(client: FlaskClient) -> dict[tuple[str, str], dict]:
    spec = client.get("/openapi.json").get_json()
    return {
        (method.upper(), _normalize(path)): operation
        for path, item in spec["paths"].items()
        for method, operation in item.items()
        if method in HTTP_METHODS
    }


def _postman_requests() -> set[tuple[str, str]]:
    collection = json.loads((DOCS / "postman_collection.json").read_text(encoding="utf-8"))
    found: set[tuple[str, str]] = set()

    def walk(items: list[dict]) -> None:
        for item in items:
            if "item" in item:
                walk(item["item"])
            else:
                url = item["request"]["url"]["raw"].split("?")[0]
                path = url.replace("{{base_url}}", "")
                found.add((item["request"]["method"], _normalize(path)))

    walk(collection["item"])
    return found


# ---------- OpenAPI ----------


def test_every_operation_is_documented_and_protected_routes_declare_security(
    client: FlaskClient,
) -> None:
    public = {
        ("GET", "/health"),
        ("POST", "/api/v1/auth/register"),
        ("POST", "/api/v1/auth/login"),
    }
    for (method, path), operation in _openapi_operations(client).items():
        assert operation.get("summary"), f"{method} {path} sem descrição (docstring)"
        assert "responses" in operation
        if (method, path) not in public:
            assert operation.get("security") == [{"bearerAuth": []}], (
                f"{method} {path} sem security"
            )
            assert "401" in operation["responses"], f"{method} {path} não documenta o 401"


def test_swagger_info_explains_authentication(client: FlaskClient) -> None:
    spec = client.get("/openapi.json").get_json()
    assert "Authorize" in spec["info"]["description"]
    assert client.get("/docs").status_code == 200


# ---------- Postman ----------


def test_postman_collection_covers_every_endpoint(client: FlaskClient) -> None:
    api = set(_openapi_operations(client))
    postman = _postman_requests()
    assert api - postman == set(), f"Endpoints fora da coleção do Postman: {sorted(api - postman)}"
    assert postman - api == set(), (
        f"Coleção chama endpoints que não existem: {sorted(postman - api)}"
    )


def test_postman_collection_has_expected_variables() -> None:
    collection = json.loads((DOCS / "postman_collection.json").read_text(encoding="utf-8"))
    names = {v["key"] for v in collection["variable"]}
    assert {"base_url", "access_token", "refresh_token", "customer_id", "service_id"} <= names
    assert collection["auth"]["type"] == "bearer"


# ---------- DER ----------


def _er_entities() -> dict[str, set[str]]:
    text = (DOCS / "er-diagram.md").read_text(encoding="utf-8")
    entities: dict[str, set[str]] = {}
    for match in re.finditer(r"^    (\w+) \{\n(.*?)^    \}", text, re.MULTILINE | re.DOTALL):
        columns = {line.split()[1] for line in match.group(2).splitlines() if line.strip()}
        entities[match.group(1).lower()] = columns
    return entities


def test_er_diagram_matches_models_column_by_column(app: object) -> None:
    entities = _er_entities()
    tables = {t.name: {c.name for c in t.columns} for t in db.metadata.sorted_tables}
    assert set(entities) == set(tables)
    for table, columns in tables.items():
        assert entities[table] == columns, f"DER desatualizado em {table}"


def test_mermaid_diagrams_exist() -> None:
    er = (DOCS / "er-diagram.md").read_text(encoding="utf-8")
    architecture = (DOCS / "architecture.md").read_text(encoding="utf-8")
    assert "```mermaid\nerDiagram" in er
    assert architecture.count("```mermaid") >= 2


# ---------- links ----------

MARKDOWN_FILES = [ROOT / "README.md", *sorted(DOCS.glob("*.md"))]


@pytest.mark.parametrize("path", MARKDOWN_FILES, ids=lambda p: p.name)
def test_relative_links_point_to_existing_files(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)  # ignora blocos de código
    for target in re.findall(r"\]\(([^)\s]+)\)", text):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        file_part = target.split("#")[0]
        assert (path.parent / file_part).resolve().exists(), f"{path.name}: link quebrado {target}"
