from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from kaoyan_agent.agents.nightly_memory_agent import NightlyMemoryAgent
from kaoyan_agent.core.settings import Settings


@dataclass
class ProblemDiscoveryResult:
    problems: List[Dict[str, Any]] = field(default_factory=list)
    parse_status: str = "failed"
    error_message: str = ""


class ProblemDiscoveryAgent:
    """Discover problem candidates from evidence without writing persistence."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        nightly_agent: Optional[NightlyMemoryAgent] = None,
    ):
        self.settings = settings
        self.nightly_agent = nightly_agent or NightlyMemoryAgent(settings)

    def discover(
        self,
        events: List[Dict[str, Any]],
        review_date: Optional[str] = None,
        memories: Optional[List[Dict[str, Any]]] = None,
        open_problems: Optional[List[Dict[str, Any]]] = None,
    ) -> ProblemDiscoveryResult:
        """Return validated problem candidates from raw evidence only.

        Persistence remains the responsibility of NightlyMemoryWorkflow and the
        repository/gate layer. A failed parse may contain fallback output, but it
        is not a valid discovery result and must not be surfaced as problems.
        """

        result = self.nightly_agent.run(
            review_date=review_date or datetime.now().astimezone().date().isoformat(),
            raw_events=events,
            memories=memories or [],
            open_problems=open_problems or [],
        )
        if result.parse_status != "success":
            return ProblemDiscoveryResult(
                problems=[],
                parse_status=result.parse_status,
                error_message=result.error_message
                or "problem discovery did not produce a valid structured result",
            )

        return ProblemDiscoveryResult(
            problems=[
                problem.model_dump()
                if hasattr(problem, "model_dump")
                else dict(problem)
                for problem in result.output.discovered_problems
            ],
            parse_status=result.parse_status,
            error_message=result.error_message,
        )

    def discover_from_graph(
        self,
        *,
        review_date: str,
        daily_graph: Dict[str, Any],
        recent_daily_graphs: Optional[List[Dict[str, Any]]] = None,
        global_graph_nodes: Optional[List[Dict[str, Any]]] = None,
        global_graph_edges: Optional[List[Dict[str, Any]]] = None,
        chroma_results: Optional[List[Dict[str, Any]]] = None,
        neo4j_neighbors: Optional[List[Dict[str, Any]]] = None,
        candidate_problems: Optional[List[Any]] = None,
        raw_events: Optional[List[Dict[str, Any]]] = None,
        memories: Optional[List[Dict[str, Any]]] = None,
        open_problems: Optional[List[Dict[str, Any]]] = None,
    ) -> ProblemDiscoveryResult:
        """Discover final problem candidates from graph-shaped context.

        This method intentionally returns data only. The workflow/gate/repository
        layer decides whether candidates are inserted or merged.
        """

        normalized_candidates = self._problem_dicts(candidate_problems or [])
        if normalized_candidates:
            return ProblemDiscoveryResult(
                problems=normalized_candidates,
                parse_status="success",
                error_message="",
            )

        context_event = {
            "source_type": "daily_memory_graph",
            "content": {
                "review_date": review_date,
                "daily_graph": daily_graph,
                "recent_daily_graphs": recent_daily_graphs or [],
                "global_graph_nodes": global_graph_nodes or [],
                "global_graph_edges": global_graph_edges or [],
                "chroma_results": chroma_results or [],
                "neo4j_neighbors": neo4j_neighbors or [],
                "raw_events": raw_events or [],
            },
        }
        result = self.nightly_agent.run(
            review_date=review_date,
            raw_events=[context_event],
            memories=memories or [],
            open_problems=open_problems or [],
            recent_daily_graphs=recent_daily_graphs or [],
            global_graph_nodes=global_graph_nodes or [],
            global_graph_edges=global_graph_edges or [],
        )
        if result.parse_status != "success":
            return ProblemDiscoveryResult(
                problems=[],
                parse_status=result.parse_status,
                error_message=result.error_message
                or "graph problem discovery did not produce a valid structured result",
            )

        output = result.output
        problems = self._problem_dicts(output.candidate_problems or output.discovered_problems)
        return ProblemDiscoveryResult(
            problems=problems,
            parse_status=result.parse_status,
            error_message=result.error_message,
        )

    @staticmethod
    def _problem_dicts(values: List[Any]) -> List[Dict[str, Any]]:
        problems: List[Dict[str, Any]] = []
        for value in values:
            if hasattr(value, "model_dump"):
                data = value.model_dump()
            elif isinstance(value, dict):
                data = dict(value)
            else:
                continue
            if str(data.get("description") or "").strip():
                problems.append(data)
        return problems

