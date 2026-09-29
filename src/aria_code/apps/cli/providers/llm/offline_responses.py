"""Canned responses for when no model backend is reachable.

These three lived in aria_cli's module globals and were borrowed by
stream_ollama through the import-time rebind, so the fallback path — the SDK
and the daemon, which never import aria_cli — died on them precisely when it
needed them most: the Ollama-unavailable branch could not build its own
"Ollama is unavailable" message.

They are pure string/dict builders with no dependencies, and they belong with
the provider whose failure mode they describe. aria_cli re-exports them under
its original private names so nothing that borrows those names changes.
"""

from __future__ import annotations

DEFAULT_OLLAMA_URL = "http://localhost:11434"

GREETINGS = frozenset({
    "hi", "hello", "hey", "你好", "您好", "嗨", "哈喽", "在吗",
    "早上好", "下午好", "晚上好",
})


def is_simple_greeting(message: str) -> bool:
    """True for a bare greeting that can be answered without a model."""
    text = (message or "").strip().lower()
    return text in GREETINGS or (
        len(text) <= 8 and any(g in text for g in GREETINGS)
    )


def offline_greeting_response() -> dict:
    """Answer a greeting when neither cloud nor local backend is reachable."""
    return {
        "success": True,
        "response": (
            "你好，我是 Aria Code。\n\n"
            "当前云端模型不可用，且本地 Ollama 服务没有启动；简单问候可以直接响应。"
            "如果要进行代码修改、市场分析或长文本推理，请先启动本地模型：\n\n"
            "```bash\n"
            "ollama serve\n"
            "```\n\n"
            "然后可用 `ollama list` 检查已安装模型，或运行 `/health` 查看 Aria Code 状态。"
        ),
        "provider": "builtin",
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "thinking_tokens": 0},
    }


def ollama_unavailable_result(ollama_url: str, err: str = "") -> dict:
    """The failure result for an unreachable local Ollama, with recovery steps."""
    host = ollama_url or DEFAULT_OLLAMA_URL
    detail = f"\n\nDetail: {err}" if err else ""
    return {
        "success": False,
        "provider": "ollama",
        "error": (
            "Local Ollama is not reachable.\n\n"
            f"Host: {host}\n"
            "Start it in another terminal:\n\n"
            "  ollama serve\n\n"
            "Then verify:\n\n"
            "  curl http://127.0.0.1:11434/api/tags\n"
            "  ollama list\n\n"
            "If you do not want local fallback, use a working cloud/API provider or disable local mode."
            f"{detail}"
        ),
    }
