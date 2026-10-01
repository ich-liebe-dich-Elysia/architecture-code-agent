"""Extract a deliberately small, task-focused subset of PlantUML syntax."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


class UmlParseError(ValueError):
    """Raised when an Architecture_View.md file cannot be used."""


@dataclass
class UmlFacts:
    """Facts extracted from the PlantUML diagrams in Architecture_View.md."""

    actors: list[str] = field(default_factory=list)
    use_cases: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    components: list[str] = field(default_factory=list)
    relationships: list[str] = field(default_factory=list)
    interactions: list[str] = field(default_factory=list)
    states: list[str] = field(default_factory=list)


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        clean_value = value.strip()
        if clean_value and clean_value not in result:
            result.append(clean_value)
    return result


def parse_uml_views(path: Path) -> UmlFacts:
    """Parse the fixed PlantUML constructs used by this assignment.

    This is intentionally not a full PlantUML parser. A production parser is
    unnecessary here; extracting the constructs that occur in the supplied
    diagrams is easier to understand and produces deterministic output.
    """
    if not path.is_file():
        raise UmlParseError(f"Architecture view file does not exist: {path}")

    text = path.read_text(encoding="utf-8")
    actors = re.findall(r"^actor\s+(\w+)", text, flags=re.MULTILINE)
    use_cases = re.findall(
        r'^\s*usecase\s+"[^"]+"\s+as\s+\((\w+)\)', text, flags=re.MULTILINE
    )
    entities = re.findall(r"^class\s+(\w+)", text, flags=re.MULTILINE)
    components = re.findall(
        r"^artifact\s+(\w+Component)\b", text, flags=re.MULTILINE
    )
    states = re.findall(r"^state\s+(\w+)", text, flags=re.MULTILINE)
    relationships = re.findall(
        r"^(\w+\s+--[*o]?\s+\w+)$", text, flags=re.MULTILINE
    )

    interactions: list[str] = []
    for source, target, message in re.findall(
        r"^(\w+)\s*->>\s*(\w+):\s*(.+)$", text, flags=re.MULTILINE
    ):
        interactions.append(f"{source} -> {target}: {message.strip()}")

    return UmlFacts(
        actors=_unique(actors),
        use_cases=_unique(use_cases),
        entities=_unique(entities),
        components=_unique(components),
        relationships=_unique(relationships),
        interactions=_unique(interactions),
        states=_unique(states),
    )
