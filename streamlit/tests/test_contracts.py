import unittest

from kaoyan_agent.schemas.contracts import (
    AgentRequest,
    AgentResponse,
    RetrievedItem,
    RouterDecision,
)


class ContractTest(unittest.TestCase):
    def test_agent_request_to_dict(self):
        item = RetrievedItem(source_type="memory", source_id=1, content="用户偏好先讲思路")
        request = AgentRequest(
            request_id="req-1",
            user_id="default",
            session_id=1,
            input_text="我该怎么复习",
            retrieved_items=[item],
        )
        data = request.to_dict()
        self.assertEqual(data["retrieved_items"][0]["source_type"], "memory")

    def test_agent_response_defaults(self):
        response = AgentResponse(text="ok")
        self.assertEqual(response.parse_status, "ok")
        self.assertEqual(response.errors, [])

    def test_router_decision_to_dict(self):
        decision = RouterDecision(route="planning", need_plan=True)
        self.assertTrue(decision.to_dict()["need_plan"])


if __name__ == "__main__":
    unittest.main()


