from .type import *
from .utils import *

import uuid

from datetime import datetime
from pydantic import BaseModel, Field


class _SummaryItem(BaseModel):
    summary: str = Field(description="当日学习总结")
    next_action: Action = Field(description="下一步行动建议")
    emotion: Emotion = Field(description="用户表现出的主要情绪")
    stress_level: int = Field(ge=0, le=10, description="压力水平")


class _NewMemoryItem(BaseModel):
    content: str = Field(description="记忆的具体内容")
    type: MemoryType = Field(description="记忆类型")
    confidence_score: int = Field(ge=0, le=10, description="对记忆准确性的置信度")
    effectiveness_score: int = Field(ge=0, le=10, description="该记忆内容的有效性")


class _NewMemoryList(BaseModel):
    data: list[_NewMemoryItem] = Field(description="新提取的记忆列表")


class _NewProblemItem(BaseModel):
    title: str = Field(description="问题标题")
    description: str = Field(description="详细描述问题的表现、原因及影响")
    impact_score: int = Field(ge=0, le=10, description="该问题对考研学习效果的阻碍程度")


class _NewProblemList(BaseModel):
    data: list[_NewProblemItem] = Field(description="新发现的问题列表")


class _UpdatedProblemItem(BaseModel):
    uuid: str = Field(description="已有问题的唯一标识")
    status: ProblemStatus = Field(description="更新后的问题状态")


class _UpdatedProblemList(BaseModel):
    data: list[_UpdatedProblemItem] = Field(description="需要更新状态的问题列表")


class _UpdatedMemoryItem(BaseModel):
    uuid: str = Field(description="已有记忆的唯一标识")
    status: MemoryStatus = Field(description="记忆状态")
    confidence_score: int = Field(ge=0, le=10, description="更新后的置信度")
    effectiveness_score: int = Field(ge=0, le=10, description="更新后的有效性评分")


class _UpdatedMemoryList(BaseModel):
    data: list[_UpdatedMemoryItem] = Field(description="需要更新的记忆列表")


def generate_summary(
    model: BaseChatModel,
    messages: list[Message],
) -> _SummaryItem:
    prompt = """
你是一位考研学习分析助手。根据用户与助手的对话记录，生成当日的考研学习总结。

**分析重点**：
- 用户复习的科目及具体内容。
- 完成的习题数量、正确率、暴露的知识盲区。
- 学习时长、专注度、阶段性目标完成情况。
- 情绪与压力：是否因真题错误率高而焦虑，或因突破难点而充满信心。

请按照给定的 JSON schema 输出，无需额外解释。
"""
    messages_text = flatten_messages(messages)
    content = f"""
对话记录如下：
{messages_text}
"""

    return call_structured_model(
        model,
        prompt,
        content,
        _SummaryItem,
    )


def extract_new_memories(
    model: BaseChatModel,
    messages: list[Message],
) -> _NewMemoryList:
    prompt = """
你是一位考研信息提取专家。从对话中提取值得长期记住的关键信息，聚焦对考研复习有长期价值的内容。

**提取规则**：
- 用户的目标院校、专业、理想分数。
- 用户的复习计划、作息规律、常用学习资料。
- 各科目具体弱点。
- 曾经有效的策略。
- 用户表达的信念、动力或长期困扰。

忽略日常寒暄和单次简单确认。
输出格式请遵循给定的 JSON schema。
"""
    messages_text = flatten_messages(messages)
    content = f"""
对话记录如下：
{messages_text}
    """

    return call_structured_model(
        model,
        prompt,
        content,
        _NewMemoryList,
    )


def update_memories(
    model: BaseChatModel,
    new_memories: list[Memory],
    exist_memories: list[Memory],
) -> _UpdatedMemoryList:
    prompt = """
你是一位考研记忆管理专家。现有系统已存储了一批长期记忆，同时根据最新对话提取了新记忆。请逐条判断每条新记忆与已有记忆的关系，并决定如何更新。

输出格式请遵循给定的 JSON schema。
"""
    new_memories_text = flatten_memories(new_memories)
    exist_memories_text = flatten_memories(exist_memories)
    content = f"""
现有记忆列表：
{exist_memories_text}

新记忆列表：
{new_memories_text}
"""

    return call_structured_model(
        model,
        prompt,
        content,
        _UpdatedMemoryList,
    )


def extract_new_problems(
    model: BaseChatModel,
    messages: list[Message],
) -> _NewProblemList:
    prompt = """
你是一位考研诊断专家。从对话中识别出用户在学习过程中暴露的、影响考研成绩的具体问题。

**诊断范围**：
- 知识漏洞：某个数学公式不会用、政治史实混淆、专业课概念不清。
- 方法问题：做题不写步骤、英语阅读先看选项、复习不做总结。
- 习惯问题：拖延、计划不合理、时间分配失衡。
- 心理障碍：畏难情绪、自我怀疑、考场紧张。

每个问题必须具体、可解决。同一问题多次出现时合并。
输出格式请遵循给定的 JSON schema。
"""
    messages_text = flatten_messages(messages)
    content = f"""
对话记录如下：
{messages_text}
    """

    return call_structured_model(
        model,
        prompt,
        content,
        _NewProblemList,
    )


def update_problems(
    model: BaseChatModel,
    messages: list[Message],
    exist_problems: list[Problem],
) -> _UpdatedProblemList:
    prompt = """
你是一位考研问题跟踪专家。根据最新对话内容，判断已有问题列表中哪些问题的状态需要改变。

**状态变更依据**：
- 用户明确表示某个问题已解决→ status = "resolved"。
- 用户正在采取措施解决→ status = "in_progress"。
- 用户放弃解决或问题不再相关 → status = "closed"。
- 没有变化 → 不输出该问题。

**注意**：只输出状态发生变化的问题，保持原有 uuid。输出列表顺序任意，但每个元素必须包含 uuid 和 status。
输出格式请遵循给定的 JSON schema。
"""
    messages_text = flatten_messages(messages)
    exist_problems_text = flatten_problems(exist_problems)
    content = f"""
最新对话：
{messages_text}

已有问题列表：
{exist_problems_text}
"""

    return call_structured_model(
        model,
        prompt,
        content,
        _UpdatedProblemList,
    )


def summarize_diary(
    model: BaseChatModel,
    messages: list[Message],
    exist_memories: list[Memory],
    exist_problems: list[Problem],
    date: datetime = datetime.today(),
) -> Diary:
    date_text: str = date.isoformat()

    raw_summary: _SummaryItem = generate_summary(model, messages)
    raw_new_memories: _NewMemoryList = extract_new_memories(model, messages)
    raw_new_problems: _NewProblemList = extract_new_problems(model, messages)
    raw_updated_problems: _UpdatedProblemList = update_problems(
        model, messages, exist_problems
    )

    summary: Summary = {
        "summary": raw_summary.summary,
        "next_action": raw_summary.next_action,
        "emotion": raw_summary.emotion,
        "stress_level": raw_summary.stress_level,
    }

    new_memories: list[Memory] = [
        {
            "uuid": str(uuid.uuid4()),
            "type": x.type,
            "content": x.content,
            "confidence_score": x.confidence_score,
            "effectiveness_score": x.effectiveness_score,
            "add_at": date_text,
            "updated_at": date_text,
            "last_used_at": date_text,
            "status": "active",
        }
        for x in raw_new_memories.data
    ]

    new_problems: list[Problem] = [
        {
            "uuid": str(uuid.uuid4()),
            "title": x.title,
            "description": x.description,
            "impact_score": x.impact_score,
            "add_at": date_text,
            "status": "open",
        }
        for x in raw_new_problems.data
    ]

    raw_updated_memories: _UpdatedMemoryList = update_memories(
        model,
        new_memories,
        exist_memories,
    )

    updated_memories: list[Memory] = []
    exist_memories_dict: dict[str, Memory] = {x["uuid"]: x for x in exist_memories}
    for x in raw_updated_memories.data:
        updated_memories.append(
            {
                **exist_memories_dict[x.uuid],
                "confidence_score": x.confidence_score,
                "effectiveness_score": x.effectiveness_score,
                "status": x.status,
            }
        )

    updated_problems: list[Problem] = []
    exist_problems_dict: dict[str, Problem] = {x["uuid"]: x for x in exist_problems}
    for x in raw_updated_problems.data:
        updated_problems.append(
            {
                **exist_problems_dict[x.uuid],
                "status": x.status,
            }
        )

    return {
        "add_at": date_text,
        "summary": summary,
        "new_memories": new_memories,
        "updated_memories": updated_memories,
        "new_problems": new_problems,
        "updated_problems": updated_problems,
    }
