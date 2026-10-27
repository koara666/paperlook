"""Reading model JSON: repairs for mistakes seen in real Gemini replies, without changing correct JSON."""
import json

import pytest

from paperlook.ai.client import parse_json


def test_wrong_closing_bracket_is_repaired():
    # Real gemini-3.5-flash-lite glossary reply (shortened): the array is closed with ">".
    reply = ('{\n  "terms": [\n    {"en": "backbone", "zh": "主干网络", "keep": false},\n'
             '    {"en": "a > b (c)", "zh": "域偏移]", "keep": false}\n  >\n}')
    assert parse_json(reply) == {"terms": [{"en": "backbone", "zh": "主干网络", "keep": False},
                                           {"en": "a > b (c)", "zh": "域偏移]", "keep": False}]}
    assert parse_json(r'{"a": [1, 2}, "b": {"c": "x\"]"]}') == {"a": [1, 2], "b": {"c": 'x"]'}}
    assert parse_json('```json\n{"items": [1)}\n```') == {"items": [1]}
    for bad in ('{"a": [1, 2 "b"]}', '{"a": }', "no json here"):
        with pytest.raises(ValueError):
            parse_json(bad)


def test_unescaped_latex_is_read_as_latex():
    # Gemini often leaves LaTeX backslashes unescaped inside JSON strings in long analyses.
    raw = (r'{"f": "W_{rot} = \prod_i (I - 2 v_i v_i^\top) \mathbf{W}, \frac{1}{2}, \beta \rho \nabla \neq '
           r'\underline{x} \{a\}", "t": "第一行\n第二行\nThe end\tx α \"q\" a\\b"}')
    assert parse_json(raw) == {
        "f": r"W_{rot} = \prod_i (I - 2 v_i v_i^\top) \mathbf{W}, \frac{1}{2}, \beta \rho \nabla \neq "
             r"\underline{x} \{a\}",
        "t": '第一行\n第二行\nThe end\tx α "q" a\\b',
    }


def test_correct_json_is_unchanged():
    obj = {
        "key_formula": r"\frac{a}{b} + \text{x} \nabla \beta \right) \neq \mathbf{W}",
        "text": "公式 $\\hat{Y}_S(x)$ 与 $\\frac{1}{2}$",
        "lines": "a\nb\n\nc\td\nnot\nThe end",
        "q": 'x"y\\',
        "items": [{"en": "a > b", "zh": "(c]"}],
    }
    for indent in (None, 2):
        for ascii_only in (False, True):
            assert parse_json(json.dumps(obj, ensure_ascii=ascii_only, indent=indent)) == obj
