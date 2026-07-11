---
name: chitchat
description: Use this skill only for brief greetings, thanks, goodbyes, acknowledgements, and questions about the assistant's business-travel capabilities. Do not use it for open-ended small talk or emotional companionship.
---

# Chitchat (闲聊对话)

处理简短礼貌对话，并自然引导回公司差旅规划、政策和报销能力。

## When to Use

- 用户问候：「你好」「嗨」「在吗」「早上好」
- 用户询问状态：「你在干嘛」「你能做什么」
- 用户表达感谢/告别：「谢谢」「再见」「拜拜」
- 不处理开放式闲聊、情绪陪伴或其他未被捕获的领域外问题

## Agent

- **ChitchatAgent** (`agents/chitchat_agent.py`)
- 入参为 **model 对象**（非 model_config_name）
- **异步**：`reply()` 为 `async`，需 `await`
- **规则优先**：内置模板匹配常见闲聊，快速响应
- **LLM 兜底**：仅生成简短回复并引导回公司差旅能力
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
