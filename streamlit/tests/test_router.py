import unittest

from kaoyan_agent.agents.router import Router


class RouterTest(unittest.TestCase):
    def test_memory_request_enables_retrieval(self):
        decision = Router().route("我最近为什么总是完不成计划")
        self.assertTrue(decision.need_memory)

    def test_planning_request_routes_to_planning(self):
        decision = Router().route("帮我安排今日任务")
        self.assertEqual(decision.route, "planning")
        self.assertTrue(decision.need_plan)

    def test_search_request_sets_search_tool_flags(self):
        decision = Router().route("最新招生政策是什么")
        self.assertTrue(decision.need_search)
        self.assertTrue(decision.need_tools)


if __name__ == "__main__":
    unittest.main()


