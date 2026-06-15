from typing import Any, Dict, List


class ProblemDiscoveryAgent:
    """Future boundary for discovering durable problems from evidence events.

    The current nightly memory workflow already writes validated discovered
    problems to the Problem Board, so this class intentionally stays minimal.
    """

    def discover(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return []

