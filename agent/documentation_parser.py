"""Extract stable architecture facts from the supplied Markdown document."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from agent.specification import ApiEndpoint


class DocumentationParseError(ValueError):
    """Raised when an architecture documentation file cannot be used."""


@dataclass
class DocumentationFacts:
    """Facts that can be extracted from Architecture_Documentation.md."""

    project_name: str
    architecture_style: str
    technology_stack: dict[str, str] = field(default_factory=dict)
    components: list[str] = field(default_factory=list)
    api_endpoints: list[ApiEndpoint] = field(default_factory=list)
    data_entities: list[str] = field(default_factory=list)
    deployment_notes: list[str] = field(default_factory=list)
    requirements: list[str] = field(default_factory=list)


TECHNOLOGY_KEYS = {
    "Language/runtime": "runtime",
    "Web framework": "web_framework",
    "RPC/HTTP": "api_style",
    "Persistence": "database",
    "Cache": "cache",
    "Messaging": "messaging",
    "Search": "search",
    "Authn/authz": "authentication",
    "Observability": "observability",
    "CI/CD": "ci_cd",
    "Container runtime": "container_runtime",
    "Infra provisioning": "infrastructure",
}


def _unique(values: list[str]) -> list[str]:
    """Keep order while removing blank and duplicate values."""
    result: list[str] = []
    for value in values:
        clean_value = value.strip()
        if clean_value and clean_value not in result:
            result.append(clean_value)
    return result


def _slugify(name: str) -> str:
    """Turn a document title such as 'Space Fractions' into a safe project name."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "generated-project"


def _extract_project_name(text: str) -> str:
    match = re.search(r"The\s+(.+?)\s+system\s+is", text, flags=re.IGNORECASE)
    if not match:
        raise DocumentationParseError("Could not find the system name in the document.")
    return _slugify(match.group(1))


def _extract_architecture_style(text: str) -> str:
    match = re.search(
        r"Chosen architectural style:\s*(.+)", text, flags=re.IGNORECASE
    )
    if not match:
        raise DocumentationParseError("Could not find the chosen architecture style.")
    return match.group(1).strip().lower()


def _extract_technology_stack(text: str) -> dict[str, str]:
    stack: dict[str, str] = {}
    for label, key in TECHNOLOGY_KEYS.items():
        match = re.search(
            rf"^\*\s+{re.escape(label)}:\s*(.+?)(?:\s+\(Justification:|$)",
            text,
            flags=re.MULTILINE,
        )
        if match:
            stack[key] = match.group(1).strip()
    return stack


def _extract_components(text: str) -> list[str]:
    return _unique(
        re.findall(r"^\*\s+(\w+Component):", text, flags=re.MULTILINE)
    )


def _extract_api_endpoints(text: str) -> list[ApiEndpoint]:
    endpoints: list[ApiEndpoint] = []
    pattern = re.compile(
        r"^\s{2}(/[^\s:]+):\s*\n"
        r"^\s{4}(get|post|put|patch|delete):\s*\n"
        r"^\s{6}summary:\s*(.+)$",
        flags=re.MULTILINE | re.IGNORECASE,
    )
    for match in pattern.finditer(text):
        endpoint = ApiEndpoint(
            method=match.group(2), path=match.group(1), summary=match.group(3).strip()
        )
        if not any(
            existing.method == endpoint.method and existing.path == endpoint.path
            for existing in endpoints
        ):
            endpoints.append(endpoint)
    return endpoints


def _extract_data_entities(text: str) -> list[str]:
    return _unique(
        re.findall(r"CREATE\s+TABLE\s+([A-Za-z_][A-Za-z0-9_]*)", text, re.IGNORECASE)
    )


def _extract_deployment_notes(text: str) -> list[str]:
    notes: list[str] = []
    if "Kubernetes" in text:
        notes.append("Kubernetes deployment")
    replica_match = re.search(r"replicas:\s*(\d+)", text)
    if replica_match:
        notes.append(f"{replica_match.group(1)} replicas")
    if "PostgreSQL replication" in text:
        notes.append("PostgreSQL replication")
    return notes


def _extract_requirements(text: str) -> list[str]:
    requirements: list[str] = []
    for requirement_id, description in re.findall(
        r"^\|\s*((?:FR|NFR|ASR)-\d+)\s*\|\s*([^|]+?)\s*\|",
        text,
        flags=re.MULTILINE,
    ):
        requirements.append(f"{requirement_id}: {description.strip()}")
    return _unique(requirements)


def parse_documentation(path: Path) -> DocumentationFacts:
    """Read an architecture Markdown file and return the facts needed downstream."""
    if not path.is_file():
        raise DocumentationParseError(f"Documentation file does not exist: {path}")

    text = path.read_text(encoding="utf-8")
    return DocumentationFacts(
        project_name=_extract_project_name(text),
        architecture_style=_extract_architecture_style(text),
        technology_stack=_extract_technology_stack(text),
        components=_extract_components(text),
        api_endpoints=_extract_api_endpoints(text),
        data_entities=_extract_data_entities(text),
        deployment_notes=_extract_deployment_notes(text),
        requirements=_extract_requirements(text),
    )
