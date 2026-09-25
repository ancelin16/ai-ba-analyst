import pytest

from app.models.artifacts import RequirementsResult
from app.utils.errors import AIResponseError
from app.utils.json_parsing import extract_json, parse_model


def test_plain_json():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_json_in_markdown_fence():
    text = 'Here you go:\n```json\n{"a": [1, 2]}\n```\nLet me know!'
    assert extract_json(text) == {"a": [1, 2]}


def test_json_surrounded_by_prose():
    text = 'Sure! {"note": "braces } inside strings { are fine"} Hope that helps.'
    assert extract_json(text) == {"note": "braces } inside strings { are fine"}


@pytest.mark.parametrize("text", ["", "   ", "no json here", '{"a": 1', "{'single': 'quotes'}"])
def test_invalid_or_missing_json_raises(text):
    with pytest.raises(AIResponseError):
        extract_json(text)


def test_parse_model_accepts_dict(order_stages):
    result = parse_model(order_stages["requirements"], RequirementsResult)
    assert [r.id for r in result.functional] == ["FR-001", "FR-002", "FR-003"]


def test_parse_model_accepts_text(order_stages):
    import json
    text = f"```json\n{json.dumps(order_stages['requirements'])}\n```"
    assert len(parse_model(text, RequirementsResult).functional) == 3


def test_parse_model_rejects_wrong_shape_with_readable_message():
    with pytest.raises(AIResponseError) as info:
        parse_model({"functional": [{"id": "REQ-1", "description": "x"}]}, RequirementsResult)
    detail = info.value.detail
    assert "functional.0.id" in detail
    assert "functional.0.priority" in detail


def test_parse_model_rejects_top_level_list():
    with pytest.raises(AIResponseError, match="Expected a JSON object"):
        parse_model("[1, 2, 3]", RequirementsResult)


def test_unknown_fields_are_ignored(order_stages):
    payload = order_stages["requirements"]
    payload["commentary"] = "The model added an extra field"
    payload["functional"][0]["confidence"] = 0.9
    assert parse_model(payload, RequirementsResult).functional[0].id == "FR-001"
