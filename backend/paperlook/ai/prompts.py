"""All prompts in one place. Outputs are JSON so the UI can render structured, consistent results.

Instructions are written in English and name the output language explicitly (zh/en/ja/ko - the interface
language, or settings.ai.output_language). Papers can be in any language and from any discipline, so the
prompts never assume an English source or a computer-science paper. Enumerated fields (paper type, module
category …) are returned as English codes that the interface translates.
"""
from __future__ import annotations

from .. import settings_store
from ..i18n import LANGS, current

# How each output language is named inside the prompts, and its register.
LANGUAGE = {"zh": "Simplified Chinese (简体中文)", "en": "English", "ja": "Japanese (日本語)", "ko": "Korean (한국어)"}
STYLE = {
    "zh": "Use standard Simplified Chinese academic prose.",
    "en": "Use clear, precise academic English.",
    "ja": "Use formal written Japanese for academic texts (である調).",
    "ko": "Use formal Korean academic prose (-다 style).",
}
NOT_STATED = {"zh": "论文未明确说明", "en": "Not stated in the paper", "ja": "論文中に明記されていない",
              "ko": "논문에 명시되어 있지 않음"}
ABSTRACT_ONLY = {"zh": "摘要未提及，需阅读全文", "en": "Not in the abstract; see the full text",
                 "ja": "要旨に記載なし（本文を参照）", "ko": "초록에 없음(본문 참조)"}
# Source-language names for translation prompts (ISO 639-1 -> English name).
SOURCE_NAMES = {"en": "English", "zh": "Chinese", "ja": "Japanese", "ko": "Korean", "de": "German", "fr": "French",
                "es": "Spanish", "pt": "Portuguese", "it": "Italian", "ru": "Russian", "nl": "Dutch", "id": "Indonesian",
                "vi": "Vietnamese", "th": "Thai", "ar": "Arabic", "tr": "Turkish", "pl": "Polish", "uk": "Ukrainian",
                "el": "Greek", "hi": "Hindi"}
TERM_EXAMPLE = {"zh": "对比学习（contrastive learning）", "ja": "対照学習（contrastive learning）",
                "ko": "대조 학습(contrastive learning)", "en": "the imperial examination (keju 科举)"}


def output_language() -> str:
    """Language of AI output: settings.ai.output_language, or the interface language when 'auto'."""
    lang = settings_store.get_settings()["ai"].get("output_language")
    return lang if lang in LANGS else current()


def source_name(code: str | None) -> str:
    return SOURCE_NAMES.get(code or "", "the original language")


def analysis_system(lang: str) -> str:
    return f"""You are a rigorous research assistant who helps researchers understand academic papers quickly and accurately. Rules:
- Answer only from the provided paper. If the paper does not state something, write "{NOT_STATED[lang]}" - never invent datasets, metrics, numbers, sources, authors' opinions or conclusions.
- Write every text field in {LANGUAGE[lang]}, whatever language the paper is written in. {STYLE[lang]} Keep names of methods, models, datasets, metrics, archives and editions as they appear in the paper.
- The paper may come from any discipline - natural sciences, engineering, medicine, social sciences or humanities. Adapt to its genre: for a humanities or social-science paper, "method" means its approach, sources and argument (archival research, close reading, philology, fieldwork, interviews, econometric identification …) and "experiments" means the evidence it uses.
- When the paper quotes classical or historical language (Classical Chinese, kanbun, Middle Korean, Latin, Old English …), keep the original wording character for character (never convert between simplified, traditional and Japanese character forms) and add a modern {LANGUAGE[lang]} rendering in parentheses wherever you use such a quotation.
- Be specific and information-dense; avoid generic filler. Quote numbers exactly as in the paper.
- In text fields, wrap every mathematical symbol or formula in $...$ and write standard LaTeX (e.g. $\\hat{{Y}}_S(x)$, $\\frac{{1}}{{2}}$). Never drop the backslashes of LaTeX commands and never write LaTeX commands outside $...$ - except in fields that explicitly say not to include $.
- Output exactly one JSON object with the required structure and nothing else."""


def abstract_only_note(lang: str) -> str:
    return (f"[Important] The full text is not available - only the title and abstract. Answer from the abstract only: "
            f"for anything the abstract does not cover (experimental setup, numbers, module details, sources) write "
            f"\"{ABSTRACT_ONLY[lang]}\" and do not guess.")


def summary_task(lang: str) -> str:
    return f"""Write a structured summary of the paper above that lets a reader decide quickly whether it is worth reading closely. All text in {LANGUAGE[lang]}.

Output JSON with this structure:
{{
  "tldr": "one sentence: what the paper does and what it finds (at most ~40 words)",
  "paper_type": "one code: method | system | empirical | dataset | survey | theory | position | humanities | other  (humanities = historical, philological, literary, philosophical or other interpretive scholarship)",
  "problem": {{
    "question": "the specific question or problem the paper addresses",
    "importance": "why it matters (gaps in prior work, practical or scholarly need)"
  }},
  "method": {{
    "overview": "the approach in 3-5 sentences (for humanities: sources, method and line of argument)",
    "core_idea": "the core idea or key insight",
    "relation_to_prior": "how it relates to and differs from prior work"
  }},
  "experiments": {{
    "datasets": ["datasets, experimental settings, corpora or primary sources used"],
    "metrics": ["evaluation metrics or criteria (empty if not applicable)"],
    "main_results": ["main results or findings, with concrete numbers and comparisons where the paper gives them"],
    "evidence_assessment": "whether the evidence supports the conclusions, with reasons (ablations, fair comparisons, scale; for humanities: quality and range of sources, counter-evidence considered)"
  }},
  "conclusions": ["the paper's main conclusions"],
  "highlights": ["2-4 points worth noticing"],
  "limitations": [
    {{"point": "a limitation", "source": "author or ai"}}
  ],
  "reading_advice": {{
    "audience": ["which readers or research areas benefit most"],
    "priority_sections": [{{"section": "section name as in the paper", "reason": "why to read it first"}}],
    "quick_path": "in which order a reader in a hurry should read which parts"
  }}
}}
In limitations, source=author means the authors acknowledge it; source=ai means it is your own assessment. Use empty arrays or "{NOT_STATED[lang]}" for fields that do not apply."""


def modules_task(lang: str) -> str:
    return f"""Identify and analyse the key technical modules of this paper so the reader understands the overall structure and how the parts work together. All text in {LANGUAGE[lang]}.

If the paper has no separable technical modules (e.g. a survey, a purely theoretical derivation, a position paper, a purely empirical study, or humanities scholarship), set applicable to false, explain why, and list the core steps of its argument in order in "structure". Never invent modules just to fill the template.

Output JSON with this structure:
{{
  "applicable": true,
  "reason": "why applicable is false; otherwise an empty string",
  "overview": "overall architecture or workflow in 3-6 sentences",
  "modules": [
    {{
      "name": "module name in {LANGUAGE[lang]}",
      "name_en": "the module's name as written in the paper (empty string if none)",
      "category": "one code: architecture | algorithm | feature_extraction | data_processing | training | inference | loss | math | evaluation | other",
      "role": "what the module is responsible for",
      "inputs": "inputs",
      "outputs": "outputs",
      "mechanism": "how it works, concretely and specifically",
      "key_formula": "the single most important formula in standard LaTeX (keep the backslashes, e.g. \\frac, \\mathbf), without $ signs; empty string if none",
      "novelty": "new (proposed in this paper) / adapted (an improved existing method) / existing (used as is)",
      "section": "the corresponding section of the paper"
    }}
  ],
  "flow": [{{"from": "module name", "to": "module name", "description": "how data or information flows between them"}}],
  "structure": ["only when applicable is false: the core steps of the argument"],
  "design_insights": ["key design choices and their motivation"]
}}
Order modules by data flow or importance; usually 3-8."""


def contributions_task(lang: str) -> str:
    return f"""Extract the main contributions and novel points of this paper. Strictly separate three kinds of statements and never present an inference as the authors' claim. All text in {LANGUAGE[lang]} except the quotes.

1. explicit - contributions the authors state themselves (usually in the abstract or at the end of the introduction, e.g. "our contributions are …"). Each must come with a supporting sentence copied verbatim from the paper in the paper's own language - never translated, rephrased or stitched together - and its section.
2. derived - contributions you derive from the content (method, experiments, analysis, sources) that the authors do not necessarily list. Give the basis.
3. inferred - potential value or impact you infer (possible applications, implications for later research). This is speculation: always give your reasoning.

Output JSON with this structure:
{{
  "problem_solved": "the core problem the paper solves",
  "explicit": [{{"claim": "the contribution", "quote": "the supporting sentence, verbatim in the paper's language", "section": "section"}}],
  "derived": [{{"point": "a derived contribution", "basis": "basis (section, experiment, table, source)"}}],
  "improvements": [{{"aspect": "what improves over prior work", "detail": "details", "evidence": "supporting evidence (numbers and baselines where possible)"}}],
  "new_methods": [{{"name": "name of a method / model / dataset / metric / concept newly proposed in this paper", "description": "short description"}}],
  "experimental_support": [{{"claim": "a conclusion supported by evidence", "evidence": "the evidence", "strength": "strong / moderate / weak"}}],
  "inferred": [{{"point": "potential value", "rationale": "reasoning"}}]
}}"""


def abstract_translation_system(source: str | None, lang: str) -> str:
    return f"""You are an expert academic translator. Translate the paper's title and abstract from {source_name(source)} into accurate, fluent {LANGUAGE[lang]}. {STYLE[lang]}
Keep LaTeX formulas ($...$), citation markers and names of models and datasets unchanged. If the text quotes classical or historical language, keep the quotation character for character (no conversion between simplified, traditional or Japanese character forms) and add a modern {LANGUAGE[lang]} translation in parentheses.
Output only JSON: {{"title": "...", "abstract": "..."}}"""


def translation_system(keep_terms: bool, source: str | None, lang: str) -> str:
    src = source_name(source)
    if keep_terms:
        term_rule = (f"When an important term first appears, write the {LANGUAGE[lang]} term followed by the original term "
                     f"in parentheses, e.g. {TERM_EXAMPLE[lang]}; afterwards use the {LANGUAGE[lang]} term alone.")
    else:
        term_rule = f"Use the {LANGUAGE[lang]} terms directly, without repeating the original terms."
    return f"""You are an expert translator of academic papers. Translate from {src} into accurate, fluent {LANGUAGE[lang]} that follows the academic writing conventions of that language. {STYLE[lang]}

Rules:
1. Faithfulness: translate every sentence completely. Do not add, omit, summarise or explain anything.
2. Formula placeholders: markers such as ⟦M1⟧ and ⟦M2⟧ stand for mathematical formulas. Keep every placeholder unchanged at the semantically corresponding position in the translation; never modify, translate, merge or drop one.
3. Keep citation markers unchanged, e.g. [12], [3, 5], (Smith et al., 2023).
4. Terminology: follow the given glossary strictly and consistently. {term_rule}
5. Proper nouns: model names, dataset names, method abbreviations, code identifiers and URLs stay exactly as in the original (e.g. CLIP, ImageNet, ResNet-50).
6. Quotations of classical or historical texts (Classical Chinese, kanbun, Latin, Old English …): keep the original quotation verbatim, character for character (never convert between simplified, traditional and Japanese character forms), and add a modern {LANGUAGE[lang]} translation in parentheses right after it.
7. Items with kind "title" are section headings: translate them as concise headings without numbering. Items with kind "caption" are figure or table captions.
8. Output format: only the JSON object {{"translations": [{{"id": "<original id>", "text": "<translation>"}}]}}. Every input id must have exactly one translation, in the same order as the input."""


def glossary_system(lang: str) -> str:
    return f"You are a terminology expert who knows the standard {LANGUAGE[lang]} renderings of academic terms in every field. Output JSON only."


def glossary_task(source: str | None, lang: str) -> str:
    return f"""From the title, abstract and section headings of the paper below (written in {source_name(source)}), extract the 15-40 technical terms most important for understanding and translating it (core concepts, method names, task names, key technical vocabulary, important historical or cultural terms) and give their standard {LANGUAGE[lang]} renderings.
- Proper nouns usually kept in the original form (model names, dataset names, abbreviations such as Transformer, CLIP, ViT): set "tgt" to the original and "keep" to true.
- For all other terms "keep" is false.
- "tgt" must be one complete, standard {LANGUAGE[lang]} term or the original term - never a mix of both or a half-transliteration. Terms named after people: use the conventional {LANGUAGE[lang]} form of the name if one exists, otherwise keep the original name.
Output JSON: {{"terms": [{{"src": "term in the paper", "tgt": "{LANGUAGE[lang]} rendering", "keep": false}}]}}"""


def rerank_system(lang: str) -> str:
    return ("You screen research papers for a researcher. Given their research directions, judge how relevant and "
            "worth reading each candidate is. Be objective: a paper whose keywords overlap only by chance while its "
            "topic or discipline differs gets a low score. Output JSON only.")


def rerank_task(lang: str) -> str:
    return f"""For every candidate paper output:
- relevance: integer 0-10. 10 = fits one of the directions very well and is clearly worth reading; 5 = partly relevant; 0 = unrelated.
- reason: in {LANGUAGE[lang]}, at most ~20 words: which direction it fits and what stands out.
- title_tr: the title translated into {LANGUAGE[lang]} (repeat it if it is already in {LANGUAGE[lang]}).
- tldr: one sentence in {LANGUAGE[lang]} (at most ~30 words).
Output JSON: {{"results": [{{"i": 0, "relevance": 8, "reason": "...", "title_tr": "...", "tldr": "..."}}]}} covering every candidate."""


def suggest_system() -> str:
    return ("You help researchers in any discipline set up a paper feed. You know the terms that papers of every field "
            "actually use in titles and abstracts, how fast each field publishes, and the arXiv categories. Output JSON only.")


def suggest_task(name: str, description: str, categories: list[dict[str, str]], fields: list[dict[str, str]],
                 lang: str) -> str:
    cats = ", ".join(c["id"] for c in categories)
    fds = ", ".join(f"{f['id']} ({f['name']})" for f in fields)
    return f"""The user wants new papers on this research direction:
Name: {name}
Notes: {description or 'none'}
The user's interface language is {LANGUAGE[lang]}.

Give:
1. keywords: 8-12 keywords or short phrases that papers in this field really use in titles and abstracts, covering the main sub-topics. Most paper databases index English titles and abstracts, so give mostly English terms; list acronyms (e.g. RAG, VLM) separately. If the field also publishes substantially in Chinese, Japanese or Korean (for example East Asian history, literature, law or regional studies), add 2-5 keywords in those languages as well.
2. exclude: optional words that pull in papers from other fields (empty array if none).
3. categories: 0-4 arXiv category ids from this list that fit (empty if the field does not use arXiv, as in most humanities, social sciences, medicine and chemistry): {cats}
4. fields: 1-3 OpenAlex field ids that the papers belong to, from: {fds}
5. window_days: a sensible time window for "new papers" given how fast the field publishes: 7 for very active fields such as machine learning, 30 for most sciences and engineering, 60-90 for social sciences, 180 for humanities or very small fields.
Output JSON: {{"keywords": ["..."], "exclude": [], "categories": [], "fields": ["17"], "window_days": 30}}"""
