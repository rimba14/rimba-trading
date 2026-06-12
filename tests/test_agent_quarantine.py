
import unittest
import os
import json
from pathlib import Path
from agent_quarantine import QuarantineRegistry, AgentState, AgentUpdate

class TestAgentQuarantine(unittest.TestCase):
    def setUp(self):
        self.test_json = "test_agent_states.json"
        if os.path.exists(self.test_json):
            os.remove(self.test_json)
        self.registry = QuarantineRegistry(persist_path=self.test_json)

    def tearDown(self):
        if os.path.exists(self.test_json):
            os.remove(self.test_json)

    def test_register_and_update(self):
        # Register
        state = AgentState(is_initialized=False, training_episodes=0)
        self.registry.register("test_agent", state)
        self.assertFalse(self.registry._agents["test_agent"].is_qualified)

        # Update using new AgentUpdate dataclass (to be implemented)
        updates = AgentUpdate(is_initialized=True, training_episodes=1000)
        self.registry.update("test_agent", updates)

        updated_state = self.registry._agents["test_agent"]
        self.assertTrue(updated_state.is_qualified)
        self.assertEqual(updated_state.training_episodes, 1000)
        self.assertTrue(updated_state.is_initialized)

    def test_filter_agents(self):
        self.registry.register("good", AgentState(is_initialized=True, training_episodes=1000))
        self.registry.register("bad", AgentState(is_initialized=False))

        scores = {"good": 0.8, "bad": 0.2, "unknown": 0.5}
        result = self.registry.filter_agents(scores, strict=False)

        self.assertIn("good", result.filtered_scores)
        self.assertNotIn("bad", result.filtered_scores)
        self.assertIn("unknown", result.filtered_scores) # pass through in non-strict
        self.assertEqual(result.active_agents, 2)

if __name__ == "__main__":
    unittest.main()
