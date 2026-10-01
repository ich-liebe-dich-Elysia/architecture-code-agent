"""Tests for the Markdown architecture-document parser."""

from __future__ import annotations

import unittest
from agent.documentation_parser import parse_documentation
from tests.fixtures import architecture_documents


class DocumentationParserTests(unittest.TestCase):
    def test_extracts_the_core_architecture_facts(self) -> None:
        with architecture_documents() as (documentation, _):
            facts = parse_documentation(documentation)

        self.assertEqual(facts.project_name, "space-fractions")
        self.assertEqual(facts.architecture_style, "microservices")
        self.assertEqual(facts.technology_stack["runtime"], "Node.js 18-20")
        self.assertIn("GameComponent", facts.components)
        self.assertEqual(facts.api_endpoints[0].path, "/play")
        self.assertIn("games", facts.data_entities)
        self.assertIn("FR-1: Play game", facts.requirements)
