"""
Hommey MCP Server
将 Hommey 商旅助手的核心能力暴露为 MCP Tools，供外部 AI 应用（Claude Desktop、Cursor 等）调用。

基于 mcp.server.fastmcp.FastMCP，使用装饰器模式注册工具。
支持 stdio 传输（与 Claude Desktop 兼容）。
"""
import asyncio
import json
import sys
import os
import logging
from typing import Optional

# 确保项目根目录在路径中
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from mcp.server.fastmcp import FastMCP
from runtime import create_agent_runtime

logger = logging.getLogger(__name__)


class HommeyMCPServer:
    """
    Hommey MCP Server - 将行程规划、偏好管理、知识问答等能力暴露为 MCP Tools。

    使用方式：
        python hommey_mcp/run_server.py
    或通过 Claude Desktop 配置：
        {
            "mcpServers": {
                "hommey": {
                    "command": "python",
                    "args": ["hommey_mcp/run_server.py"]
                }
            }
        }
    """

    def __init__(self):
        self._model = None
        self._memory_manager = None
        self._intention_agent = None
        self._agent_registry = None
        self._orchestrator = None
        self._agent_cache = {}
        self._initialized = False

    async def initialize(self):
        """Initialize the shared Hommey runtime for MCP tools."""
        if self._initialized:
            return

        runtime = create_agent_runtime(
            user_id="mcp_user",
            session_id="mcp_session",
            agent_cache=self._agent_cache,
        )

        self._model = runtime.model
        self._memory_manager = runtime.memory_manager
        self._intention_agent = runtime.intention_agent
        self._agent_registry = runtime.agent_registry
        self._orchestrator = runtime.orchestrator
        self._agent_cache = runtime.agent_cache

        self._initialized = True
        logger.info("Hommey MCP Server initialized")

    def _ensure_initialized(self):
        """同步检查初始化状态（FastMCP 工具是同步的）"""
        if not self._initialized:
            raise RuntimeError("Hommey MCP Server not initialized. Call initialize() first.")


# ─── 全局 Server 实例 ───────────────────────────────────────

_hommey = HommeyMCPServer()

server = FastMCP(
    name="hommey-travel-assistant",
    instructions="""Hommey 商旅助手 - 智能差旅规划系统。
提供以下能力：
- 行程规划：根据出发地、目的地、日期生成完整行程
- 差旅政策查询：查询企业差旅标准、报销政策
- 天气查询：查询目的地天气
- 网络搜索：搜索旅行相关信息
- 偏好管理：查询和保存用户出行偏好
- 历史行程：查询用户历史出行记录""",
)


# ─── 工具注册 ───────────────────────────────────────────────

@server.tool()
async def plan_trip(
    origin: str,
    destination: str,
    date: Optional[str] = None,
    purpose: Optional[str] = None,
    duration: Optional[str] = None,
) -> str:
    """
    规划出行行程。根据出发地、目的地、日期等信息生成完整的行程计划，
    包含每日安排、交通建议、住宿推荐等。

    Args:
        origin: 出发城市，如"上海"
        destination: 目的城市，如"北京"
        date: 出发日期，如"2026-05-15"（可选，默认使用当前日期）
        purpose: 出行目的，如"出差"、"旅游"（可选）
        duration: 行程时长，如"3天"（可选）
    """
    await _hommey.initialize()

    from datetime import datetime
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    # 构建查询
    query_parts = [f"从{origin}去{destination}"]
    if date:
        query_parts.append(f"{date}出发")
    if duration:
        query_parts.append(f"共{duration}")
    if purpose:
        query_parts.append(purpose)
    user_query = "，".join(query_parts)

    try:
        # 使用完整的 Agent 流水线
        from agentscope.message import Msg

        # 意图识别
        context_msgs = [Msg(name="user", content=user_query, role="user")]
        intention_result = await _hommey._intention_agent.reply(context_msgs)
        intention_data = json.loads(intention_result.content)

        # 构建 agent_schedule（确保包含行程规划）
        if not any(t.get("agent_name") == "itinerary_planning" for t in intention_data.get("agent_schedule", [])):
            intention_data["agent_schedule"] = [
                {"agent_name": "event_collection", "priority": 1, "reason": "收集行程信息"},
                {"agent_name": "itinerary_planning", "priority": 2, "reason": "生成行程计划"},
            ]

        # 调度执行

        orch_result = await _hommey._orchestrator.reply(
            Msg(name="intention", content=json.dumps(intention_data, ensure_ascii=False), role="assistant")
        )
        result_data = json.loads(orch_result.content)

        # 提取行程信息
        for r in result_data.get("results", []):
            if r.get("agent_name") == "itinerary_planning":
                itinerary = r.get("data", {}).get("itinerary")
                if itinerary:
                    return json.dumps(itinerary, ensure_ascii=False, indent=2)

        return json.dumps(result_data, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"行程规划失败: {e}")
        return f"行程规划出错: {str(e)}"


@server.tool()
async def query_travel_policy(question: str) -> str:
    """
    查询企业差旅政策、报销标准等知识库内容。
    基于 RAG（检索增强生成）从企业知识库中检索相关文档并回答。

    Args:
        question: 要查询的问题，如"北京的住宿标准是多少"、"差旅报销流程是什么"
    """
    await _hommey.initialize()

    try:
        from agentscope.message import Msg

        rag_agent = _hommey._agent_registry["rag_knowledge"]
        result = await rag_agent.reply(
            [Msg(name="user", content=question, role="user")]
        )

        result_data = json.loads(result.content)
        answer = result_data.get("answer", str(result_data))
        return answer

    except Exception as e:
        logger.error(f"政策查询失败: {e}")
        return f"政策查询出错: {str(e)}"


@server.tool()
async def get_weather(city: str) -> str:
    """
    查询指定城市的天气信息。

    Args:
        city: 城市名称，如"北京"、"上海"
    """
    await _hommey.initialize()

    try:
        from agentscope.message import Msg

        info_agent = _hommey._agent_registry["information_query"]
        result = await info_agent.reply(
            [Msg(name="user", content=f"{city}天气", role="user")]
        )

        result_data = json.loads(result.content)
        summary = result_data.get("results", {}).get("summary", str(result_data))
        return summary

    except Exception as e:
        logger.error(f"天气查询失败: {e}")
        return f"天气查询出错: {str(e)}"


@server.tool()
async def search_web(query: str) -> str:
    """
    搜索网络信息，获取旅行相关的实时信息。

    Args:
        query: 搜索关键词，如"北京故宫开放时间"、"上海到北京高铁"
    """
    await _hommey.initialize()

    try:
        from agentscope.message import Msg

        info_agent = _hommey._agent_registry["information_query"]
        result = await info_agent.reply(
            [Msg(name="user", content=f"搜索 {query}", role="user")]
        )

        result_data = json.loads(result.content)
        summary = result_data.get("results", {}).get("summary", str(result_data))
        return summary

    except Exception as e:
        logger.error(f"网络搜索失败: {e}")
        return f"搜索出错: {str(e)}"


@server.tool()
async def get_user_preferences() -> str:
    """
    查询当前用户的出行偏好设置，包括常用航司、酒店品牌、座位偏好等。
    """
    await _hommey.initialize()

    try:
        prefs = _hommey._memory_manager.long_term.get_preference()
        if not prefs:
            return "暂无偏好设置"
        return json.dumps(prefs, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"偏好查询失败: {e}")
        return f"查询出错: {str(e)}"


@server.tool()
async def save_preference(key: str, value: str) -> str:
    """
    保存用户出行偏好。

    Args:
        key: 偏好类型，如"hotel_brands"、"airlines"、"seat_preference"、"home_location"
        value: 偏好值，如"汉庭,如家"、"东航"、"靠窗"、"上海"
    """
    await _hommey.initialize()

    try:
        current = _hommey._memory_manager.long_term.get_preference()
        current[key] = value
        _hommey._memory_manager.long_term.save_preference(key, value)
        return f"已保存偏好: {key} = {value}"
    except Exception as e:
        logger.error(f"偏好保存失败: {e}")
        return f"保存出错: {str(e)}"


@server.tool()
async def get_trip_history(limit: int = 5) -> str:
    """
    查询用户历史出行记录。

    Args:
        limit: 返回记录数量，默认5条
    """
    await _hommey.initialize()

    try:
        trips = _hommey._memory_manager.long_term.get_trip_history(limit)
        if not trips:
            return "暂无历史行程记录"
        return json.dumps(trips, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"历史行程查询失败: {e}")
        return f"查询出错: {str(e)}"
