import re

from kaoyan_agent.schemas.contracts import RouterDecision


class Router:
    PLAN_KEYWORDS = {
        "计划",
        "今日任务",
        "今日作战台",
        "作战台",
        "安排",
        "明天学什么",
        "创建",
        "加一个",
        "加上",
        "任务",
    }
    SEARCH_KEYWORDS = {"最新", "政策", "招生", "官网", "分数线", "院校"}
    FILE_KEYWORDS = {"文件", "上传", "pdf", "资料"}
    PRACTICE_KEYWORDS = {
        "错题",
        "错题卡",
        "复刷",
        "看懂答案",
        "不会做",
        "不会",
        "同型题",
        "错因",
        "原因是",
    }
    FOCUS_KEYWORDS = {
        "番茄钟",
        "开始番茄钟",
        "督学",
        "专注",
        "专注统计",
        "暂停",
        "继续番茄钟",
        "摄像头",
    }
    MOTIVATION_KEYWORDS = {"抽签", "上岸签", "每日签", "运势签", "安抚签"}
    SCORE_KEYWORDS = {"成绩趋势", "分数趋势", "成绩记录", "成绩分析"}
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

        starts_timed_focus = re.search(r"开始\s*\d{1,3}\s*(分钟|分)", text) is not None
        if any(keyword in text for keyword in self.FOCUS_KEYWORDS) or starts_timed_focus:
            decision.route = "focus"
            decision.need_memory = True
            decision.reason = "focus supervision request"

        if any(keyword in text for keyword in self.MOTIVATION_KEYWORDS):
            decision.route = "motivation"
            decision.need_plan = True
            decision.need_memory = True
            decision.reason = "motivation or fortune card request"

        if any(keyword in text for keyword in self.SCORE_KEYWORDS):
            decision.route = "score_trend"
            decision.need_memory = True
            decision.reason = "score trend request"

        if any(keyword in text for keyword in self.SEARCH_KEYWORDS):
            decision.need_search = True
            decision.need_tools = True
            decision.reason = "current external information may be required"

        if any(keyword in text.lower() for keyword in self.FILE_KEYWORDS):
            decision.need_file = True
            decision.need_tools = True
            decision.reason = "file handling may be required"

        return decision
