"""Tests for the task-focused PlantUML parser."""

from __future__ import annotations

import unittest
from agent.uml_parser import parse_uml_views
from tests.fixtures import architecture_documents


class UmlParserTests(unittest.TestCase):
    def test_extracts_roles_domain_model_and_interactions(self) -> None:
        with architecture_documents() as (_, views):
            facts = parse_uml_views(views)

        self.assertEqual(facts.actors, ["EndUser", "Admin"])
        self.assertIn("PlayGame", facts.use_cases)
        self.assertIn("Question", facts.entities)
        self.assertIn("AdminComponent", facts.components)
        self.assertIn("Game --* Question", facts.relationships)
        self.assertIn("User -> Game: submit answer", facts.interactions)
        self.assertEqual(facts.states, ["Playing", "Paused", "GameOver"])
