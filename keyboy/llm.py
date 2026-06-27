from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class LLMResult:
    text: str
    model: str
    provider: str
    used_remote_model: bool
    raw: dict[str, Any] | None = None


class LLMProvider:
    """Small OpenAI-compatible chat client with deterministic fallback.

    The project intentionally keeps this dependency-free. Any provider that
    exposes `/chat/completions` with an OpenAI-compatible request body can be
    used by setting environment variables:

    - KEYBOY_LLM_API_KEY
    - KEYBOY_LLM_BASE_URL, default https://api.openai.com/v1
    - KEYBOY_LLM_MODEL
    """

    def __init__(self) -> None:
        self.api_key = (
            os.getenv("KEYBOY_LLM_API_KEY")
            or os.getenv("DASHSCOPE_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or ""
        )
        self.base_url = self._default_base_url().rstrip("/")
        self.model = self._default_model()
        self.timeout = float(os.getenv("KEYBOY_LLM_TIMEOUT", "60"))

    @property
    def enabled(self) -> bool:
        return bool(self.api_key and self.model != "openai-compatible-model")

    def configure(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float | None = None,
        enable_thinking: bool | None = None,
    ) -> None:
        if api_key is not None:
            self.api_key = api_key.strip()
        if base_url is not None and base_url.strip():
            self.base_url = base_url.strip().rstrip("/")
        if model is not None and model.strip():
            self.model = model.strip()
        if timeout is not None:
            self.timeout = max(3.0, float(timeout))
        if enable_thinking is not None:
            os.environ["KEYBOY_LLM_ENABLE_THINKING"] = "1" if enable_thinking else "0"

    def safe_config(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "base_url": self.base_url,
            "model": self.model,
            "timeout": self.timeout,
            "has_api_key": bool(self.api_key),
        }

    @staticmethod
    def _default_base_url() -> str:
        if os.getenv("KEYBOY_LLM_BASE_URL"):
            return os.getenv("KEYBOY_LLM_BASE_URL", "")
        if os.getenv("DASHSCOPE_API_KEY"):
            return "https://dashscope.aliyuncs.com/compatible-mode/v1"
        return "https://api.openai.com/v1"

    @staticmethod
    def _default_model() -> str:
        if os.getenv("KEYBOY_LLM_MODEL"):
            return os.getenv("KEYBOY_LLM_MODEL", "")
        if os.getenv("DASHSCOPE_API_KEY"):
            return "qwen3.7-max"
        return "openai-compatible-model"

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1200,
        on_chunk: Any = None,
    ) -> LLMResult:
        if not self.enabled:
            return LLMResult(
                text="",
                model="deterministic-fallback",
                provider="local",
                used_remote_model=False,
            )

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if os.getenv("KEYBOY_LLM_ENABLE_THINKING"):
            payload["enable_thinking"] = os.getenv("KEYBOY_LLM_ENABLE_THINKING", "").lower() not in {"0", "false", "no"}
        if on_chunk:
            payload["stream"] = True
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                if on_chunk:
                    text_parts = []
                    for line in response:
                        line_str = line.decode("utf-8").strip()
                        if line_str.startswith("data: ") and line_str != "data: [DONE]":
                            try:
                                chunk = json.loads(line_str[6:])
                                delta = chunk.get("choices", [{}])[0].get("delta", {})
                                content = delta.get("content", "")
                                if content:
                                    text_parts.append(content)
                                    on_chunk(content)
                            except json.JSONDecodeError:
                                pass
                    text = "".join(text_parts)
                    return LLMResult(text=text, model=self.model, provider=self.base_url, used_remote_model=True, raw={})
                else:
                    raw = json.loads(response.read().decode("utf-8"))
                    text = raw["choices"][0]["message"]["content"]
                    return LLMResult(text=text, model=self.model, provider=self.base_url, used_remote_model=True, raw=raw)
        except Exception as exc:
            return LLMResult(
                text="大模型调用失败，请检查密钥、模型名、服务地址或网络配置。",
                model=self.model,
                provider=self.base_url,
                used_remote_model=False,
            )

    def chat_json(
        self,
        messages: list[dict[str, str]],
        *,
        fallback: dict[str, Any],
        on_chunk: Any = None,
    ) -> tuple[dict[str, Any], LLMResult]:
        result = self.chat(messages, temperature=0.1, max_tokens=1300, on_chunk=on_chunk)
        if not result.used_remote_model:
            return fallback, result

        text = result.text.strip()
        fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
        if fenced:
            text = fenced.group(1).strip()
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed, result
        except json.JSONDecodeError:
            pass
        return fallback, result
