---
name: chitchat
description: Use this skill when the user engages in casual conversation, greetings, small talk, or social dialogue. Triggers when user says "你好", "你在干嘛", "谢谢", "再见", or expresses emotions like "我好累", "好无聊". This skill uses ChitchatAgent to generate friendly, natural responses. Rule-based templates handle 80% of common chats, with LLM fallback for complex casual conversation.
---

# Chitchat (闲聊对话)

处理日常问候、闲聊和社交对话，使用 **ChitchatAgent** 生成轻松友好的回复。

## When to Use

- 用户问候：「你好」「嗨」「在吗」「早上好」
- 用户询问状态：「你在干嘛」「你能做什么」
- 用户表达感谢/告别：「谢谢」「再见」「拜拜」
- 用户表达情绪：「我好累」「好无聊」「今天真倒霉」
- 其他未被其他意图捕获的日常对话

## Agent

- **ChitchatAgent** (`agents/chitchat_agent.py`)
- 入参为 **model 对象**（非 model_config_name）
- **异步**：`reply()` 为 `async`，需 `await`
- **规则优先**：内置模板匹配常见闲聊，快速响应
- **LLM 兜底**：规则未命中时调用 LLM 生成自然回复
- **离线可用**：LLM 不可用时仍可输出友善兜底文案

## 初始化与调用

```python
import asyncio
from agentscope.message import Msg
from agentscope.model import OpenAIChatModel
from config_agentscope import init_agentscope
from config import LLM_CONFIG

async def main():
    init_agentscope()
    model = OpenAIChatModel(
        model_name=LLM_CONFIG["model_name"],
        api_key=LLM_CONFIG["api_key"],
        client_kwargs={"base_url": LLM_CONFIG["base_url"]},
    )
    agent = ChitchatAgent(name="ChitchatAgent", model=model)
    msg = Msg(name="user", content='{ "query": "你在干嘛" }', role="user")
    response = await agent.reply(msg)
    print(response.content)

asyncio.run(main())
```
