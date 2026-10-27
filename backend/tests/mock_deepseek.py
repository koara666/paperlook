"""A local stand-in for the DeepSeek API (OpenAI-compatible) and the Gemini API (native
generateContent) used for end-to-end testing without spending real tokens or quota.

Run:   python backend/tests/mock_deepseek.py [port]      (default 8790)
Then in PaperLook: Settings -> AI 服务 -> 高级设置 -> 服务地址 = http://127.0.0.1:8790
(the same address works for both DeepSeek and Gemini).

Error injection by API key:
  sk-mock-401...  -> 401 on every call        sk-mock-402...  -> 402 on chat
  sk-mock-429...  -> 429 on the first chat call, then OK (tests retry)
  sk-mock-500...  -> 500 on chat              anything else   -> success
Gemini keys (header x-goog-api-key):
  AIza-mock-invalid...  -> 400 API_KEY_INVALID      AIza-mock-region...  -> 400 location not supported
  AIza-mock-daily...    -> 429 per-day quota         AIza-mock-zero...    -> 429 quota limit 0
  AIza-mock-rpm...      -> 429 per-minute (retryDelay 1s) on the first call, then OK
  AIza-mock-strict...   -> rejects systemInstruction and thinkingLevel "minimal" (tests fallbacks)
  anything else         -> success; models: gemini-3.5-flash-lite, gemini-3.8-flash
Responses are deterministic and shaped like the real prompts' JSON schemas.
"""
from __future__ import annotations

import json
import re
import sys
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()
_seen_429: set[str] = set()


def _key(req: Request) -> str:
    return (req.headers.get("authorization") or "").removeprefix("Bearer ").strip()


def _err(status: int, msg: str):
    return JSONResponse({"error": {"message": msg, "type": "mock", "code": status}}, status_code=status)


@app.get("/models")
async def models(req: Request):
    if _key(req).startswith("sk-mock-401"):
        return _err(401, "Authentication Fails, Your api key is invalid")
    return {"object": "list", "data": [{"id": "deepseek-flash", "object": "model"}, {"id": "deepseek-v4-pro", "object": "model"}]}


@app.get("/user/balance")
async def balance(req: Request):
    if _key(req).startswith("sk-mock-401"):
        return _err(401, "Authentication Fails")
    ok = not _key(req).startswith("sk-mock-402")
    return {"is_available": ok, "balance_infos": [{"currency": "CNY", "total_balance": "42.00" if ok else "0.00",
                                                    "granted_balance": "0.00", "topped_up_balance": "42.00"}]}


def _summary():
    return {
        "tldr": "提出一个新的基准与分析方法（模拟输出），用于测试 PaperLook 的总结渲染。",
        "paper_type": "数据集与基准",
        "problem": {"question": "现有方法在该任务上缺乏可靠评测。", "importance": "没有可靠评测就无法比较模型能力。"},
        "method": {"overview": "作者构建了数据集并设计评测协议。", "core_idea": "通过受控变量隔离关键因素，公式如 $x^2+y^2$。",
                   "relation_to_prior": "与已有基准相比覆盖更多模态。"},
        "experiments": {"datasets": ["MockBench", "ImageNet"], "metrics": ["Accuracy", "F1"],
                        "main_results": ["最佳模型准确率 61.2%，比人类低 20 个百分点"], "evidence_assessment": "包含消融实验，较为充分。"},
        "conclusions": ["现有模型仍有明显差距"],
        "highlights": ["新的评测视角", "开放数据"],
        "limitations": [{"point": "数据规模较小", "source": "author"}, {"point": "可能存在标注偏差", "source": "ai"}],
        "reading_advice": {"audience": ["多模态学习"], "priority_sections": [{"section": "3 Method", "reason": "核心设计"}],
                           "quick_path": "先读摘要和第 3 节，再看主要结果表。"},
    }


def _modules():
    return {
        "applicable": True, "reason": "",
        "overview": "系统由编码器、对齐模块和评测器组成（模拟输出）。",
        "modules": [
            {"name": "视觉编码器", "name_en": "Vision Encoder", "category": "特征提取", "role": "提取图像特征", "inputs": "图像",
             "outputs": "特征 $z$", "mechanism": "使用 ViT 将图像切分为 patch 并编码。", "key_formula": "z = f(x)", "novelty": "existing", "section": "3.1"},
            {"name": "对齐模块", "name_en": "Alignment Module", "category": "核心算法", "role": "对齐不同模态", "inputs": "特征",
             "outputs": "对齐分数", "mechanism": "计算互近邻重叠。", "key_formula": "S = \\frac{1}{N}\\sum_i |A_i \\cap B_i|", "novelty": "new", "section": "3.2"},
            {"name": "评测器", "name_en": "Evaluator", "category": "评估方法", "role": "计算指标", "inputs": "对齐分数", "outputs": "相关系数",
             "mechanism": "计算 Pearson 相关。", "key_formula": "", "novelty": "adapted", "section": "4"},
        ],
        "flow": [{"from": "视觉编码器", "to": "对齐模块", "description": "传递特征"}, {"from": "对齐模块", "to": "评测器", "description": "传递分数"}],
        "structure": [], "design_insights": ["无需训练即可评估"],
    }


def _contributions(content: str):
    # pick a real sentence from the paper content so quote verification can succeed
    m = re.search(r"([A-Z][^.\n]{40,220}\b(?:we|We)\s+(?:propose|introduce|present)[^.\n]{10,200}\.)", content)
    real = m.group(1) if m else (re.search(r"([A-Z][a-z][^.\n]{60,200}\.)", content) or [None, "We propose a method."])[1]
    return {
        "problem_solved": "评测缺失的问题（模拟输出）",
        "explicit": [{"claim": "提出新的方法/基准", "quote": real, "section": "1 Introduction"},
                     {"claim": "（故意伪造的引用，用于测试核验）", "quote": "This sentence does not appear anywhere in the paper at all.", "section": "1"}],
        "derived": [{"point": "提供了可复现的评测协议", "basis": "第 3 节"}],
        "improvements": [{"aspect": "覆盖范围", "detail": "更多模态", "evidence": "表 1"}],
        "new_methods": [{"name": "MockBench", "description": "新的基准"}],
        "experimental_support": [{"claim": "模型落后于人类", "evidence": "表 2", "strength": "strong"}],
        "inferred": [{"point": "可推广到其他任务", "rationale": "方法与任务无关"}],
    }


def _route(system: str, user: str) -> str:
    if "Reply with the single word" in user:
        return "OK"
    if "学术论文翻译专家" in system:
        payload = user.split("待翻译内容：\n", 1)[1]
        items = json.loads(payload)["items"]
        out = []
        for it in items:
            # keep placeholders, prefix to make the translation visible
            out.append({"id": it["id"], "text": f"【译】{it['text']}"})
        return json.dumps({"translations": out}, ensure_ascii=False)
    if "提取 15-40 个" in user:
        return json.dumps({"terms": [{"en": "vision-language model", "zh": "视觉-语言模型", "keep": False},
                                     {"en": "Transformer", "zh": "Transformer", "keep": True}]}, ensure_ascii=False)
    if "结构化总结" in user:
        return json.dumps(_summary(), ensure_ascii=False)
    if "关键技术模块" in user:
        return json.dumps(_modules(), ensure_ascii=False)
    if "主要贡献与创新点" in user:
        return json.dumps(_contributions(user), ensure_ascii=False)
    if "abstract_zh" in system:
        return json.dumps({"title_zh": "（模拟）论文中文标题", "abstract_zh": "这是模拟的摘要翻译，公式 $x$ 保留。"}, ensure_ascii=False)
    if "候选论文" in user:
        cands = json.loads(user.split("候选论文：\n", 1)[1])
        res = [{"i": c["i"], "relevance": 9 - (c["i"] % 5), "reason": "与研究方向高度相关（模拟）",
                "title_zh": "（模拟中文标题）" + c["title"][:20], "tldr": "模拟的一句话概述"} for c in cands]
        return json.dumps({"results": res}, ensure_ascii=False)
    if "订阅以下研究方向" in user:
        return json.dumps({"keywords": ["graph neural network", "GNN", "message passing"], "exclude": [], "categories": ["cs.LG"]})
    return json.dumps({"note": "unhandled prompt"})


@app.post("/chat/completions")
async def chat(req: Request):
    key = _key(req)
    if key.startswith("sk-mock-401"):
        return _err(401, "Authentication Fails, Your api key is invalid")
    if key.startswith("sk-mock-402"):
        return _err(402, "Insufficient Balance")
    if key.startswith("sk-mock-500"):
        return _err(500, "Internal Server Error")
    if key.startswith("sk-mock-429") and key not in _seen_429:
        _seen_429.add(key)
        return _err(429, "Rate Limit Reached")
    body = await req.json()
    if body.get("model") not in ("deepseek-flash", "deepseek-v4-pro"):
        return _err(400, f"Model Not Exist: {body.get('model')}")
    msgs = body.get("messages", [])
    system = next((m["content"] for m in msgs if m["role"] == "system"), "")
    user = next((m["content"] for m in reversed(msgs) if m["role"] == "user"), "")
    content = _route(system, user)
    time.sleep(0.25)
    pt = (len(system) + len(user)) // 3
    ct = len(content) // 2
    return {
        "id": "mock", "object": "chat.completion", "created": int(time.time()), "model": body["model"],
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": pt, "completion_tokens": ct, "total_tokens": pt + ct,
                  "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": pt},
    }


# ---------------- Gemini (native API) ----------------

GEMINI_MODELS = ["gemini-3.5-flash-lite", "gemini-3.8-flash"]
gemini_requests: list[dict] = []  # inspected by tests


def _gkey(req: Request) -> str:
    return (req.headers.get("x-goog-api-key") or "").strip()


def _gerr(status: int, gstatus: str, msg: str, details: list | None = None):
    return JSONResponse({"error": {"code": status, "message": msg, "status": gstatus, "details": details or []}},
                        status_code=status)


def _gemini_auth(key: str):
    if key.startswith("AIza-mock-invalid"):
        return _gerr(400, "INVALID_ARGUMENT", "API key not valid. Please pass a valid API key.",
                     [{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "API_KEY_INVALID",
                       "domain": "googleapis.com"}])
    return None


@app.get("/v1beta/models")
async def gemini_models(req: Request):
    err = _gemini_auth(_gkey(req))
    if err:
        return err
    models = [{"name": f"models/{m}", "supportedGenerationMethods": ["generateContent", "countTokens"]} for m in GEMINI_MODELS]
    models += [{"name": "models/gemini-embedding-001", "supportedGenerationMethods": ["embedContent"]},
               {"name": "models/gemini-3.8-flash-tts", "supportedGenerationMethods": ["generateContent"]}]
    return {"models": models}


def _quota(quota_id: str, value: str, retry: str | None = None):
    details = [{"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [
        {"quotaMetric": "generativelanguage.googleapis.com/generate_content_free_tier_requests",
         "quotaId": quota_id, "quotaValue": value}]}]
    if retry:
        details.append({"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": retry})
    return _gerr(429, "RESOURCE_EXHAUSTED", "You exceeded your current quota, please check your plan and billing details.",
                 details)


@app.post("/v1beta/models/{model}:generateContent")
async def gemini_generate(model: str, req: Request):
    key = _gkey(req)
    err = _gemini_auth(key)
    if err:
        return err
    body = await req.json()
    gemini_requests.append({"model": model, "key": key, "body": body})
    if key.startswith("AIza-mock-region"):
        return _gerr(400, "FAILED_PRECONDITION", "User location is not supported for the API use.")
    if key.startswith("AIza-mock-daily"):
        return _quota("GenerateRequestsPerDayPerProjectPerModel-FreeTier", "20")
    if key.startswith("AIza-mock-zero"):
        return _quota("GenerateRequestsPerDayPerProjectPerModel-FreeTier", "0")
    if key.startswith("AIza-mock-rpm") and key not in _seen_429:
        _seen_429.add(key)
        return _quota("GenerateRequestsPerMinutePerProjectPerModel-FreeTier", "5", retry="1s")
    if model not in GEMINI_MODELS:
        return _gerr(404, "NOT_FOUND", f"models/{model} is not found for API version v1beta, or is not supported for generateContent.")
    gen = body.get("generationConfig") or {}
    if key.startswith("AIza-mock-strict"):
        if "systemInstruction" in body:
            return _gerr(400, "INVALID_ARGUMENT", "Developer instruction is not enabled for this model")
        if (gen.get("thinkingConfig") or {}).get("thinkingLevel") == "minimal":
            return _gerr(400, "INVALID_ARGUMENT", "Thinking level MINIMAL is not supported for this model.")
    system = " ".join(p.get("text", "") for p in (body.get("systemInstruction") or {}).get("parts", []))
    user = " ".join(p.get("text", "") for c in body.get("contents", []) if c.get("role") == "user" for p in c.get("parts", []))
    if not system:  # system merged into the user turn (models without system instructions)
        system = user
    content = _route(system, user)
    time.sleep(0.05)
    pt = (len(system) + len(user)) // 3
    ct = len(content) // 2
    return {
        "candidates": [{"content": {"role": "model", "parts": [{"text": content}]}, "finishReason": "STOP", "index": 0}],
        "usageMetadata": {"promptTokenCount": pt, "candidatesTokenCount": ct, "thoughtsTokenCount": 7,
                          "totalTokenCount": pt + ct + 7},
        "modelVersion": model,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(sys.argv[1]) if len(sys.argv) > 1 else 8790, log_level="warning")
