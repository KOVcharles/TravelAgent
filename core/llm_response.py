"""Helpers for extracting text from model responses."""
from __future__ import annotations

from typing import Any


def extract_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            elif hasattr(item, "text"):
                parts.append(str(item.text or ""))
            elif hasattr(item, "content"):
                parts.append(extract_content(item.content))
            else:
                parts.append(str(item))
        return "".join(parts)
    return str(content)


def extract_text_from_dict(response: dict) -> str:
    if "text" in response:
        return extract_content(response.get("text"))
    if "content" in response:
        return extract_content(response.get("content"))
    return ""


def merge_stream_text(current: str, incoming: str) -> str:
    """Merge either delta or cumulative text chunks from a model stream.

    OpenAI-compatible providers are not consistent: some yield only the new
    delta while others yield the complete generated text on every chunk.  A
    plain concatenation corrupts the latter (for example ``{"`` +
    ``{"reasoning"``), which then makes otherwise valid JSON unparsable.
    """
    if not incoming:
        return current
    if not current:
        return incoming
    if incoming.startswith(current):
        return incoming
    if current.endswith(incoming):
        return current
    return current + incoming


async def extract_text_from_response(response: Any) -> str:
    if response is None:
        return ""
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        return extract_text_from_dict(response)

    if hasattr(response, "__aiter__"):
        text = ""
        async for chunk in response:
            if isinstance(chunk, str):
                incoming = chunk
            elif isinstance(chunk, dict):
                incoming = extract_text_from_dict(chunk)
            elif hasattr(chunk, "text"):
                incoming = extract_content(chunk.text)
            elif hasattr(chunk, "content"):
                incoming = extract_content(chunk.content)
            else:
                incoming = str(chunk)
            text = merge_stream_text(text, incoming)
        return text

    if hasattr(response, "text"):
        return extract_content(response.text)
    if hasattr(response, "content"):
        return extract_content(response.content)

    return str(response)
