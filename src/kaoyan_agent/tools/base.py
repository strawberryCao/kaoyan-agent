from kaoyan_agent.schemas.contracts import ToolRequest, ToolResult


class ToolAdapter:
    tool_name = "base"

    def run(self, request: ToolRequest) -> ToolResult:
        return ToolResult(
            tool_name=self.tool_name,
            status="error",
            error="Tool adapter is not implemented.",
        )


