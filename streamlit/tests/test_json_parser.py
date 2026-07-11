import unittest

from kaoyan_agent.core.json_parser import parse_json_object, response_candidates


class JSONParserTest(unittest.TestCase):
    def test_parse_plain_json_object(self):
        self.assertEqual(parse_json_object('{"a": 1}')["a"], 1)

    def test_parse_fenced_json_object(self):
        parsed = parse_json_object('```json\n{"status": "ok"}\n```')
        self.assertEqual(parsed["status"], "ok")

    def test_parse_embedded_json_object(self):
        parsed = parse_json_object('prefix {"route": "chat"} suffix')
        self.assertEqual(parsed["route"], "chat")

    def test_candidates_skip_empty(self):
        self.assertEqual(response_candidates(""), [])


if __name__ == "__main__":
    unittest.main()


