import json
from pathlib import Path
from typing import Any
from app.connectors import CONNECTORS

SOURCES_FILE = Path(__file__).resolve().parent.parent / "sources.json"
# Companies we can't collect jobs from automatically; the dashboard links to their careers pages instead.
LINK_ONLY_FILE = Path(__file__).resolve().parent.parent / "link_only.json"


def load_link_only(path: Path = LINK_ONLY_FILE) -> list[dict[str, Any]]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def source_key(source: dict) -> str:
    connector = CONNECTORS[source["provider"]]
    return ":".join([source["provider"], *(str(source[f]) for f in connector.KEY_FIELDS)])


def validate_source(source: dict) -> str | None:
    """Return a problem description, or None when the source is usable."""
    if not source.get("company"):
        return "missing 'company'"
    provider = str(source.get("provider", "")).lower()
    if provider not in CONNECTORS:
        return f"unknown provider {source.get('provider')!r} (known: {', '.join(sorted(CONNECTORS))})"
    missing = [f for f in CONNECTORS[provider].KEY_FIELDS if not source.get(f) or str(source[f]).startswith("REPLACE_")]
    if missing:
        return f"missing {', '.join(missing)}"
    return None


def load_sources(path: Path = SOURCES_FILE) -> list[dict[str, Any]]:
    """Enabled, valid sources from sources.json, each with a computed "key". Bad entries are skipped with a warning."""
    sources, seen = [], set()
    for index, raw in enumerate(json.loads(path.read_text(encoding="utf-8"))):
        if raw.get("enabled", True) is False:
            continue
        source = {**raw, "provider": str(raw.get("provider", "")).lower()}
        problem = validate_source(source)
        if problem:
            print(f"WARNING sources.json entry {index} ({raw.get('company')}): {problem}; skipped")
            continue
        source["key"] = source_key(source)
        if source["key"] in seen:
            print(f"WARNING sources.json entry {index} ({raw.get('company')}): duplicate of {source['key']}; skipped")
            continue
        seen.add(source["key"])
        sources.append(source)
    return sources
