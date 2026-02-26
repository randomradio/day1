# Day1 多框架快速集成方案

**Date**: 2026-02-25
**Scope**: Hooks/MCP + 多工具采集层 + OTEL Exporter

---

## 一、架构设计原则

### 1.1 核心理念

```
┌─────────────────────────────────────────────────────────────────┐
│                      AI Tools / Frameworks                      │
│  Claude Code │ Cursor │ LangGraph │ AutoGen │ CrewAI │ Custom  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Day1 Data Collection Layer                   │
│                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │ MCP Hooks   │  │ REST API    │  │ OTEL Collector          │ │
│  │ (Claude)    │  │ (通用)      │  │ (标准化采集)            │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Day1 Storage Layer                         │
│                                                                  │
│  conversations │ messages │ facts │ observations │ relations    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Export Layer                                │
│                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │ OTEL        │  │ REST API    │  │ MCP Tools               │ │
│  │ Exporter    │  │ Query       │  │ Search                  │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| **数据采集** | Hooks/MCP (Claude) + OTEL (通用) | Claude 用 MCP,其他框架用 OTEL 标准化 |
| **SDK 定位** | 简单的 REST 客户端 | 不过度封装,保持灵活 |
| **存储格式** | Day1 原生格式 + OTEL 语义兼容 | 两者兼顾,可相互转换 |
| **导出能力** | OTEL Exporter | 兼容现有可观测性生态 |

---

## 二、数据采集层设计

### 2.1 Claude Code: MCP Hooks (已有,保持)

**当前实现** - 完整保留:

```python
# src/day1/hooks/
├── session_start.py      # 会话开始,注入历史记忆
├── user_prompt.py        # 用户输入
├── pre_tool_use.py       # 工具调用前
├── post_tool_use.py      # 工具调用后
├── assistant_response.py # AI 响应
└── session_end.py        # 会话结束,整合记忆
```

### 2.2 通用采集: OTEL Collector (新增)

```python
# src/day1/otel/collector.py
"""
Day1 OpenTelemetry Collector

接收 OTEL Span/Event 数据,转换为 Day1 存储格式
支持:
- OTLP HTTP/gRPC 接收
- 自动提取对话数据
- 自动提取工具调用
"""

from opentelemetry.sdk.trace.export import SpanExporter
from opentelemetry.sdk.trace import ReadableSpan
from typing import Sequence
from datetime import datetime

import asyncio
from day1.db.engine import get_session
from day1.core.message_engine import MessageEngine
from day1.core.fact_engine import FactEngine


class Day1SpanExporter(SpanExporter):
    """
    OpenTelemetry Span Exporter to Day1

    将 OTEL Spans 转换为 Day1 conversations/messages
    """

    def __init__(
        self,
        branch_name: str = "main",
        session_id: str | None = None,
        auto_extract_facts: bool = True,
    ):
        self._branch = branch_name
        self._session_id = session_id
        self._auto_extract_facts = auto_extract_facts

    async def export(self, spans: Sequence[ReadableSpan]) -> "SpanExportResult":
        """导出 spans 到 Day1"""
        async for session in get_session():
            msg_engine = MessageEngine(session)
            fact_engine = FactEngine(session)

            # 按 trace_id 分组 (每个 trace = 一个对话)
            traces = self._group_by_trace(spans)

            for trace_id, trace_spans in traces.items():
                # 创建或获取 conversation
                conversation = await self._get_or_create_conversation(
                    msg_engine, trace_id, trace_spans
                )

                # 转换 spans 为 messages
                for span in trace_spans:
                    await self._span_to_message(msg_engine, conversation.id, span)

                # 自动提取 facts
                if self._auto_extract_facts:
                    await self._extract_facts_from_trace(
                        fact_engine, trace_id, trace_spans
                    )

        return SpanExportResult.SUCCESS

    def _group_by_trace(self, spans: Sequence[ReadableSpan]) -> dict[str, list[ReadableSpan]]:
        """按 trace_id 分组"""
        groups = {}
        for span in spans:
            trace_id = hex(span.context.trace_id)
            groups.setdefault(trace_id, []).append(span)
        return groups

    async def _get_or_create_conversation(
        self, msg_engine, trace_id: str, spans: list[ReadableSpan]
    ):
        """获取或创建对话"""
        # 从 root span 提取元数据
        root_span = next((s for s in spans if s.parent is None), spans[0])

        # 尝试获取现有对话
        existing = await msg_engine.list_conversations(
            branch_name=self._branch,
            metadata_json={"otel_trace_id": trace_id},
        )
        if existing:
            return existing[0]

        # 创建新对话
        title = root_span.attributes.get("gen_ai.session.id", f"Trace {trace_id[:8]}")
        return await msg_engine.create_conversation(
            session_id=self._session_id,
            title=title,
            branch_name=self._branch,
            metadata_json={"otel_trace_id": trace_id},
        )

    async def _span_to_message(self, msg_engine, conversation_id: str, span: ReadableSpan):
        """将 span 转换为 message"""
        # 提取角色
        span_kind = span.kind.name
        if span_kind == "SERVER":
            role = "user"
        elif span_kind == "CLIENT":
            role = "assistant"
        else:
            role = "system"  # INTERNAL/PRODUCER/CONSUMER

        # 提取内容
        content = span.attributes.get("gen_ai.input.value") or span.attributes.get("gen_ai.output.value")

        # 提取工具调用
        tool_calls = []
        for event in span.events:
            if event.name == "tool_call":
                tool_calls.append({
                    "name": event.attributes.get("tool.name"),
                    "input": event.attributes.get("tool.input"),
                    "output": event.attributes.get("tool.output"),
                })

        await msg_engine.write_message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            tool_calls_json=tool_calls if tool_calls else None,
            branch_name=self._branch,
            metadata_json={
                "otel_span_id": hex(span.context.span_id),
                "otel_parent_id": hex(span.parent.span_id) if span.parent else None,
                "span_name": span.name,
            },
        )

    async def _extract_facts_from_trace(self, fact_engine, trace_id: str, spans: list[ReadableSpan]):
        """从 trace 中自动提取 facts"""
        for span in spans:
            # 从 attributes 提取有意义的 facts
            for key, value in span.attributes.items():
                if self._is_fact_candidate(key, value):
                    await fact_engine.write_fact(
                        fact_text=str(value),
                        category=self._infer_category(key),
                        confidence=0.7,
                        session_id=self._session_id,
                        branch_name=self._branch,
                        metadata_json={"otel_source": f"{trace_id}:{hex(span.context.span_id)}"},
                    )

    def _is_fact_candidate(self, key: str, value) -> bool:
        """判断是否为候选 fact"""
        # 匹配特定的 attribute key 模式
        fact_patterns = [
            "user.preference",
            "config.setting",
            "feature.flag",
            "decision.made",
        ]
        return any(p in key.lower() for p in fact_patterns)

    def _infer_category(self, key: str) -> str:
        """从 key 推断 category"""
        key_lower = key.lower()
        if "preference" in key_lower:
            return "preference"
        elif "config" in key_lower or "setting" in key_lower:
            return "configuration"
        elif "error" in key_lower:
            return "error"
        else:
            return "observation"


# ───────────────────────────────────────────────────────────────
# OTEL Collector HTTP Server (接收 OTLP 数据)
# ───────────────────────────────────────────────────────────────

from fastapi import FastAPI, Request
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

app = FastAPI()
_exporter = Day1SpanExporter()

@app.post("/v1/traces")
async def export_traces(request: Request):
    """接收 OTEL OTLP trace 数据"""
    body = await request.body()
    request_pb = ExportTraceServiceRequest()
    request_pb.ParseFromString(body)

    # 转换为 ReadableSpan
    spans = _pb_to_spans(request_pb.resource_spans)

    # 导出到 Day1
    await _exporter.export(spans)

    return {"status": "success"}
```

### 2.3 LangGraph Instrumentation (示例)

```python
# examples/langgraph_otel.py
"""
LangGraph + Day1 通过 OTEL 集成
"""

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# 配置 Day1 作为 OTEL Exporter
from day1.otel.collector import Day1SpanExporter

tracer_provider = TracerProvider()
day1_exporter = Day1SpanExporter(
    branch_name="langgraph",
    auto_extract_facts=True,
)
processor = BatchSpanProcessor(day1_exporter)
tracer_provider.add_span_processor(processor)
trace.set_tracer_provider(tracer_provider)

# LangGraph 代码
from langgraph.graph import StateGraph

tracer = trace.get_tracer("langgraph-app")

@tracer.start_as_current_span("agent_run")
async def agent_node(state):
    # LangGraph 逻辑
    response = await llm.invoke(state["messages"])

    # OTEL 自动记录 span,Day1 自动接收并存储
    return {"messages": [response]}
```

### 2.4 通用 REST 采集 (简化)

```python
# examples/simple_rest.py
"""
简单 REST API 采集
"""

import requests
from day1.sdk.rest_client import Day1RestClient

# 简单的 REST 客户端
client = Day1RestClient(
    base_url="http://localhost:8000",
    api_key="your-key",
)

async def main():
    # 写入对话
    conv = await client.create_conversation(
        title="用户咨询",
        session_id="session-123",
    )

    await client.add_message(
        conversation_id=conv.id,
        role="user",
        content="如何使用 Day1?",
    )

    await client.add_message(
        conversation_id=conv.id,
        role="assistant",
        content="Day1 是一个类似 Git 的记忆层...",
    )

    # 自动提取 facts
    await client.consolidate(level="session")
```

---

## 三、Day1 数据模型与 OTEL 映射

### 3.1 映射表

| Day1 | OTEL | 说明 |
|-------|------|------|
| `Conversation` | `Trace` | 一个对话 = 一个 trace |
| `Message` | `Span` | 一条消息 = 一个 span |
| `message.role` | `span.kind` | user=SERVER, assistant=CLIENT |
| `message.tool_calls` | `span.events` | 工具调用 = span 事件 |
| `conversation.metadata_json["otel_trace_id"]` | `trace_id` | 关联 trace |
| `message.metadata_json["otel_span_id"]` | `span_id` | 关联 span |
| `Fact` | `span.attributes` (筛选) | 自动提取的 facts |

### 3.2 语义约定

```python
# 遵循 OTEL GenAI 语义约定
# https://github.com/open-telemetry/semantic-conventions/tree/main/docs/gen-ai

GEN_AI_ATTRIBUTES = {
    # Session
    "gen_ai.session.id": "conversation_id",

    # User
    "gen_ai.user.id": "user_id",

    # Model
    "gen_ai.model.name": "gpt-4",
    "gen_ai.model.provider": "openai",

    # Usage
    "gen_ai.usage.prompt_tokens": 150,
    "gen_ai.usage.completion_tokens": 300,

    # I/O
    "gen_ai.input.value": "user message",
    "gen_ai.output.value": "ai response",

    # Span Kind
    "gen_ai.span.kind": "LLM" | "CHAIN" | "RETRIEVER" | "TOOL",
}
```

---

## 四、文件结构

```
src/day1/
├── otel/                        # 新增: OTEL 集成
│   ├── __init__.py
│   ├── collector.py             # Day1SpanExporter
│   ├── server.py                # OTLP HTTP Server
│   └── instrumentation/          # 框架特定采集
│       ├── __init__.py
│       ├── langgraph.py         # LangGraph helper
│       └── autogen.py           # AutoGen helper
│
├── sdk/                         # 简化: 只保留 REST 客户端
│   ├── __init__.py
│   ├── client.py                # Day1Client (REST only)
│   └── types.py
│
├── hooks/                       # 保持: Claude Code Hooks
│   ├── session_start.py
│   ├── user_prompt.py
│   └── ...
│
├── mcp/                         # 保持: MCP Server
│   ├── mcp_server.py
│   └── tools.py
│
└── api/                         # 保持: REST API
    └── app.py

examples/
├── otel/
│   ├── langgraph.py             # LangGraph + OTEL
│   ├── autogen.py               # AutoGen + OTEL
│   └── custom.py                # 自定义应用 + OTEL
├── simple_rest.py               # 简单 REST 采集
└── claude_code_hooks.py         # Claude Code Hooks 示例
```

---

## 五、实现优先级

### Phase 1: OTEL Collector (3-4天) ⭐ 最高优先级

| 文件 | 描述 |
|------|------|
| `src/day1/otel/__init__.py` | 包初始化 |
| `src/day1/otel/collector.py` | Day1SpanExporter 实现 |
| `src/day1/otel/server.py` | OTLP HTTP Server |
| `tests/test_otel/test_collector.py` | 单元测试 |

### Phase 2: 框架 Instrumentation (2-3天)

| 文件 | 描述 |
|------|------|
| `src/day1/otel/instrumentation/langgraph.py` | LangGraph helper |
| `src/day1/otel/instrumentation/autogen.py` | AutoGen helper |
| `examples/otel/langgraph.py` | LangGraph 示例 |
| `examples/otel/autogen.py` | AutoGen 示例 |

### Phase 3: REST SDK (1-2天)

| 文件 | 描述 |
|------|------|
| `src/day1/sdk/__init__.py` | SDK 入口 |
| `src/day1/sdk/client.py` | Day1Client (REST) |
| `src/day1/sdk/types.py` | 类型定义 |
| `examples/simple_rest.py` | 简单示例 |

### Phase 4: 一键启动 (1天)

| 文件 | 描述 |
|------|------|
| `scripts/start.sh` | 智能启动脚本 |
| `scripts/check_db.py` | 数据库检查 |
| `scripts/start_otel.sh` | OTEL 服务启动 |

---

## 六、验证标准

- [ ] OTEL Collector 能接收 OTLP trace 数据并转换为 Day1 conversations
- [ ] LangGraph 示例能通过 OTEL 采集对话数据
- [ ] Claude Code Hooks 继续正常工作
- [ ] REST SDK 能正常写入和查询
- [ ] `bash scripts/start.sh` 能一键启动所有服务
