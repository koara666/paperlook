"""Research directions: what the user cares about. Each direction is a name + keyword list
(+ optional exclusions and arXiv categories). Query syntax for each source is generated
from this automatically - users never write search syntax."""
from __future__ import annotations

from typing import Any

from . import db

# Friendly names for arXiv categories the UI offers. Extend freely.
ARXIV_CATEGORIES: list[dict[str, str]] = [
    {"id": "cs.AI", "name": "人工智能"},
    {"id": "cs.CL", "name": "自然语言处理"},
    {"id": "cs.CV", "name": "计算机视觉"},
    {"id": "cs.LG", "name": "机器学习"},
    {"id": "stat.ML", "name": "统计机器学习"},
    {"id": "cs.IR", "name": "信息检索"},
    {"id": "cs.MM", "name": "多媒体"},
    {"id": "cs.NI", "name": "计算机网络"},
    {"id": "cs.DC", "name": "分布式与并行计算"},
    {"id": "cs.RO", "name": "机器人"},
    {"id": "cs.CR", "name": "安全与密码学"},
    {"id": "cs.HC", "name": "人机交互"},
    {"id": "cs.SE", "name": "软件工程"},
    {"id": "cs.DB", "name": "数据库"},
    {"id": "cs.GR", "name": "计算机图形学"},
    {"id": "cs.NE", "name": "神经与进化计算"},
    {"id": "cs.MA", "name": "多智能体系统"},
    {"id": "cs.SI", "name": "社会与信息网络"},
    {"id": "cs.OS", "name": "操作系统"},
    {"id": "cs.AR", "name": "硬件体系结构"},
    {"id": "cs.PF", "name": "性能评估"},
    {"id": "cs.IT", "name": "信息论"},
    {"id": "cs.SD", "name": "声音处理"},
    {"id": "eess.AS", "name": "音频与语音"},
    {"id": "eess.IV", "name": "图像与视频处理"},
    {"id": "eess.SP", "name": "信号处理"},
    {"id": "math.OC", "name": "优化与控制"},
    {"id": "q-bio.QM", "name": "定量生物学方法"},
]

PRESETS: list[dict[str, Any]] = [
    {
        "key": "cv",
        "name": "计算机视觉",
        "name_en": "Computer Vision",
        "keywords": ["object detection", "semantic segmentation", "image generation", "vision transformer",
                     "visual representation learning", "3D reconstruction", "video understanding", "image recognition"],
        "categories": ["cs.CV"],
    },
    {
        "key": "multimodal",
        "name": "多模态学习",
        "name_en": "Multimodal Learning",
        "keywords": ["multimodal", "vision-language", "multimodal large language model", "cross-modal",
                     "image-text", "visual question answering", "VLM", "MLLM"],
        "categories": ["cs.CV", "cs.CL", "cs.LG", "cs.MM", "cs.AI"],
    },
    {
        "key": "ir",
        "name": "信息检索",
        "name_en": "Information Retrieval",
        "keywords": ["information retrieval", "dense retrieval", "retrieval-augmented generation", "recommender system",
                     "learning to rank", "reranking", "search engine", "RAG"],
        "categories": ["cs.IR", "cs.CL"],
    },
    {
        "key": "networks",
        "name": "计算机网络",
        "name_en": "Computer Networks",
        "keywords": ["congestion control", "routing", "software-defined networking", "edge computing",
                     "wireless network", "network measurement", "datacenter network", "5G"],
        "categories": ["cs.NI", "cs.DC"],
    },
    {
        "key": "ml",
        "name": "机器学习",
        "name_en": "Machine Learning",
        "keywords": ["deep learning", "representation learning", "self-supervised learning", "reinforcement learning",
                     "diffusion model", "generalization", "optimization", "transformer"],
        "categories": ["cs.LG", "stat.ML"],
    },
    {
        "key": "ai",
        "name": "人工智能",
        "name_en": "Artificial Intelligence",
        "keywords": ["large language model", "reasoning", "LLM agent", "planning", "knowledge graph", "LLM"],
        "categories": ["cs.AI", "cs.CL", "cs.LG"],
    },
    {
        "key": "nlp",
        "name": "自然语言处理",
        "name_en": "Natural Language Processing",
        "keywords": ["language model", "machine translation", "question answering", "text generation",
                     "instruction tuning", "natural language processing"],
        "categories": ["cs.CL"],
    },
    {
        "key": "robotics",
        "name": "机器人与具身智能",
        "name_en": "Robotics & Embodied AI",
        "keywords": ["robot manipulation", "embodied", "vision-language-action", "navigation", "sim-to-real",
                     "robot learning"],
        "categories": ["cs.RO", "cs.CV", "cs.LG"],
    },
    {
        "key": "security",
        "name": "AI 安全与隐私",
        "name_en": "AI Security & Privacy",
        "keywords": ["adversarial attack", "privacy", "backdoor", "jailbreak", "federated learning",
                     "differential privacy", "AI safety"],
        "categories": ["cs.CR", "cs.LG", "cs.AI"],
    },
]


def _clean_list(values: Any, limit: int = 30) -> list[str]:
    if not isinstance(values, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        s = " ".join(str(v).replace(",", " ").split()).strip()
        if s and s.lower() not in seen and len(s) <= 80:
            seen.add(s.lower())
            out.append(s)
    return out[:limit]


def _row(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": r["id"],
        "name": r["name"],
        "keywords": db.loads(r["keywords"], []),
        "exclude": db.loads(r["exclude"], []),
        "categories": db.loads(r["categories"], []),
        "weight": r["weight"],
        "enabled": bool(r["enabled"]),
        "sort_order": r["sort_order"],
    }


def list_directions(enabled_only: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT * FROM directions"
    if enabled_only:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY sort_order, id"
    return [_row(r) for r in db.query(sql)]


def get_direction(direction_id: int) -> dict[str, Any] | None:
    r = db.query_one("SELECT * FROM directions WHERE id = ?", (direction_id,))
    return _row(r) if r else None


def create_direction(data: dict[str, Any]) -> dict[str, Any]:
    name = " ".join(str(data.get("name", "")).split())[:60]
    if not name:
        raise ValueError("研究方向名称不能为空")
    keywords = _clean_list(data.get("keywords"))
    if not keywords:
        keywords = [name] if name.isascii() else []
    order = (db.query_one("SELECT COALESCE(MAX(sort_order), 0) AS m FROM directions") or {"m": 0})["m"] + 1
    now = db.now_iso()
    new_id = db.execute(
        "INSERT INTO directions(name, keywords, exclude, categories, weight, enabled, sort_order, created_at, updated_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (
            name,
            db.dumps(keywords),
            db.dumps(_clean_list(data.get("exclude"))),
            db.dumps(_clean_list(data.get("categories"), 12)),
            int(max(1, min(5, int(data.get("weight", 3) or 3)))),
            1 if data.get("enabled", True) else 0,
            order,
            now,
            now,
        ),
    )
    return get_direction(new_id)  # type: ignore[return-value]


def update_direction(direction_id: int, data: dict[str, Any]) -> dict[str, Any]:
    cur = get_direction(direction_id)
    if not cur:
        raise KeyError(direction_id)
    fields: dict[str, Any] = {}
    if "name" in data:
        name = " ".join(str(data["name"]).split())[:60]
        if not name:
            raise ValueError("研究方向名称不能为空")
        fields["name"] = name
    for key, limit in (("keywords", 30), ("exclude", 30), ("categories", 12)):
        if key in data:
            fields[key] = db.dumps(_clean_list(data[key], limit))
    if "weight" in data:
        fields["weight"] = int(max(1, min(5, int(data["weight"] or 3))))
    if "enabled" in data:
        fields["enabled"] = 1 if data["enabled"] else 0
    if "sort_order" in data:
        fields["sort_order"] = int(data["sort_order"])
    if fields:
        fields["updated_at"] = db.now_iso()
        sets = ", ".join(f"{k} = ?" for k in fields)
        db.execute(f"UPDATE directions SET {sets} WHERE id = ?", (*fields.values(), direction_id))
    return get_direction(direction_id)  # type: ignore[return-value]


def delete_direction(direction_id: int) -> None:
    db.execute("DELETE FROM directions WHERE id = ?", (direction_id,))
