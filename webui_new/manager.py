"""
Hommey 商旅助手 - Web 界面管理器
管理多用户 Hommey 实例的生命周期
"""
import asyncio
import json
import logging
import os
import sys
import time
import uuid
from typing import Optional

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from agents.intention_agent import IntentionAgent
from agents.orchestration_agent import OrchestrationAgent
from settings import RESILIENCE_CONFIG
from context.memory_manager import MemoryManager
from runtime import create_agent_runtime, create_circuit_breaker
from utils.circuit_breaker import CircuitBreaker, CircuitOpenError
from utils.llm_resilience import retry_with_backoff
from core.onboarding import InitialPreferenceOnboarding
from core.intent_router import FastIntentRouter
from core.intent_catalog import INTENT_DISPLAY_NAMES

logger = logging.getLogger(__name__)

# 智能体显示名称（统一来源：core.intent_catalog）
AGENT_DISPLAY_NAMES = INTENT_DISPLAY_NAMES


class HommeyWebInstance:
    """单个用户的 Hommey 实例"""

    # 简单闲聊匹配规则（不经过 LLM）
    CHITCHAT_PATTERNS = [
        "你好", "您好", "嗨", "hi", "hello", "hey",
        "谢谢", "感谢", "多谢", "thanks", "thank",
        "再见", "拜拜", "bye", "回头见",
        "在吗", "在不在", "有人吗",
        "哈哈", "呵呵", "好的", "ok", "okay",
        "没事", "没什么", "算了",
        "再见", "明天见", "下次见",
        "你叫什么", "你是谁", "你能做什么",
    ]

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.session_id = str(uuid.uuid4())[:8]
        self.memory_manager: Optional[MemoryManager] = None
        self.orchestrator: Optional[OrchestrationAgent] = None
        self.intention_agent: Optional[IntentionAgent] = None
        self.model = None
        self._agent_cache = {}
        self.circuit_breaker: Optional[CircuitBreaker] = None
        self.onboarding = InitialPreferenceOnboarding()
        self.initialized = False
        self.init_error: Optional[str] = None

        # ── 性能优化: 缓存 ──
        self._summary_cache: Optional[str] = None  # 长期记忆摘要缓存
        self._summary_msg_count: int = 0           # 缓存时的消息数
        self._total_messages: int = 0              # 本会话消息计数

    async def initialize(self):
        """Initialize the shared Hommey runtime for this web user."""
        try:
            runtime = create_agent_runtime(
                user_id=self.user_id,
                session_id=self.session_id,
                agent_cache=self._agent_cache,
            )

            self.model = runtime.model
            self.memory_manager = runtime.memory_manager
            self.intention_agent = runtime.intention_agent
            self.orchestrator = runtime.orchestrator
            self._agent_cache = runtime.agent_cache
            self.circuit_breaker = create_circuit_breaker()

            self.initialized = True
        except Exception as e:
            self.init_error = str(e)
            logger.error(f"Init failed for user {self.user_id}: {e}")
            raise

    async def get_preferences(self) -> dict:
        """获取用户偏好"""
        if not self.memory_manager:
            return {"preferences": [], "raw": {}}
        prefs = self.memory_manager.long_term.get_preference()
        if not prefs:
            return {"preferences": [], "raw": {}}
        # 转换为前端友好格式
        display_map = {
            "home_location": ("常驻地", "📍"),
            "transportation_preference": ("出行偏好", "🚄"),
            "hotel_brands": ("常住酒店", "🏨"),
            "airlines": ("常用航空", "✈️"),
            "seat_preference": ("座位偏好", "💺"),
            "meal_preference": ("餐食偏好", "🍜"),
            "budget_level": ("预算等级", "💰"),
        }
        result = []
        for key, value in prefs.items():
            if value:
                label, icon = display_map.get(key, (key, "📋"))
                display_value = value
                if isinstance(value, list):
                    display_value = " · ".join(str(v) for v in value)
                result.append({"icon": icon, "label": label, "value": display_value})
        return {"preferences": result, "raw": prefs}

    async def is_new_user(self) -> bool:
        """检查是否为新用户（没有任何偏好设置）"""
        if not self.memory_manager:
            return True
        return self.onboarding.needs_onboarding(self.memory_manager)

    async def get_onboarding_state(self) -> dict:
        """Return first-run preference setup progress."""
        if not self.memory_manager:
            return {"is_new": True, "completed": False, "missing_keys": []}
        return self.onboarding.get_state(self.memory_manager)

    async def save_onboarding_preference(self, key: str, value: str) -> dict:
        """Save one first-run preference without using the chat pipeline."""
        if not self.memory_manager:
            return {"success": False, "error": "系统未初始化"}
        return self.onboarding.save_answer(self.memory_manager, key, value)

    async def get_user_summary(self) -> dict:
        """获取用户摘要信息（用于右侧面板）"""
        prefs = await self.get_preferences()
        name_display = self.user_id
        if prefs["raw"].get("name"):
            name_display = prefs["raw"]["name"]
        return {
            "user_id": self.user_id,
            "name_display": name_display,
            "preferences": prefs["preferences"],
            "member_level": "白银会员",
            "member_tag": "差旅常客",
        }

    @staticmethod
    def _is_simple_chitchat(message: str) -> bool:
        """快速判断是否纯闲聊（不经过 LLM）"""
        msg = message.strip().lower()
        # 纯问候/感谢/告别
        for pattern in HommeyWebInstance.CHITCHAT_PATTERNS:
            if msg == pattern or msg.startswith(pattern) and len(msg) < 15:
                return True
        # 单字/简单表情
        if len(msg) <= 2 and msg in ("嗯", "哦", "啊", "好", "行", "ok"):
            return True
        return False

    async def _get_cached_summary(self, user_input: str) -> str:
        """获取缓存的长期记忆摘要（避免每次调用 LLM）"""
        current_count = len(self.memory_manager.short_term.messages)

        # 仅在首次或消息数增长超过阈值时重新生成
        if self._summary_cache is None or current_count - self._summary_msg_count >= 5:
            summary = await self._get_long_term_summary(user_input)
            if summary:
                self._summary_cache = summary
                self._summary_msg_count = current_count
                return summary
            elif self._summary_cache:
                return self._summary_cache
            return ""

        return self._summary_cache or ""

    async def process_message(self, message: str) -> dict:
        """处理用户消息，返回响应"""
        from agentscope.message import Msg

        start_time = time.perf_counter()
        timings = {}

        if not self.initialized:
            return {"error": "系统未初始化"}

        # ═══ 优化 1: 简单闲聊直接处理，不经过 LLM ═══
        if self._is_simple_chitchat(message):
            self.memory_manager.add_message("user", message)
            response = await self._handle_chitchat(message)
            self.memory_manager.add_message("assistant", response)
            return {"response": response, "agents": [], "preferences_updated": False}

        rc = RESILIENCE_CONFIG
        max_retries = rc.get("max_retries", 3)
        fast_route = self._route_without_context(message)

        if fast_route:
            intention_data = fast_route.to_intention_data(message)
            intention_result = Msg(
                name="IntentionAgent",
                content=json.dumps(intention_data, ensure_ascii=False),
                role="assistant",
            )
            timings["context"] = 0.0
            timings["intent"] = 0.0
        else:
            # ═══ 优化 2: 缓存长期记忆摘要，避免每次都 LLM 总结 ═══
            # 同时构建上下文和意图识别可以部分重叠
            context_future = asyncio.ensure_future(self._build_context(message))

            # 2. Intent recognition
            try:
                if self.circuit_breaker:
                    self.circuit_breaker.raise_if_open()

                context_start = time.perf_counter()
                context_messages = await context_future
                timings["context"] = time.perf_counter() - context_start

                intent_start = time.perf_counter()
                intention_result = await retry_with_backoff(
                    lambda: self.intention_agent.reply(context_messages),
                    max_retries=max_retries,
                    base_delay_sec=rc.get("retry_base_delay_sec", 1.0),
                    max_delay_sec=rc.get("retry_max_delay_sec", 30.0),
                )
                timings["intent"] = time.perf_counter() - intent_start
                if self.circuit_breaker:
                    self.circuit_breaker.record_success()
            except CircuitOpenError:
                return {"error": "服务暂时不可用，请稍后再试。"}
            except Exception as e:
                if self.circuit_breaker:
                    self.circuit_breaker.record_failure()
                logger.error(f"Intention agent failed: {e}")
                return {"error": f"处理请求时出错: {e}"}

        try:
            intention_data = json.loads(intention_result.content)
        except json.JSONDecodeError:
            return {"error": "抱歉，我没能理解您的意思，请换一种说法试试？"}

        self._total_messages += 1
        self.memory_manager.add_message("user", message)

        # 3. Orchestration
        try:
            orchestration_start = time.perf_counter()
            orchestration_result = await retry_with_backoff(
                lambda: self.orchestrator.reply(intention_result),
                max_retries=max_retries,
                base_delay_sec=rc.get("retry_base_delay_sec", 1.0),
                max_delay_sec=rc.get("retry_max_delay_sec", 30.0),
            )
            timings["orchestration"] = time.perf_counter() - orchestration_start
            if self.circuit_breaker:
                self.circuit_breaker.record_success()
        except CircuitOpenError:
            return {"error": "服务暂时不可用，请稍后再试。"}
        except Exception as e:
            if self.circuit_breaker:
                self.circuit_breaker.record_failure()
            logger.error(f"Orchestration failed: {e}")
            return {"error": f"调度执行失败: {e}"}

        try:
            result_data = json.loads(orchestration_result.content)
        except json.JSONDecodeError:
            result_data = {"error": "解析结果失败"}

        # 4. Chitchat fallback
        if result_data.get("status") == "no_agents" and not result_data.get("results"):
            if result_data.get("message"):
                response = result_data["message"]
                self.memory_manager.add_message("assistant", response)
                return {"response": response, "agents": [], "preferences_updated": False}
            response = await self._handle_chitchat(message)
            self.memory_manager.add_message("assistant", response)
            return {"response": response, "agents": [], "preferences_updated": False}

        # 5. Format response
        response = self._format_response(result_data)
        self.memory_manager.add_message("assistant", json.dumps(result_data, ensure_ascii=False))

        # 6. Extract agent names
        agents = []
        results = result_data.get("results", [])
        for r in results:
            name = r.get("agent_name", "")
            status = r.get("status", "")
            agents.append({
                "name": name,
                "display": AGENT_DISPLAY_NAMES.get(name, name),
                "status": status,
                "duration_sec": r.get("duration_sec"),
            })

        # 7. Check if preferences were updated
        prefs_updated = any(r.get("agent_name") == "preference" and r.get("status") == "success" for r in results)
        timings["total"] = time.perf_counter() - start_time
        logger.info(
            "WebUI message timing for %s: %s",
            self.user_id,
            {key: round(value, 3) for key, value in timings.items()},
        )

        return {
            "response": response,
            "agents": agents,
            "preferences_updated": prefs_updated,
            "timings": {key: round(value, 3) for key, value in timings.items()},
        }

    async def stream_message(self, message: str):
        """Yield JSON-serializable progress and response events for Web streaming."""
        yield {"type": "status", "message": "processing"}
        result = await self.process_message(message)
        if result.get("error"):
            yield {"type": "error", "error": result["error"]}
            return

        agents = result.get("agents", [])
        if agents:
            yield {"type": "agents", "agents": agents}

        response = result.get("response") or ""
        for chunk in self._chunk_text(response):
            yield {"type": "chunk", "text": chunk}
            await asyncio.sleep(0.01)

        yield {
            "type": "done",
            "preferences_updated": result.get("preferences_updated", False),
            "timings": result.get("timings", {}),
        }

    @staticmethod
    def _chunk_text(text: str, size: int = 18):
        for idx in range(0, len(text), size):
            yield text[idx:idx + size]

    @staticmethod
    def _route_without_context(message: str):
        """Run cheap routing before building memory context for context-free intents."""
        route = FastIntentRouter.route(message)
        if not route or len(route.agent_schedule) != 1:
            return None
        agent_name = route.agent_schedule[0].get("agent_name")
        if agent_name in {"rag_knowledge", "information_query", "chitchat"}:
            return route
        return None

    async def _build_context(self, message: str) -> list:
        """构建上下文消息（可与其他异步任务并行）"""
        from agentscope.message import Msg

        long_term_summary = await self._get_cached_summary(message)
        recent_context = self.memory_manager.short_term.get_recent_context(n_turns=5)

        context_messages = []
        if long_term_summary:
            context_messages.append(Msg(name="system", content=long_term_summary, role="system"))
        for msg in recent_context:
            context_messages.append(Msg(name=msg["role"], content=msg["content"], role=msg["role"]))
        context_messages.append(Msg(name="user", content=message, role="user"))

        return context_messages

    async def _get_long_term_summary(self, user_input: str = "") -> str:
        """生成长期记忆摘要"""
        summary_parts = []
        prefs = self.memory_manager.long_term.get_preference()
        if prefs:
            pref_lines = ["【用户背景信息】（来自长期记忆）"]
            for pref_key, pref_value in prefs.items():
                if pref_value:
                    if isinstance(pref_value, list):
                        pref_lines.append(f"• {pref_key}: {', '.join(pref_value)}")
                    else:
                        pref_lines.append(f"• {pref_key}: {pref_value}")
            if len(pref_lines) > 1:
                summary_parts.extend(pref_lines)

        chat_summary = await self.memory_manager.get_long_term_summary_async(max_messages=20)
        if chat_summary:
            summary_parts.append("\n【历史会话总结】")
            summary_parts.append(chat_summary)

        all_trips = self.memory_manager.long_term.get_trip_history(limit=None)
        if all_trips:
            relevant_trips = []
            other_trips = []
            for trip in all_trips:
                origin = trip.get("origin", "") or ""
                destination = trip.get("destination", "") or ""
                if (origin and origin in user_input) or (destination and destination in user_input):
                    relevant_trips.append(trip)
                else:
                    other_trips.append(trip)
            trips_to_show = relevant_trips[:2] + other_trips[:1]
            if trips_to_show:
                summary_parts.append("\n【历史行程】")
                for i, trip in enumerate(trips_to_show[:3], 1):
                    origin = trip.get("origin", "未知")
                    destination = trip.get("destination", "未知")
                    start_date = trip.get("start_date", "")
                    purpose = trip.get("purpose", "")
                    mark = "✦ " if trip in relevant_trips else ""
                    summary_parts.append(f"{i}. {mark}{origin} → {destination} ({start_date}) - {purpose}")

        return "\n".join(summary_parts) if summary_parts else ""

    async def _handle_chitchat(self, user_input: str) -> str:
        """闲聊兜底"""
        from agentscope.message import Msg
        import importlib.util

        agent = None
        try:
            agent = self.orchestrator.agent_registry["chitchat"]
        except (KeyError, Exception):
            pass

        if agent is None:
            try:
                script_path = os.path.join(
                    project_root, ".claude", "skills", "chitchat", "script", "agent.py"
                )
                spec = importlib.util.spec_from_file_location("chitchat_agent", script_path)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    agent = module.ChitchatAgent(name="ChitchatAgent", model=self.model)
            except Exception as e:
                logger.warning(f"Failed to load ChitchatAgent: {e}")

        if agent is None:
            return "嗯嗯，我听着呢～有什么出行相关的问题需要帮忙吗？😊"

        try:
            input_msg = Msg(
                name="user",
                content=json.dumps({"query": user_input}, ensure_ascii=False),
                role="user",
            )
            response = await agent.reply(input_msg)
            data = json.loads(response.content) if isinstance(response.content, str) else response.content
            reply = data.get("response", "") if isinstance(data, dict) else str(data)
            return reply
        except Exception as e:
            logger.warning(f"Chitchat failed: {e}")
            return "嗯嗯，我听着呢～有什么出行相关的问题需要帮忙吗？😊"

    def _format_response(self, result_data: dict) -> str:
        """将智能体结果格式化为文本"""
        results = result_data.get("results", [])
        if not results:
            return "✓ 好的，我已收到。"
        lines = []
        for result in results:
            agent_name = result.get("agent_name", "")
            status = result.get("status", "")
            data = result.get("data", {})
            if status == "error":
                error_msg = data.get("error", "未知错误")
                display = AGENT_DISPLAY_NAMES.get(agent_name, agent_name)
                lines.append(f"❌ {display} 执行失败: {error_msg}")
                continue
            if status != "success":
                continue
            text = self._format_agent_result(agent_name, data)
            if text:
                lines.append(text)
        return "\n".join(lines).strip()

    def _format_agent_result(self, agent_name: str, data: dict) -> str:
        """格式化单个智能体输出"""
        # Itinerary
        if agent_name == "itinerary_planning":
            itinerary = data.get("itinerary")
            if not itinerary and "data" in data and isinstance(data["data"], dict):
                itinerary = data["data"].get("itinerary")
            if itinerary:
                parts = [f"✈️ **{itinerary.get('title', '行程规划')}**"]
                parts.append(f"  时长: {itinerary.get('duration', '未知')}\n")
                for day_plan in itinerary.get("daily_plans", []):
                    day_num = day_plan.get("day", 1)
                    parts.append(f"**第 {day_num} 天**")
                    activities = day_plan.get("activities") or day_plan.get("time_slots") or []
                    for slot in activities:
                        time = slot.get("time", "")
                        activity = slot.get("activity") or slot.get("location") or ""
                        description = slot.get("description", "")
                        transport = slot.get("transport", "")
                        parts.append(f"  {time} - {activity}")
                        if description:
                            parts.append(f"  _{description}_")
                        if transport:
                            parts.append(f"  🚇 {transport}")
                    meals = day_plan.get("meals", {})
                    if meals:
                        if meals.get("lunch"):
                            parts.append(f"  🍜 {meals['lunch']}")
                        if meals.get("dinner"):
                            parts.append(f"  🍽️ {meals['dinner']}")
                    parts.append("")
                notes = itinerary.get("notes", [])
                if notes:
                    parts.append("📌 **注意事项**")
                    for note in notes:
                        parts.append(f"  • {note}")
                return "\n".join(parts)

        # Preference
        if agent_name == "preference":
            raw_prefs = data.get("preferences")
            if not raw_prefs and "data" in data and isinstance(data["data"], dict):
                raw_prefs = data["data"].get("preferences")
            if isinstance(raw_prefs, dict):
                prefs_list = raw_prefs.get("preferences", [])
            else:
                prefs_list = raw_prefs if isinstance(raw_prefs, list) else []
            if prefs_list:
                parts = ["✓ **已更新您的偏好设置**"]
                type_names = {
                    "home_location": "常驻地",
                    "transportation_preference": "交通偏好",
                    "hotel_brands": "酒店偏好",
                    "airlines": "航空公司偏好",
                    "seat_preference": "座位偏好",
                    "meal_preference": "餐食偏好",
                    "budget_level": "预算等级",
                }
                for pref in prefs_list:
                    pref_type = pref.get("type", "")
                    pref_value = pref.get("value", "")
                    action = pref.get("action", "replace")
                    display_type = type_names.get(pref_type, pref_type)
                    action_text = "追加" if action == "append" else "设置为"
                    parts.append(f"  • {display_type} {action_text} `{pref_value}`")
                return "\n".join(parts)

        # Event collection
        if agent_name == "event_collection":
            origin = data.get("origin") or data.get("data", {}).get("origin")
            destination = data.get("destination") or data.get("data", {}).get("destination")
            start_date = data.get("start_date") or data.get("data", {}).get("start_date")
            end_date = data.get("end_date") or data.get("data", {}).get("end_date")
            missing_info = data.get("missing_info") or data.get("data", {}).get("missing_info") or []
            parts = []
            if destination or origin:
                parts.append("✓ **已收集行程信息**")
                if origin:
                    parts.append(f"  • 出发地: `{origin}`")
                if destination:
                    parts.append(f"  • 目的地: `{destination}`")
                if start_date:
                    parts.append(f"  • 出发日期: `{start_date}`")
                if end_date:
                    parts.append(f"  • 返程日期: `{end_date}`")
            if missing_info:
                parts.append(f"💡 还需要补充: {', '.join(missing_info)}")
            return "\n".join(parts) if parts else ""

        # Information query
        if agent_name == "information_query":
            query_results = data.get("results")
            if not query_results and "data" in data and isinstance(data["data"], dict):
                query_results = data["data"].get("results")
            if not query_results:
                query_results = data
            if not isinstance(query_results, dict):
                query_results = {}
            summary = query_results.get("summary", "")
            message = query_results.get("message", "")
            error = query_results.get("error", "")
            parts = []
            if summary:
                parts.append(summary)
            elif message:
                parts.append(message)
            elif error:
                parts.append(error)
            return "\n".join(parts) if parts else ""

        # RAG knowledge
        if agent_name == "rag_knowledge":
            answer = data.get("answer")
            if not answer and "data" in data and isinstance(data["data"], dict):
                answer = data["data"].get("answer")
            if not answer:
                answer = data.get("content") or data.get("data", {}).get("content")
            if isinstance(answer, dict):
                answer = answer.get("answer", str(answer))
            if isinstance(answer, str) and answer.strip().startswith("{") and answer.strip().endswith("}"):
                try:
                    json_obj = json.loads(answer)
                    if isinstance(json_obj, dict) and "answer" in json_obj:
                        answer = json_obj["answer"]
                except Exception:
                    pass
            if answer:
                return str(answer)

        # Memory query
        if agent_name == "memory_query":
            query_result = data.get("answer") or data.get("result") or data.get("content")
            if not query_result and "data" in data and isinstance(data["data"], dict):
                inner = data["data"]
                query_result = inner.get("answer") or inner.get("result") or inner.get("content")
            if query_result:
                return str(query_result)

        # Chitchat
        if agent_name == "chitchat":
            response = data.get("response") or data.get("data", {}).get("response")
            if isinstance(response, dict):
                response = response.get("response", str(response))
            if response:
                return str(response)

        # Fallback
        if data:
            common_keys = ["answer", "content", "result", "message", "summary", "text", "description"]
            for k in common_keys:
                if k in data and isinstance(data[k], str) and data[k].strip():
                    return data[k]
                if "data" in data and isinstance(data["data"], dict):
                    if k in data["data"] and isinstance(data["data"][k], str) and data["data"][k].strip():
                        return data["data"][k]

        display = AGENT_DISPLAY_NAMES.get(agent_name, agent_name)
        return f"✓ {display}已完成"


class WebHommeyManager:
    """管理所有用户的 Hommey 实例"""

    def __init__(self):
        self._instances: dict[str, HommeyWebInstance] = {}

    def get_or_create(self, user_id: str) -> HommeyWebInstance:
        if user_id not in self._instances:
            self._instances[user_id] = HommeyWebInstance(user_id)
        return self._instances[user_id]

    def get(self, user_id: str) -> Optional[HommeyWebInstance]:
        return self._instances.get(user_id)

    async def initialize_user(self, user_id: str) -> HommeyWebInstance:
        instance = self.get_or_create(user_id)
        if not instance.initialized:
            await instance.initialize()
        return instance

    def get_status(self, user_id: str) -> dict:
        instance = self.get(user_id)
        if not instance:
            return {"initialized": False}
        return {
            "initialized": instance.initialized,
            "error": instance.init_error,
        }
