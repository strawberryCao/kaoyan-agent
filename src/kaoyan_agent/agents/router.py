from kaoyan_agent.schemas.contracts import RouterDecision


class Router:
    PLAN_KEYWORDS = {"计划", "今日任务", "作战台", "安排", "明天学什么"}
    SEARCH_KEYWORDS = {"最新", "政策", "招生", "官网", "分数线", "院校"}
    FILE_KEYWORDS = {"文件", "上传", "pdf", "资料"}
    PRACTICE_KEYWORDS = {"错题", "复刷", "看懂答案", "不会做", "同型题"}
    FOCUS_KEYWORDS = {"番茄钟", "督学", "专注", "暂停", "摄像头"}
    MEMORY_KEYWORDS = {"我之前", "我的问题", "长期", "最近", "复盘", "为什么总是"}

    def route(self, rewritten_query: str) -> RouterDecision:
        text = rewritten_query or ""
        decision = RouterDecision(
            route="chat",
            need_memory=False,
            retrieval_weights={
                "matching_score": 0.55,
                "time_score": 0.2,
                "effectiveness_score": 0.2,
                "heat_score": 0.05,
            },
            reason="default chat route",
        )

        if any(keyword in text for keyword in self.MEMORY_KEYWORDS):
            decision.need_memory = True
            decision.reason = "request likely depends on long-term context"

        if any(keyword in text for keyword in self.PLAN_KEYWORDS):
            decision.route = "planning"
            decision.need_plan = True
            decision.need_memory = True
            decision.reason = "planning request"
            decision.retrieval_weights.update({"time_score": 0.3})

        if any(keyword in text for keyword in self.PRACTICE_KEYWORDS):
            decision.route = "practice_review"
            decision.need_problem_discovery = True
            decision.need_memory = True
            decision.reason = "practice review or method gap request"

        if any(keyword in text for keyword in self.FOCUS_KEYWORDS):
            decision.route = "focus"
            decision.need_memory = True
            decision.reason = "focus supervision request"

        if any(keyword in text for keyword in self.SEARCH_KEYWORDS):
            decision.need_search = True
            decision.need_tools = True
            decision.reason = "current external information may be required"

        if any(keyword in text.lower() for keyword in self.FILE_KEYWORDS):
            decision.need_file = True
            decision.need_tools = True
            decision.reason = "file handling may be required"

        return decision


