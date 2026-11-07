"""Research directions: what the user cares about. Each direction is a name + keyword list
(+ optional exclusions, arXiv categories, paper languages and its own time window). Query syntax for each
source is generated from this automatically - users never write search syntax."""
from __future__ import annotations

import re
from typing import Any

from . import db
from .i18n import t

# arXiv categories the UI offers (names are translated: catalog key "cat.<id>"). Extend freely.
ARXIV_CATEGORY_IDS: list[str] = [
    # Computer science
    "cs.AI", "cs.CL", "cs.CV", "cs.LG", "stat.ML", "cs.IR", "cs.MM", "cs.NI", "cs.DC", "cs.RO", "cs.CR", "cs.HC",
    "cs.SE", "cs.DB", "cs.GR", "cs.NE", "cs.MA", "cs.SI", "cs.OS", "cs.AR", "cs.PF", "cs.IT", "cs.SD", "cs.DS",
    "cs.LO", "cs.PL", "cs.GT", "cs.CY", "cs.CE", "cs.DL",
    # Electrical engineering and systems
    "eess.AS", "eess.IV", "eess.SP", "eess.SY",
    # Mathematics and statistics
    "math.OC", "math.AG", "math.NT", "math.RT", "math.DG", "math.GT", "math.CO", "math.PR", "math.AP", "math.NA",
    "math.ST", "stat.ME", "stat.AP", "stat.CO",
    # Physics
    "cond-mat.str-el", "cond-mat.supr-con", "cond-mat.mtrl-sci", "cond-mat.mes-hall", "cond-mat.soft", "quant-ph",
    "hep-th", "hep-ph", "hep-ex", "nucl-th", "gr-qc", "astro-ph.GA", "astro-ph.CO", "astro-ph.HE", "astro-ph.EP",
    "astro-ph.SR", "physics.optics", "physics.flu-dyn", "physics.ao-ph", "physics.geo-ph", "physics.bio-ph",
    "physics.chem-ph", "physics.soc-ph", "physics.comp-ph",
    # Quantitative biology, finance, economics
    "q-bio.GN", "q-bio.MN", "q-bio.BM", "q-bio.NC", "q-bio.PE", "q-bio.QM",
    "q-fin.GN", "q-fin.ST", "q-fin.PR", "q-fin.CP", "econ.GN", "econ.EM", "econ.TH",
]


def arxiv_categories() -> list[dict[str, str]]:
    return [{"id": c, "name": t(f"cat.{c}")} for c in ARXIV_CATEGORY_IDS]


# Paper languages a direction can ask for (ISO 639-1). "Any language" is the default (empty list).
PAPER_LANGUAGES = ["en", "zh", "ja", "ko", "de", "fr", "es", "ru", "pt", "it"]

# OpenAlex fields of study (catalog key "field.<id>"). A direction may name its fields: papers that OpenAlex
# files under another field are ranked lower (keywords such as "transformer" or "Ming-Qing" also appear in
# electrical engineering or architecture papers).
FIELDS = ["17", "26", "31", "16", "25", "15", "22", "21", "19", "23", "13", "11", "24", "28", "27", "30", "29", "35",
          "36", "34", "20", "14", "18", "32", "33", "12"]

# Preset groups shown in onboarding (catalog key "preset.group.<id>").
PRESET_GROUPS = ["cs", "science", "life", "engineering", "social", "humanities"]

# Humanities publish slowly (a journal issue every few months), so their presets look back half a year.
_SLOW = 180

PRESETS: list[dict[str, Any]] = [
    # ---- computer science & AI ----
    {"key": "cv", "group": "cs", "name_en": "Computer Vision", "categories": ["cs.CV"],
     "keywords": ["object detection", "semantic segmentation", "image generation", "vision transformer",
                  "visual representation learning", "3D reconstruction", "video understanding", "image recognition"]},
    {"key": "multimodal", "group": "cs", "name_en": "Multimodal Learning",
     "categories": ["cs.CV", "cs.CL", "cs.LG", "cs.MM", "cs.AI"],
     "keywords": ["multimodal", "vision-language", "multimodal large language model", "cross-modal",
                  "image-text", "visual question answering", "VLM", "MLLM"]},
    {"key": "nlp", "group": "cs", "name_en": "Natural Language Processing", "categories": ["cs.CL"],
     "keywords": ["language model", "machine translation", "question answering", "text generation",
                  "instruction tuning", "natural language processing"]},
    {"key": "ml", "group": "cs", "name_en": "Machine Learning", "categories": ["cs.LG", "stat.ML"],
     "keywords": ["deep learning", "representation learning", "self-supervised learning", "reinforcement learning",
                  "diffusion model", "generalization", "optimization", "transformer"]},
    {"key": "ai", "group": "cs", "name_en": "Artificial Intelligence", "categories": ["cs.AI", "cs.CL", "cs.LG"],
     "keywords": ["large language model", "reasoning", "LLM agent", "planning", "knowledge graph", "LLM"]},
    {"key": "ir", "group": "cs", "name_en": "Information Retrieval", "categories": ["cs.IR", "cs.CL"],
     "keywords": ["information retrieval", "dense retrieval", "retrieval-augmented generation", "recommender system",
                  "learning to rank", "reranking", "search engine", "RAG"]},
    {"key": "robotics", "group": "cs", "name_en": "Robotics & Embodied AI", "categories": ["cs.RO", "cs.CV", "cs.LG"],
     "keywords": ["robot manipulation", "embodied", "vision-language-action", "navigation", "sim-to-real",
                  "robot learning"]},
    {"key": "security", "group": "cs", "name_en": "AI Security & Privacy", "categories": ["cs.CR", "cs.LG", "cs.AI"],
     "keywords": ["adversarial attack", "privacy", "backdoor", "jailbreak", "federated learning",
                  "differential privacy", "AI safety"]},
    {"key": "networks", "group": "cs", "name_en": "Computer Networks", "categories": ["cs.NI", "cs.DC"],
     "keywords": ["congestion control", "routing", "software-defined networking", "edge computing",
                  "wireless network", "network measurement", "datacenter network", "5G"]},
    {"key": "systems", "group": "cs", "name_en": "Computer Systems", "categories": ["cs.DC", "cs.OS", "cs.AR", "cs.PF"],
     "keywords": ["distributed systems", "operating system", "GPU", "LLM serving", "storage system",
                  "compiler", "hardware accelerator"]},
    # ---- natural sciences ----
    {"key": "condmat", "group": "science", "name_en": "Condensed Matter Physics",
     "categories": ["cond-mat.str-el", "cond-mat.supr-con", "cond-mat.mtrl-sci", "cond-mat.mes-hall"],
     "keywords": ["superconductivity", "topological insulator", "quantum materials", "strongly correlated",
                  "magnetism", "moiré", "two-dimensional materials"]},
    {"key": "quantum", "group": "science", "name_en": "Quantum Information", "categories": ["quant-ph"],
     "keywords": ["quantum computing", "quantum error correction", "quantum algorithm", "qubit",
                  "quantum entanglement", "quantum communication"]},
    {"key": "astro", "group": "science", "name_en": "Astrophysics & Cosmology",
     "categories": ["astro-ph.GA", "astro-ph.CO", "astro-ph.HE", "astro-ph.EP", "gr-qc"],
     "keywords": ["exoplanet", "galaxy formation", "dark matter", "gravitational waves", "cosmology", "black hole"]},
    {"key": "math", "group": "science", "name_en": "Pure Mathematics",
     "categories": ["math.AG", "math.NT", "math.RT", "math.DG", "math.GT", "math.CO"],
     "keywords": ["algebraic geometry", "number theory", "representation theory", "differential geometry",
                  "topology", "combinatorics"]},
    {"key": "stats", "group": "science", "name_en": "Statistics", "categories": ["stat.ME", "math.ST", "stat.AP", "stat.ML"],
     "keywords": ["causal inference", "Bayesian inference", "high-dimensional statistics", "nonparametric",
                  "survival analysis", "statistical learning"]},
    {"key": "chemistry", "group": "science", "name_en": "Chemistry & Catalysis", "categories": ["physics.chem-ph"],
     "keywords": ["catalysis", "electrocatalysis", "photocatalysis", "organic synthesis", "metal-organic framework",
                  "CO2 reduction"]},
    {"key": "materials", "group": "science", "name_en": "Materials Science", "categories": ["cond-mat.mtrl-sci"],
     "keywords": ["materials science", "perovskite", "lithium battery", "solid-state electrolyte", "nanomaterials",
                  "thin film"]},
    {"key": "earth", "group": "science", "name_en": "Earth & Climate Science",
     "categories": ["physics.ao-ph", "physics.geo-ph"],
     "keywords": ["climate change", "atmospheric", "hydrology", "remote sensing", "carbon cycle", "extreme weather"]},
    # ---- life sciences & medicine ----
    {"key": "molbio", "group": "life", "name_en": "Molecular & Cell Biology", "categories": ["q-bio.GN", "q-bio.MN", "q-bio.BM"],
     "keywords": ["gene regulation", "CRISPR", "single-cell RNA sequencing", "protein structure", "cell signaling",
                  "epigenetics"]},
    {"key": "neuro", "group": "life", "name_en": "Neuroscience", "categories": ["q-bio.NC"],
     "keywords": ["neural circuits", "cognitive neuroscience", "fMRI", "synaptic plasticity",
                  "brain-computer interface", "neurodegeneration"]},
    {"key": "oncology", "group": "life", "name_en": "Oncology",
     "keywords": ["cancer", "tumor microenvironment", "immunotherapy", "chemotherapy", "tumor", "oncology"]},
    {"key": "public_health", "group": "life", "name_en": "Public Health & Epidemiology",
     "keywords": ["epidemiology", "public health", "infectious disease", "vaccination", "health disparities",
                  "global health"]},
    {"key": "medical_ai", "group": "life", "name_en": "Medical AI", "categories": ["eess.IV", "cs.CV", "cs.LG"],
     "keywords": ["medical image segmentation", "medical imaging", "clinical prediction", "electronic health records",
                  "computer-aided diagnosis", "digital pathology"]},
    {"key": "ecology", "group": "life", "name_en": "Ecology & Evolution", "categories": ["q-bio.PE"],
     "keywords": ["biodiversity", "ecology", "evolution", "species distribution", "conservation", "ecosystem"]},
    # ---- engineering ----
    {"key": "power", "group": "engineering", "name_en": "Power & Energy Systems", "categories": ["eess.SY"],
     "keywords": ["power system", "smart grid", "renewable energy", "power electronics", "energy storage",
                  "electric vehicle"]},
    {"key": "control", "group": "engineering", "name_en": "Control & Automation", "categories": ["eess.SY", "math.OC"],
     "keywords": ["control theory", "model predictive control", "robust control", "optimal control",
                  "system identification", "multi-agent system"]},
    {"key": "signal", "group": "engineering", "name_en": "Communications & Signal Processing",
     "categories": ["eess.SP", "cs.IT"],
     "keywords": ["wireless communication", "signal processing", "MIMO", "6G", "channel estimation", "radar"]},
    {"key": "civil", "group": "engineering", "name_en": "Civil Engineering & Architecture",
     "keywords": ["structural engineering", "concrete", "seismic", "building energy", "urban planning",
                  "geotechnical"]},
    {"key": "mechanical", "group": "engineering", "name_en": "Mechanical & Aerospace Engineering",
     "categories": ["physics.flu-dyn"],
     "keywords": ["fluid dynamics", "turbulence", "heat transfer", "additive manufacturing", "fatigue",
                  "aerospace"]},
    # ---- social sciences ----
    {"key": "economics", "group": "social", "name_en": "Economics", "categories": ["econ.GN", "econ.EM"],
     "keywords": ["monetary policy", "labor market", "economic growth", "inflation", "international trade",
                  "development economics"], "window_days": 30},
    {"key": "finance", "group": "social", "name_en": "Finance", "categories": ["q-fin.GN", "q-fin.ST", "q-fin.PR"],
     "keywords": ["asset pricing", "corporate finance", "financial markets", "banking", "stock returns",
                  "risk management"], "window_days": 30},
    {"key": "management", "group": "social", "name_en": "Management",
     "keywords": ["corporate governance", "innovation management", "organizational behavior",
                  "supply chain management", "entrepreneurship", "strategic management"], "window_days": 30},
    {"key": "psychology", "group": "social", "name_en": "Psychology",
     "keywords": ["cognitive psychology", "social psychology", "working memory", "emotion regulation",
                  "mental health", "developmental psychology"], "window_days": 30},
    {"key": "sociology", "group": "social", "name_en": "Sociology",
     "keywords": ["social inequality", "social mobility", "migration", "gender", "family", "social networks"],
     "window_days": 60},
    {"key": "polisci", "group": "social", "name_en": "Political Science & IR",
     "keywords": ["democracy", "public policy", "international relations", "political participation",
                  "authoritarianism", "foreign policy"], "window_days": 60},
    {"key": "education", "group": "social", "name_en": "Education",
     "keywords": ["higher education", "teacher education", "educational technology", "student achievement",
                  "curriculum", "online learning"], "window_days": 60},
    {"key": "law", "group": "social", "name_en": "Law",
     "keywords": ["constitutional law", "international law", "data protection", "criminal justice",
                  "contract law", "human rights"], "window_days": 90},
    {"key": "linguistics", "group": "social", "name_en": "Linguistics",
     "keywords": ["syntax", "phonology", "second language acquisition", "sociolinguistics", "corpus linguistics",
                  "language acquisition"], "window_days": 90},
    # ---- humanities ----
    {"key": "history_china", "group": "humanities", "name_en": "Chinese History",
     "keywords": ["Chinese history", "imperial China", "Ming dynasty", "Qing dynasty", "Song dynasty",
                  "Tang dynasty", "中国古代史", "宋代", "明代", "清代"], "window_days": _SLOW},
    {"key": "history_japan", "group": "humanities", "name_en": "Japanese History",
     "keywords": ["Japanese history", "Edo period", "Tokugawa", "Meiji Japan", "江戸時代", "明治", "日本史"],
     "window_days": _SLOW},
    {"key": "history_korea", "group": "humanities", "name_en": "Korean History",
     "keywords": ["Korean history", "Joseon dynasty", "Goryeo", "조선시대", "고려", "한국사"], "window_days": _SLOW},
    {"key": "history_world", "group": "humanities", "name_en": "World History",
     "keywords": ["global history", "early modern Europe", "medieval Europe", "colonialism", "Ottoman Empire",
                  "world history"], "window_days": _SLOW},
    {"key": "lit_chinese", "group": "humanities", "name_en": "Classical Chinese Literature",
     "keywords": ["classical Chinese literature", "Tang poetry", "Song ci", "唐诗", "宋词", "古典文学", "诗经"],
     "window_days": _SLOW},
    {"key": "literature", "group": "humanities", "name_en": "Literary Studies",
     "keywords": ["literary theory", "comparative literature", "modernism", "novel", "poetry",
                  "postcolonial literature"], "window_days": _SLOW},
    {"key": "philosophy", "group": "humanities", "name_en": "Philosophy",
     "keywords": ["ethics", "epistemology", "metaphysics", "philosophy of mind", "political philosophy",
                  "Confucianism"], "window_days": _SLOW},
    {"key": "religion", "group": "humanities", "name_en": "Religious Studies",
     "keywords": ["Buddhism", "religious studies", "Christianity", "Daoism", "Islam", "ritual"], "window_days": _SLOW},
    {"key": "art", "group": "humanities", "name_en": "Art History & Musicology",
     "keywords": ["art history", "painting", "visual culture", "museum", "architectural history", "musicology"],
     "window_days": _SLOW},
    {"key": "archaeology", "group": "humanities", "name_en": "Archaeology",
     "keywords": ["archaeology", "excavation", "Neolithic", "Bronze Age", "ancient DNA", "radiocarbon"],
     "window_days": 90},
]


_GROUP_FIELDS = {"cs": ["17"], "humanities": ["12", "33"]}
_PRESET_FIELDS = {
    "medical_ai": ["17", "27"], "condmat": ["31", "25"], "quantum": ["31", "17"], "astro": ["31"], "math": ["26"],
    "stats": ["26", "18"], "chemistry": ["16", "15"], "materials": ["25", "16"], "earth": ["19", "23"],
    "molbio": ["13"], "neuro": ["28"], "oncology": ["27", "13"], "public_health": ["27"], "ecology": ["11", "23"],
    "power": ["22", "21"], "control": ["22", "17"], "signal": ["22", "17"], "civil": ["22"],
    "mechanical": ["22", "31"], "economics": ["20"], "finance": ["20", "14"], "management": ["14"],
    "psychology": ["32"], "sociology": ["33"], "polisci": ["33"], "education": ["33"], "law": ["33"],
    "linguistics": ["12", "33"], "archaeology": ["12", "33"],
}


def preset_fields(p: dict[str, Any]) -> list[str]:
    return _PRESET_FIELDS.get(p["key"]) or _GROUP_FIELDS.get(p["group"], [])


def fields() -> list[dict[str, str]]:
    return [{"id": f, "name": t(f"field.{f}")} for f in FIELDS]


def presets() -> list[dict[str, Any]]:
    """Presets with names in the interface language."""
    return [{"key": p["key"], "group": p["group"], "name": t(f"preset.{p['key']}"), "name_en": p["name_en"],
             "keywords": p["keywords"], "categories": p.get("categories", []), "window_days": p.get("window_days"),
             "languages": p.get("languages", []), "fields": preset_fields(p)} for p in PRESETS]


def preset_groups() -> list[dict[str, str]]:
    return [{"id": g, "name": t(f"preset.group.{g}")} for g in PRESET_GROUPS]


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


def _languages(values: Any) -> list[str]:
    return [v for v in _clean_list(values, 12) if re.fullmatch(r"[a-z]{2}", v)]


def _fields(values: Any) -> list[str]:
    return [v for v in _clean_list(values, 8) if v in FIELDS]


def _window(value: Any) -> int | None:
    if value in (None, "", 0):
        return None
    try:
        return max(1, min(1095, int(value)))
    except (TypeError, ValueError):
        return None


def _row(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": r["id"],
        "name": r["name"],
        "keywords": db.loads(r["keywords"], []),
        "exclude": db.loads(r["exclude"], []),
        "categories": db.loads(r["categories"], []),
        "languages": db.loads(r.get("languages"), []),
        "fields": db.loads(r.get("fields"), []),
        "window_days": r.get("window_days"),
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
        raise ValueError(t("err.direction_name"))
    keywords = _clean_list(data.get("keywords"))
    if not keywords:
        keywords = [name]
    order = (db.query_one("SELECT COALESCE(MAX(sort_order), 0) AS m FROM directions") or {"m": 0})["m"] + 1
    now = db.now_iso()
    new_id = db.execute(
        "INSERT INTO directions(name, keywords, exclude, categories, languages, fields, window_days, weight, "
        "enabled, sort_order, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            name,
            db.dumps(keywords),
            db.dumps(_clean_list(data.get("exclude"))),
            db.dumps(_clean_list(data.get("categories"), 12)),
            db.dumps(_languages(data.get("languages"))),
            db.dumps(_fields(data.get("fields"))),
            _window(data.get("window_days")),
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
            raise ValueError(t("err.direction_name"))
        fields["name"] = name
    for key, limit in (("keywords", 30), ("exclude", 30), ("categories", 12)):
        if key in data:
            fields[key] = db.dumps(_clean_list(data[key], limit))
    if "languages" in data:
        fields["languages"] = db.dumps(_languages(data["languages"]))
    if "fields" in data:
        fields["fields"] = db.dumps(_fields(data["fields"]))
    if "window_days" in data:
        fields["window_days"] = _window(data["window_days"])
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
