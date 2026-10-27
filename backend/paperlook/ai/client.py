"""DeepSeek API client (OpenAI-compatible /chat/completions).

- Thinking mode is controlled via `thinking: {type: enabled|disabled}` (DeepSeek V4+ API).
  Translation always runs non-thinking (faster, cheaper); analysis can opt in via settings.
- Every call is recorded in `api_usage` (token counts only - never prompt content or keys).
- HTTP errors are mapped to clear Chinese messages with an error code the UI can act on.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx

from .. import config, db, secrets_store, settings_store
from ..errors import AppError

log = logging.getLogger(__name__)

DEFAULT_MODELS = ["deepseek-flash", "deepseek-v4-pro"]


@dataclass
class ChatResult:
    content: str
    reasoning: str | None
    finish_reason: str | None
    model: str
    usage: dict[str, int]


class AIError(AppError):
    def __init__(self, message: str, code: str, status_code: int = 400, retryable: bool = False):
        super().__init__(message, status_code=status_code, code=code)
        self.retryable = retryable


def is_configured() -> bool:
    return bool(secrets_store.get_secret(secrets_store.DEEPSEEK))


def _error_from_response(resp: httpx.Response) -> AIError:
    detail = ""
    try:
        body = resp.json()
        err = body.get("error") if isinstance(body, dict) else None
        detail = (err.get("message") if isinstance(err, dict) else str(err or "")) or ""
    except ValueError:
        detail = resp.text[:200]
    detail = detail.strip()
    code = resp.status_code
    if code == 401:
        return AIError("API Key 无效或已被删除。请在「设置 → AI 服务」中检查 DeepSeek API Key。", "auth")
    if code == 402:
        return AIError("DeepSeek 账户余额不足。请前往 platform.deepseek.com 充值后重试。", "balance")
    if code == 429:
        return AIError("请求过于频繁，已触发 DeepSeek 限流。请稍后重试，或在设置中降低翻译并发数。", "rate_limit", retryable=True)
    if code in (400, 422):
        low = detail.lower()
        if "model" in low and ("not exist" in low or "not found" in low or "invalid" in low or "support" in low):
            return AIError(f"模型不可用：{detail}。请在「设置 → AI 服务」中选择其他模型。", "model")
        if "context" in low or "too long" in low or "maximum" in low:
            return AIError(f"内容超出模型上下文长度：{detail}", "too_long")
        return AIError(f"请求参数错误（HTTP {code}）：{detail or '无详细信息'}", "bad_request")
    if code == 404:
        return AIError("服务地址不正确（HTTP 404）。请检查「服务地址」，DeepSeek 官方地址为 https://api.deepseek.com。", "endpoint")
    if code == 503:
        return AIError("DeepSeek 服务器繁忙（503），请稍后重试。", "overloaded", retryable=True)
    if code >= 500:
        return AIError(f"DeepSeek 服务暂时异常（HTTP {code}），请稍后重试。", "server", retryable=True)
    return AIError(f"DeepSeek 返回错误（HTTP {code}）：{detail}", "unknown")


class DeepSeekClient:
    def __init__(self, api_key: str, base_url: str, model: str, timeout: float = 600.0):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._http = httpx.Client(
            timeout=httpx.Timeout(timeout, connect=20.0),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
                     "User-Agent": config.USER_AGENT},
        )
        self._thinking_param_supported = True

    def close(self) -> None:
        self._http.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            return self._http.request(method, f"{self.base_url}{path}", **kwargs)
        except httpx.TimeoutException:
            raise AIError("请求 DeepSeek 超时。内容较长时模型需要更多时间，请稍后重试。", "timeout", retryable=True)
        except httpx.HTTPError as e:
            raise AIError(f"无法连接到 DeepSeek 服务（{type(e).__name__}）。请检查网络连接和服务地址。", "network", retryable=True)

    # ---- metadata endpoints (free) ----
    def list_models(self) -> list[str]:
        resp = self._request("GET", "/models")
        if resp.status_code != 200:
            raise _error_from_response(resp)
        data = resp.json().get("data") or []
        return [m.get("id") for m in data if m.get("id")]

    def balance(self) -> dict[str, Any] | None:
        resp = self._request("GET", "/user/balance")
        if resp.status_code == 404:
            return None  # non-DeepSeek compatible endpoints may not offer this
        if resp.status_code != 200:
            raise _error_from_response(resp)
        return resp.json()

    # ---- chat ----
    def chat(self, messages: list[dict[str, str]], *, json_mode: bool = False, thinking: bool = False,
             max_tokens: int | None = None, temperature: float | None = None, kind: str = "",
             paper_id: str | None = None, model: str | None = None, retries: int = 3) -> ChatResult:
        model = model or self.model
        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": False}
        if self._thinking_param_supported:
            payload["thinking"] = {"type": "enabled" if thinking else "disabled"}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if temperature is not None and not thinking:
            payload["temperature"] = temperature

        attempt = 0
        while True:
            attempt += 1
            started = time.monotonic()
            try:
                resp = self._request("POST", "/chat/completions", json=payload)
                if resp.status_code in (400, 422) and "thinking" in payload and "thinking" in resp.text.lower():
                    # Compatible endpoints that do not know the `thinking` field.
                    self._thinking_param_supported = False
                    payload.pop("thinking", None)
                    resp = self._request("POST", "/chat/completions", json=payload)
                if resp.status_code != 200:
                    raise _error_from_response(resp)
                body = resp.json()
            except AIError as e:
                _record_usage(kind, model, paper_id, {}, ok=False)
                if e.retryable and attempt < retries:
                    wait = 3 * attempt if e.code != "rate_limit" else 10 * attempt
                    log.info("DeepSeek %s (attempt %d), retrying in %ss", e.code, attempt, wait)
                    time.sleep(wait)
                    continue
                raise
            except ValueError:
                _record_usage(kind, model, paper_id, {}, ok=False)
                if attempt < retries:
                    time.sleep(2)
                    continue
                raise AIError("DeepSeek 返回了无法解析的响应。", "bad_response", retryable=True)
            break

        choice = (body.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        usage = body.get("usage") or {}
        u = {
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
            "cache_hit_tokens": int(usage.get("prompt_cache_hit_tokens") or 0),
        }
        _record_usage(kind, body.get("model") or model, paper_id, u, ok=True)
        log.info("DeepSeek %s ok: %s in / %s out tokens, %.1fs", kind or "chat", u["prompt_tokens"],
                 u["completion_tokens"], time.monotonic() - started)
        return ChatResult(content=msg.get("content") or "", reasoning=msg.get("reasoning_content"),
                          finish_reason=choice.get("finish_reason"), model=body.get("model") or model, usage=u)

    def chat_json(self, messages: list[dict[str, str]], **kwargs: Any) -> tuple[dict[str, Any], ChatResult]:
        """Chat in JSON mode and parse the result; retries once on malformed / truncated JSON."""
        last_err = None
        for attempt in range(2):
            res = self.chat(messages, json_mode=True, **kwargs)
            if res.finish_reason == "length":
                last_err = AIError("模型输出被截断（超过最大输出长度）。", "truncated", retryable=True)
                kwargs["max_tokens"] = min(int((kwargs.get("max_tokens") or 8000) * 2), 64000)
                continue
            try:
                return parse_json(res.content), res
            except ValueError as e:
                last_err = AIError(f"模型返回的 JSON 格式无效：{e}", "bad_json", retryable=True)
        assert last_err is not None
        raise last_err


def parse_json(text: str) -> dict[str, Any]:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    try:
        val = json.loads(t)
    except json.JSONDecodeError:
        start, end = t.find("{"), t.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("未找到 JSON 对象")
        val = json.loads(t[start:end + 1])
    if not isinstance(val, dict):
        raise ValueError("顶层不是 JSON 对象")
    return val


_usage_lock = threading.Lock()


def _record_usage(kind: str, model: str, paper_id: str | None, usage: dict[str, int], ok: bool) -> None:
    try:
        with _usage_lock:
            db.execute(
                "INSERT INTO api_usage(at, kind, model, paper_id, prompt_tokens, completion_tokens, cache_hit_tokens, ok) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (db.now_iso(), kind, model, paper_id, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0),
                 usage.get("cache_hit_tokens", 0), 1 if ok else 0),
            )
    except Exception:
        log.exception("could not record usage")


def get_client(model: str | None = None) -> DeepSeekClient:
    key = secrets_store.get_secret(secrets_store.DEEPSEEK)
    if not key:
        raise AIError("尚未配置 DeepSeek API Key。请在「设置 → AI 服务」中填写后再使用 AI 功能。", "not_configured")
    s = settings_store.get_settings()["ai"]
    return DeepSeekClient(key, s["base_url"], model or s["model"])


def usage_summary() -> dict[str, Any]:
    def agg(where: str, params: tuple = ()) -> dict[str, int]:
        r = db.query_one(
            f"SELECT COUNT(*) AS calls, COALESCE(SUM(prompt_tokens),0) AS prompt, COALESCE(SUM(completion_tokens),0) AS completion, "
            f"COALESCE(SUM(cache_hit_tokens),0) AS cache_hit FROM api_usage WHERE ok = 1 {where}", params) or {}
        return {k: int(v or 0) for k, v in r.items()}

    by_kind = db.query(
        "SELECT kind, COUNT(*) AS calls, SUM(prompt_tokens) AS prompt, SUM(completion_tokens) AS completion "
        "FROM api_usage WHERE ok = 1 AND datetime(at) >= datetime('now','-30 days') GROUP BY kind ORDER BY prompt DESC")
    return {
        "today": agg("AND date(at, 'localtime') = date('now', 'localtime')"),
        "last_30_days": agg("AND datetime(at) >= datetime('now','-30 days')"),
        "total": agg(""),
        "by_kind_30d": by_kind,
    }
