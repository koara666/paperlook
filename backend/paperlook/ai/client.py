"""AI provider clients: DeepSeek (OpenAI-compatible) and Google Gemini (native generateContent API).

Both expose the same interface (`chat`, `chat_json`, `list_models`, `balance`, `close`), so the
translation / analysis code does not care which provider is active (`settings.ai.provider`).

- DeepSeek: thinking mode via `thinking: {type: enabled|disabled}` (DeepSeek V4+ API).
- Gemini: free tier has small per-minute / per-day request quotas, so the client can rate-limit
  itself (`free_tier`), honours the server's `retryDelay` on 429, reports an exhausted daily quota
  clearly (it is not retried), and asks callers for larger translation chunks (fewer requests).
  Gemini is not reachable from mainland China without a proxy: an optional proxy can be configured.
- Every call is recorded in `api_usage` (token counts only - never prompt content or keys).
- HTTP errors are mapped to clear Chinese messages with an error code the UI can act on.
"""
from __future__ import annotations

import json
import logging
import re
import ssl
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import httpx

from .. import config, db, secrets_store, settings_store
from ..errors import AppError

log = logging.getLogger(__name__)

DEFAULT_MODELS = ["deepseek-flash", "deepseek-v4-pro"]
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com"
# Recommended free-tier models (Gemini API docs, 2026-10). The live list comes from GET /v1beta/models.
GEMINI_DEFAULT_MODELS = ["gemini-3.5-flash-lite", "gemini-3.8-flash"]

PROVIDERS: dict[str, dict[str, str]] = {
    "deepseek": {"label": "DeepSeek", "secret": secrets_store.DEEPSEEK},
    "gemini": {"label": "Gemini", "secret": secrets_store.GEMINI},
}


@dataclass
class ChatResult:
    content: str
    reasoning: str | None
    finish_reason: str | None
    model: str
    usage: dict[str, int]


class AIError(AppError):
    def __init__(self, message: str, code: str, status_code: int = 400, retryable: bool = False,
                 retry_after: float | None = None):
        super().__init__(message, status_code=status_code, code=code)
        self.retryable = retryable
        self.retry_after = retry_after


def active_provider() -> str:
    p = settings_store.get_settings()["ai"].get("provider")
    return p if p in PROVIDERS else "deepseek"


def provider_label(provider: str | None = None) -> str:
    return PROVIDERS[provider or active_provider()]["label"]


def is_configured(provider: str | None = None) -> bool:
    return bool(secrets_store.get_secret(PROVIDERS[provider or active_provider()]["secret"]))


def not_configured_error() -> AIError:
    return AIError(f"尚未配置 {provider_label()} API Key。请在「设置 → AI 服务」中填写后再使用 AI 功能。", "not_configured")


# ---------------------------------------------------------------------------------------------
# shared client behaviour: retries + usage accounting
# ---------------------------------------------------------------------------------------------

_ssl_ctx: ssl.SSLContext | None = None


def _ssl_context() -> ssl.SSLContext:
    """One shared context: building it (loading the CA bundle) takes ~1 s on Windows, per client."""
    global _ssl_ctx
    if _ssl_ctx is None:
        import certifi

        _ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    return _ssl_ctx


class BaseClient:
    provider = ""
    label = ""
    # Translation hints for callers: characters / paragraphs per request, max parallel requests.
    chunk_chars = 4500
    chunk_units = 40
    max_concurrency: int | None = None

    def __init__(self, model: str):
        self.model = model
        self._http: httpx.Client
        # Called with the number of seconds the client is about to wait (rate limit), for progress messages.
        self.on_wait: Callable[[float], None] | None = None

    def close(self) -> None:
        self._http.close()

    def list_models(self) -> list[str]:
        raise NotImplementedError

    def balance(self) -> dict[str, Any] | None:
        return None

    def _send(self, messages: list[dict[str, str]], *, json_mode: bool, thinking: bool, max_tokens: int | None,
              temperature: float | None, model: str) -> ChatResult:
        raise NotImplementedError

    def _wait(self, seconds: float) -> None:
        if seconds <= 0:
            return
        if self.on_wait:
            try:
                self.on_wait(seconds)
            except Exception:
                pass
        time.sleep(seconds)

    def chat(self, messages: list[dict[str, str]], *, json_mode: bool = False, thinking: bool = False,
             max_tokens: int | None = None, temperature: float | None = None, kind: str = "",
             paper_id: str | None = None, model: str | None = None, retries: int = 3) -> ChatResult:
        model = model or self.model
        attempt = 0
        while True:
            attempt += 1
            started = time.monotonic()
            try:
                res = self._send(messages, json_mode=json_mode, thinking=thinking, max_tokens=max_tokens,
                                 temperature=temperature, model=model)
            except AIError as e:
                _record_usage(kind, model, paper_id, {}, ok=False)
                # Server-told waits (Gemini per-minute quota) get a few extra attempts: they are expected
                # on the free tier and always clear within a minute.
                limit = retries + 3 if (e.code == "rate_limit" and e.retry_after) else retries
                if e.retryable and attempt < limit:
                    if e.retry_after:
                        wait = min(e.retry_after + 1, 90)
                    else:
                        wait = 3 * attempt if e.code != "rate_limit" else 10 * attempt
                    log.info("%s %s (attempt %d), retrying in %ss", self.label, e.code, attempt, wait)
                    self._wait(wait)
                    continue
                raise
            break
        _record_usage(kind, res.model, paper_id, res.usage, ok=True)
        log.info("%s %s ok: %s in / %s out tokens, %.1fs", self.label, kind or "chat", res.usage["prompt_tokens"],
                 res.usage["completion_tokens"], time.monotonic() - started)
        return res

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


# ---------------------------------------------------------------------------------------------
# DeepSeek
# ---------------------------------------------------------------------------------------------

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


class DeepSeekClient(BaseClient):
    provider = "deepseek"
    label = "DeepSeek"

    def __init__(self, api_key: str, base_url: str, model: str, timeout: float = 600.0):
        super().__init__(model)
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._http = httpx.Client(
            timeout=httpx.Timeout(timeout, connect=20.0), verify=_ssl_context(),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
                     "User-Agent": config.USER_AGENT},
        )
        self._thinking_param_supported = True

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
    def _send(self, messages: list[dict[str, str]], *, json_mode: bool, thinking: bool, max_tokens: int | None,
              temperature: float | None, model: str) -> ChatResult:
        payload: dict[str, Any] = {"model": model, "messages": messages, "stream": False}
        if self._thinking_param_supported:
            payload["thinking"] = {"type": "enabled" if thinking else "disabled"}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        if max_tokens:
            payload["max_tokens"] = max_tokens
        if temperature is not None and not thinking:
            payload["temperature"] = temperature

        resp = self._request("POST", "/chat/completions", json=payload)
        if resp.status_code in (400, 422) and "thinking" in payload and "thinking" in resp.text.lower():
            # Compatible endpoints that do not know the `thinking` field.
            self._thinking_param_supported = False
            payload.pop("thinking", None)
            resp = self._request("POST", "/chat/completions", json=payload)
        if resp.status_code != 200:
            raise _error_from_response(resp)
        try:
            body = resp.json()
        except ValueError:
            raise AIError("DeepSeek 返回了无法解析的响应。", "bad_response", retryable=True)

        choice = (body.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        usage = body.get("usage") or {}
        u = {
            "prompt_tokens": int(usage.get("prompt_tokens") or 0),
            "completion_tokens": int(usage.get("completion_tokens") or 0),
            "cache_hit_tokens": int(usage.get("prompt_cache_hit_tokens") or 0),
        }
        return ChatResult(content=msg.get("content") or "", reasoning=msg.get("reasoning_content"),
                          finish_reason=choice.get("finish_reason"), model=body.get("model") or model, usage=u)


# ---------------------------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------------------------

def _us_pacific_offset(utc: datetime) -> int:
    """UTC offset (hours) of US Pacific time: -7 during DST (2nd Sunday of March 02:00 to
    1st Sunday of November 02:00 local), otherwise -8. No tz database needed (Windows has none)."""
    y = utc.year

    def nth_sunday(month: int, n: int) -> datetime:
        d = datetime(y, month, 1, tzinfo=timezone.utc)
        d += timedelta(days=(6 - d.weekday()) % 7)
        return d + timedelta(weeks=n - 1)

    dst_start = nth_sunday(3, 2) + timedelta(hours=10)   # 02:00 PST = 10:00 UTC
    dst_end = nth_sunday(11, 1) + timedelta(hours=9)     # 02:00 PDT = 09:00 UTC
    return -7 if dst_start <= utc < dst_end else -8


def gemini_quota_day_start(now: datetime | None = None) -> datetime:
    """Gemini daily quotas reset at midnight US Pacific time; returns that moment (UTC) for today."""
    now = now or datetime.now(timezone.utc)
    off = timedelta(hours=_us_pacific_offset(now))
    local = now + off
    return datetime(local.year, local.month, local.day, tzinfo=timezone.utc) - off


def gemini_reset_hour_beijing(now: datetime | None = None) -> int:
    return (8 - _us_pacific_offset(now or datetime.now(timezone.utc))) % 24  # 15 (PDT) or 16 (PST)


def free_tier_rpm(model: str) -> int:
    """Conservative requests-per-minute guess for the free tier (Google publishes per-project values
    only in AI Studio). A too-low guess just makes us slower; a too-high one is caught by 429 + retryDelay."""
    m = model.lower()
    if m.startswith("gemma"):
        return 15
    if "lite" in m:
        return 10
    return 5


class _RateLimiter:
    """Sliding one-minute window shared by all clients of the same model (jobs create their own clients)."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._sent: dict[str, deque[float]] = {}

    def reserve(self, key: str, rpm: int) -> float:
        """Reserve a slot; returns how long the caller must wait before sending."""
        with self._lock:
            now = self._clock()
            q = self._sent.setdefault(key, deque())
            while q and q[0] <= now - 60:
                q.popleft()
            at = now if len(q) < rpm else q[-rpm] + 60
            q.append(at)
            return max(0.0, at - now)


_limiter = _RateLimiter()
# Per-model request features the endpoint rejected (thinking level, JSON mode, system instruction),
# remembered so later requests do not repeat the failed attempt.
_gemini_compat: dict[str, dict[str, Any]] = {}
_compat_lock = threading.Lock()


def _gemini_error(resp: httpx.Response, model: str) -> AIError:
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if isinstance(body, list):  # some endpoints wrap the error in a list
        body = body[0] if body else {}
    err = body.get("error") if isinstance(body, dict) else None
    err = err if isinstance(err, dict) else {}
    msg = str(err.get("message") or resp.text[:300]).strip()
    low = msg.lower()
    details = [d for d in (err.get("details") or []) if isinstance(d, dict)]
    reasons = {str(d.get("reason") or "") for d in details}
    code = resp.status_code

    if "API_KEY_INVALID" in reasons or "api key not valid" in low or "api key expired" in low:
        return AIError("Gemini API Key 无效或已过期。请在 Google AI Studio（aistudio.google.com/apikey）重新复制 Key。", "auth")
    if "location is not supported" in low or "not available in your country" in low:
        return AIError("当前网络所在地区不支持 Gemini API（中国大陆、香港等地区不在支持范围内）。"
                       "请把代理切换到美国、日本、新加坡、台湾等地区的节点后重试。", "region")
    if code == 403:
        return AIError(f"这个 Key 没有权限使用 Gemini API：{msg[:200]}。请确认 Key 是在 Google AI Studio 创建的。", "auth")
    if code == 429:
        violations = [v for d in details for v in (d.get("violations") or []) if isinstance(v, dict)]
        retry_after = None
        for d in details:
            m = re.match(r"^([\d.]+)s$", str(d.get("retryDelay") or ""))
            if m:
                retry_after = float(m.group(1))
        per_day = [v for v in violations if "perday" in str(v.get("quotaId") or "").lower()]
        zero = [v for v in violations if str(v.get("quotaValue") or "") == "0"] or (
            "limit: 0" in low and not violations)
        if zero:
            return AIError(f"模型 {model} 不在你的免费额度内（每日上限为 0）。请在「设置 → AI 服务」改用 "
                           f"{GEMINI_DEFAULT_MODELS[0]} 等免费模型，或在 Google AI Studio 为项目开通付费。", "quota_daily")
        if per_day:
            limit = str(per_day[0].get("quotaValue") or "").strip()
            limit_text = f"每天 {limit} 次请求" if limit else "每日请求数"
            return AIError(f"今天的 Gemini 免费额度已用完（{model}：{limit_text}）。额度在北京时间每天 "
                           f"{gemini_reset_hour_beijing()}:00 重置；已完成的部分都已保存，之后可以继续。也可以在"
                           f"「设置 → AI 服务」改用每日额度更多的模型（如 {GEMINI_DEFAULT_MODELS[0]}），或切换到 DeepSeek。",
                           "quota_daily")
        return AIError("请求过于频繁，触发了 Gemini 每分钟请求上限，正在自动等待后重试。", "rate_limit", retryable=True,
                       retry_after=retry_after or 30.0)
    if code == 404 or (code == 400 and "model" in low and ("not found" in low or "not supported" in low)):
        return AIError(f"模型不可用：{model}。请在「设置 → AI 服务」点击「测试连接」刷新模型列表后重新选择。", "model")
    if code == 400:
        if "token" in low and ("exceed" in low or "too long" in low or "maximum" in low):
            return AIError(f"内容超出模型上下文长度：{msg[:200]}", "too_long")
        return AIError(f"请求参数错误（HTTP 400）：{msg[:300] or '无详细信息'}", "bad_request")
    if code == 503 or "overloaded" in low:
        return AIError("Gemini 服务器繁忙（503），请稍后重试。", "overloaded", retryable=True)
    if code >= 500:
        return AIError(f"Gemini 服务暂时异常（HTTP {code}），请稍后重试。", "server", retryable=True)
    return AIError(f"Gemini 返回错误（HTTP {code}）：{msg[:300]}", "unknown")


_BLOCK_REASONS = {
    "SAFETY": "触发了安全过滤",
    "RECITATION": "输出与已有文本高度重复（RECITATION）",
    "PROHIBITED_CONTENT": "内容被判定为禁止处理",
    "BLOCKLIST": "内容命中屏蔽词",
    "SPII": "内容可能包含个人敏感信息",
    "OTHER": "未说明的原因",
}


class GeminiClient(BaseClient):
    provider = "gemini"
    label = "Gemini"

    def __init__(self, api_key: str, model: str, *, base_url: str = GEMINI_BASE_URL, proxy: str | None = None,
                 free_tier: bool = True, timeout: float = 600.0):
        super().__init__(model)
        self.base_url = base_url.rstrip("/")
        self.free_tier = free_tier
        if free_tier:
            # The free tier counts requests, not tokens: fewer, larger translation requests go much further
            # (a 13k-word paper: 9 requests instead of 29).
            self.chunk_chars = 16000
            self.chunk_units = 80
            self.max_concurrency = 2
        try:
            self._http = httpx.Client(
                timeout=httpx.Timeout(timeout, connect=20.0), proxy=proxy or None, verify=_ssl_context(),
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json", "User-Agent": config.USER_AGENT},
            )
        except (ValueError, ImportError) as e:
            raise AIError(f"代理地址无效：{e}。请填写类似 http://127.0.0.1:7890 的地址。", "proxy")

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            return self._http.request(method, f"{self.base_url}{path}", **kwargs)
        except httpx.TimeoutException:
            raise AIError("请求 Gemini 超时。内容较长时模型需要更多时间，请稍后重试。", "timeout", retryable=True)
        except httpx.ProxyError:
            raise AIError("无法连接到代理。请确认代理软件正在运行，且「代理地址」的端口正确。", "network", retryable=True)
        except httpx.HTTPError as e:
            raise AIError(f"无法连接到 Google Gemini 服务（{type(e).__name__}）。中国大陆无法直接访问 Google："
                          "请开启代理软件的「系统代理」，或在「设置 → AI 服务」填写代理地址（如 http://127.0.0.1:7890）。",
                          "network", retryable=True)

    def list_models(self) -> list[str]:
        out: list[str] = []
        token = ""
        for _ in range(5):
            resp = self._request("GET", "/v1beta/models", params={"pageSize": 1000, **({"pageToken": token} if token else {})})
            if resp.status_code != 200:
                raise _gemini_error(resp, self.model)
            body = resp.json()
            for m in body.get("models") or []:
                name = str(m.get("name") or "").removeprefix("models/")
                if "generateContent" in (m.get("supportedGenerationMethods") or []) and _is_text_model(name):
                    out.append(name)
            token = body.get("nextPageToken") or ""
            if not token:
                break
        return out

    def _send(self, messages: list[dict[str, str]], *, json_mode: bool, thinking: bool, max_tokens: int | None,
              temperature: float | None, model: str) -> ChatResult:
        with _compat_lock:
            compat = _gemini_compat.setdefault(model, {"system": True, "json": True, "levels": {}})
        levels = compat["levels"].get(thinking)
        if levels is None:
            levels = ["high"] if thinking else ["minimal", "low"]
        levels = list(levels) + [None]  # None = let the model use its default

        if self.free_tier:
            self._wait(_limiter.reserve(model, free_tier_rpm(model)))

        while True:
            payload = self._payload(messages, json_mode=json_mode and compat["json"], level=levels[0],
                                    max_tokens=max_tokens, temperature=temperature, system=compat["system"])
            resp = self._request("POST", f"/v1beta/models/{model}:generateContent", json=payload)
            if resp.status_code == 400:
                low = resp.text.lower()
                # Degrade request features the model does not support, remember it, and try again.
                if "thinking" in low and levels[0] is not None:
                    levels.pop(0)
                    compat["levels"][thinking] = [x for x in levels if x is not None]
                    continue
                if compat["json"] and json_mode and ("mime" in low or "json mode" in low):
                    compat["json"] = False
                    continue
                if compat["system"] and ("developer instruction" in low or "system_instruction" in low
                                         or "systeminstruction" in low):
                    compat["system"] = False
                    continue
            if resp.status_code != 200:
                raise _gemini_error(resp, model)
            break

        try:
            body = resp.json()
        except ValueError:
            raise AIError("Gemini 返回了无法解析的响应。", "bad_response", retryable=True)
        block = (body.get("promptFeedback") or {}).get("blockReason")
        if block:
            raise AIError(f"Gemini 拒绝处理这段内容（{_BLOCK_REASONS.get(block, block)}）。可以重试，或换用 DeepSeek。", "blocked")
        cands = body.get("candidates") or []
        if not cands:
            raise AIError("Gemini 没有返回结果，请重试。", "bad_response", retryable=True)
        cand = cands[0]
        reason = cand.get("finishReason") or ""
        parts = (cand.get("content") or {}).get("parts") or []
        text = "".join(p.get("text") or "" for p in parts if isinstance(p, dict) and not p.get("thought"))
        if reason in _BLOCK_REASONS and not text.strip():
            raise AIError(f"Gemini 中止了输出（{_BLOCK_REASONS[reason]}）。可以重试一次，或换用 DeepSeek。", "blocked")
        um = body.get("usageMetadata") or {}
        usage = {
            "prompt_tokens": int(um.get("promptTokenCount") or 0),
            "completion_tokens": int(um.get("candidatesTokenCount") or 0) + int(um.get("thoughtsTokenCount") or 0),
            "cache_hit_tokens": int(um.get("cachedContentTokenCount") or 0),
        }
        return ChatResult(content=text, reasoning=None, finish_reason="length" if reason == "MAX_TOKENS" else "stop",
                          model=str(body.get("modelVersion") or model), usage=usage)

    @staticmethod
    def _payload(messages: list[dict[str, str]], *, json_mode: bool, level: str | None, max_tokens: int | None,
                 temperature: float | None, system: bool) -> dict[str, Any]:
        sys_text = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
        contents = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
                    for m in messages if m["role"] != "system"]
        if sys_text and not system and contents:
            contents[0]["parts"][0]["text"] = f"{sys_text}\n\n{contents[0]['parts'][0]['text']}"
        # Thinking tokens count against maxOutputTokens on Gemini; leave generous room (output is not
        # billed on the free tier and only what is generated counts on the paid tier).
        gen: dict[str, Any] = {"maxOutputTokens": min(max(max_tokens or 0, 16384 if json_mode else 2048), 65536)}
        if temperature is not None:
            gen["temperature"] = temperature
        if json_mode:
            gen["responseMimeType"] = "application/json"
        if level:
            gen["thinkingConfig"] = {"thinkingLevel": level}
        payload: dict[str, Any] = {"contents": contents, "generationConfig": gen}
        if sys_text and system:
            payload["systemInstruction"] = {"parts": [{"text": sys_text}]}
        return payload


_NON_TEXT = ("embedding", "tts", "image", "live", "audio", "transcribe", "robotics", "veo", "imagen", "lyria",
             "aqa", "omni", "computer-use", "nano-banana", "learnlm", "deep-research", "antigravity")


def _is_text_model(name: str) -> bool:
    n = name.lower()
    return (n.startswith("gemini") or n.startswith("gemma")) and not any(x in n for x in _NON_TEXT)


# ---------------------------------------------------------------------------------------------

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


def make_client(provider: str, api_key: str, model: str | None = None, timeout: float = 600.0) -> BaseClient:
    s = settings_store.get_settings()["ai"]
    if provider == "gemini":
        g = s["gemini"]
        return GeminiClient(api_key, model or g["model"], base_url=g["base_url"], proxy=g["proxy"] or None,
                            free_tier=g["free_tier"], timeout=timeout)
    return DeepSeekClient(api_key, s["base_url"], model or s["model"], timeout=timeout)


def get_client(model: str | None = None) -> BaseClient:
    provider = active_provider()
    key = secrets_store.get_secret(PROVIDERS[provider]["secret"])
    if not key:
        raise not_configured_error()
    return make_client(provider, key, model)


def gemini_requests_today() -> dict[str, int]:
    """Successful Gemini requests per model since the last daily quota reset (midnight US Pacific)."""
    since = gemini_quota_day_start().replace(microsecond=0).isoformat()
    rows = db.query("SELECT model, COUNT(*) AS n FROM api_usage WHERE ok = 1 AND (model LIKE 'gemini%' OR model LIKE "
                    "'gemma%') AND datetime(at) >= datetime(?) GROUP BY model ORDER BY n DESC", (since,))
    return {r["model"]: int(r["n"]) for r in rows}


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
