from .store import *
from .type import *
from .utils import *

import math

from datetime import datetime
from pydantic import BaseModel, Field


class _MemoryQueryItem(BaseModel):
    query: str = Field(description="用于向量检索的自然语言查询")
    type: MemoryType = Field(description="希望检索的记忆类型")
    top_k: int = Field(20, ge=1, le=50, description="返回的相关记忆条数")


class _MemoryQueryList(BaseModel):
    data: list[_MemoryQueryItem] = Field(description="查询列表，每个查询针对一类信息")


class _ScoreWeightItem(BaseModel):
    matching: float = Field(ge=0, le=1, description="语义匹配度权重")
    recency: float = Field(ge=0, le=1, description="记忆最后更新时间的新鲜度权重")
    effectiveness: float = Field(ge=0, le=1, description="记忆有效性分数的权重")
    heat: float = Field(ge=0, le=1, description="基于匹配度的热度权重")


class _ProblemQueryItem(BaseModel):
    query: str = Field(description="用于检索问题的自然语言查询")
    top_k: int = Field(10, ge=1, le=30, description="返回的相关问题条数")


class _ProblemQueryList(BaseModel):
    data: list[_ProblemQueryItem] = Field(description="问题查询列表")


class _ProblemScoreWeightItem(BaseModel):
    matching: float = Field(ge=0, le=1, description="语义匹配度权重")
    impact: float = Field(ge=0, le=1, description="问题影响分数权重")
    recency: float = Field(ge=0, le=1, description="问题添加时间的新鲜度权重")


def require_memory_query(
    model: BaseChatModel,
    messages: list[Message],
) -> _MemoryQueryList:
    prompt = """
你是一位考研记忆检索规划师。根据以下对话内容，判断为了回答用户当前问题或继续当前考研学习任务，需要从长期记忆库中检索哪些信息。

**考研场景检索重点**：
- 用户的目标院校、专业、考试科目。
- 用户的各科薄弱点。
- 曾经有效的学习策略。
- 用户的复习计划、当前进度、时间安排。
- 用户偏好的资料、老师或学习方式。

**生成规则**：
1. 识别用户当前核心需求。
2. 考虑对话历史中提及的旧概念、曾暴露的弱点、有效的策略等，生成针对性的查询。
3. 每个查询聚焦一个明确的信息类别，不要混合多个类型。
4. 如果对话很简短或用户只是闲聊，可以不生成任何查询。
5. 输出列表长度一般不超过 3 条。

输出格式遵循给定的 JSON schema。
"""
    conversation = flatten_messages(messages)
    content = f"""
对话记录如下：
{conversation}
"""

    return call_structured_model(
        model,
        prompt,
        content,
        _MemoryQueryList,
    )


def generate_score_weight(
    model: BaseChatModel,
    messages: list[Message],
) -> _ScoreWeightItem:
    prompt = """
你是一位考研记忆排序专家。根据以下对话上下文，决定在为用户检索相关记忆时，各项评分因素的重要性权重。

**权重字段说明**：
- `matching`: 语义匹配度。
- `time`: 记忆最后更新时间的新鲜度。
- `effectiveness`: 记忆本身的有效性分数。
- `heat`: 热度权重。

**考研场景权重分配原则**：
- 如果用户正在解决一个非常具体的知识点问题，应提高 `matching` 权重，精准命中。
- 如果用户频繁改变复习计划或询问“最近该复习什么”，应提高 `time` 权重，关注最新状态。
- 如果用户强调“以前用过的方法哪个最有效”或“哪些资料提分快”，应提高 `effectiveness` 权重。
- 如果用户表现出探索性提问，可适当提高 `heat` 权重，让中等匹配但有价值的经验浮现。

输出格式遵循给定的 JSON schema。
"""
    conversation = flatten_messages(messages)
    content = f"""
对话记录如下：
{conversation}
"""

    return call_structured_model(
        model,
        prompt,
        content,
        _ScoreWeightItem,
    )


def query_memories(
    memory_store: AbstractMemoryStore,
    query: str,
    type: MemoryType,
    top_k: int = 20,
) -> list[tuple[Memory, float]]:
    filter_dict = {
        "status": "active",
        "type": type,
    }

    documents = memory_store.similarity_search(
        query,
        top_k,
        filter=filter_dict,
    )

    return [(x[0]["metadata"], x[1]) for x in documents]  # type: ignore


def calculate_memory_score(
    memory: Memory,
    matching_score: float,
    weight: _ScoreWeightItem,
    now: datetime = datetime.now(),
) -> tuple[Memory, float]:
    def calculate_heat_score(
        similarity: float,
        peak: float = 0.55,
        sigma: float = 0.2,
    ) -> float:
        return math.exp(-((similarity - peak) ** 2) / (2 * sigma**2))

    def calculate_time_score(
        updated_at: str,
        now: datetime = now,
    ) -> float:
        return 1 / (1 + max(0, (now - datetime.fromisoformat(updated_at)).days))

    overall_score = (
        weight.matching * matching_score
        + weight.recency * calculate_time_score(memory["updated_at"])
        + weight.effectiveness * memory["effectiveness_score"]
        + weight.heat * calculate_heat_score(matching_score)
    )

    return (
        memory,
        overall_score,
    )


def retrieve_memories(
    model: BaseChatModel,
    memory_store: AbstractMemoryStore,
    messages: list[Message],
    top_k: int = 4,
) -> list[Memory]:
    memory_queries: list[_MemoryQueryItem] = require_memory_query(model, messages).data
    score_weight = generate_score_weight(model, messages)

    candidate_memories: list[tuple[Memory, float]] = []
    for x in memory_queries:
        candidate_memories.extend(
            query_memories(
                memory_store,
                x.query,
                x.type,
                x.top_k,
            )
        )

    scored_memories: list[tuple[Memory, float]] = [
        calculate_memory_score(x[0], x[1], score_weight) for x in candidate_memories
    ]
    scored_memories.sort(reverse=True, key=lambda x: x[1])
    return [x[0] for x in scored_memories[:top_k]]


def require_problem_query(
    model: BaseChatModel,
    messages: list[Message],
) -> _ProblemQueryList:
    prompt = """
你是一位考研问题诊断规划师。根据以下对话内容，判断为了解答用户当前疑问或推进学习，需要从问题库中检索哪些已记录的问题。

**考研场景问题检索重点**：
- 用户当前科目的具体知识漏洞。
- 用户反复遇到的解题方法错误。
- 影响复习进度的长期问题。
- 用户之前标记但尚未解决的问题。

**生成规则**：
1. 识别用户当前描述的学习困难或提问中暗示的潜在问题。
2. 每个查询应聚焦一个具体科目或一类问题，例如“数学级数收敛性判断问题”而非“数学问题”。
3. 如果对话未暴露任何明确问题，可以不生成查询。
4. 输出列表长度一般不超过 3 条。

输出格式遵循给定的 JSON schema。
"""
    conversation = flatten_messages(messages)
    content = f"""
对话记录如下：
{conversation}
"""
    return call_structured_model(
        model,
        prompt,
        content,
        _ProblemQueryList,
    )


def generate_problem_score_weight(
    model: BaseChatModel,
    messages: list[Message],
) -> _ProblemScoreWeightItem:
    prompt = """
你是一位考研问题排序专家。根据以下对话上下文，决定在检索相关问题时，各项评分因素的重要性权重。

**权重字段说明**：
- `matching`: 查询与问题描述之间的语义匹配度。
- `impact`: 问题的影响分数，分数越高代表对考研成绩阻碍越大。
- `recency`: 问题添加时间的新鲜度，近期出现的问题更应关注。

**考研场景权重分配原则**：
- 如果用户正在解决具体题目或知识点，应提高 `matching` 权重，精准匹配历史类似问题。
- 如果用户面临多处困难且时间紧迫，应提高 `impact` 权重，优先检索影响大的问题。
- 如果用户提到“最近总是错这类题”或“这几天一直没搞懂”，应提高 `recency` 权重。
- 默认情况下，应给予 `status_open` 一定权重，让未解决的问题更容易被召回。

输出格式遵循给定的 JSON schema。
"""
    conversation = flatten_messages(messages)
    content = f"""
对话记录如下：
{conversation}
"""
    return call_structured_model(
        model,
        prompt,
        content,
        _ProblemScoreWeightItem,
    )


def query_problems(
    problem_store: AbstractProblemStore,
    query: str,
    top_k: int = 20,
) -> list[tuple[Problem, float]]:
    filter_dict = {"status": "in_progress"}

    documents = problem_store.similarity_search(
        query,
        top_k,
        filter=filter_dict,  # type: ignore
    )

    return [(x[0]["metadata"], x[1]) for x in documents]  # type: ignore


def calculate_problem_score(
    problem: Problem,
    similarity: float,
    weight: _ProblemScoreWeightItem,
    now: datetime = datetime.now(),
) -> tuple[Problem, float]:
    def calculate_time_score(
        updated_at: str,
        now: datetime = now,
    ) -> float:
        return 1 / (1 + max(0, (now - datetime.fromisoformat(updated_at)).days))

    overall_score = (
        weight.matching * similarity
        + weight.impact * problem["impact_score"]
        + weight.recency * calculate_time_score(problem["add_at"])
    )

    return (
        problem,
        overall_score,
    )


def retrieve_problems(
    model: BaseChatModel,
    problem_store: AbstractProblemStore,
    messages: list[Message],
    top_k: int = 3,
) -> list[Problem]:
    problem_queries = require_problem_query(model, messages).data
    score_weight = generate_problem_score_weight(model, messages)

    candidate_problems: list[tuple[Problem, float]] = []
    for x in problem_queries:
        candidate_problems.extend(
            query_problems(
                problem_store,
                x.query,
                top_k=x.top_k,
            )
        )

    scored_problems: list[tuple[Problem, float]] = [
        calculate_problem_score(x[0], x[1], score_weight) for x in candidate_problems
    ]
    scored_problems.sort(key=lambda x: x[1], reverse=True)

    return [x[0] for x in scored_problems[:top_k]]
