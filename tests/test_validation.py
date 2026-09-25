from app.config import MAX_OPTIONAL_FIELD_CHARS, MAX_REQUEST_CHARS
from app.utils.validation import assess_vagueness, normalize_text, validate_project_input


def test_valid_request_passes_without_warnings(order_input):
    result = validate_project_input(order_input)
    assert result.ok
    assert result.errors == []
    assert result.warnings == []
    assert result.input.project_name == "Online Order Tracking"


def test_empty_request_is_rejected(order_input):
    order_input["request"] = "   \n  "
    result = validate_project_input(order_input)
    assert not result.ok
    assert "describe the business request" in result.errors[0]


def test_missing_project_name_is_rejected(order_input):
    order_input["project_name"] = ""
    result = validate_project_input(order_input)
    assert "Project name is required." in result.errors


def test_too_short_request_is_rejected(order_input):
    order_input["request"] = "Build an app"
    result = validate_project_input(order_input)
    assert not result.ok
    assert "too short" in result.errors[0]


def test_extremely_long_request_is_rejected(order_input):
    order_input["request"] = "Customers need order tracking. " * 500
    result = validate_project_input(order_input)
    assert not result.ok
    assert f"{MAX_REQUEST_CHARS:,}" in result.errors[0]


def test_long_optional_field_is_rejected(order_input):
    order_input["constraints"] = "x" * (MAX_OPTIONAL_FIELD_CHARS + 1)
    result = validate_project_input(order_input)
    assert any(e.startswith("Constraints") for e in result.errors)


def test_vague_request_warns_but_is_allowed(order_input):
    order_input["request"] = "We are thinking about doing something new with our website soon"
    result = validate_project_input(order_input)
    assert result.ok
    assert "quite vague" in result.warnings[0]
    assert len(result.warnings) >= 3  # header plus at least two specific gaps


def test_vagueness_detects_each_missing_element():
    assert len(assess_vagueness("Something with the website at some point")) == 3
    assert assess_vagueness(
        "Employees want to request laptops online because the paper form causes delays"
    ) == []


def test_missing_optional_fields_are_fine(order_input):
    for key in ("industry", "stakeholders", "existing_systems", "constraints"):
        order_input.pop(key)
    result = validate_project_input(order_input)
    assert result.ok
    assert result.input.industry == ""


def test_whitespace_is_normalized():
    assert normalize_text("  a \t  b\r\n\r\n\r\n\nc  ") == "a b\n\nc"
    assert normalize_text(None) == ""


def test_prompt_context_marks_missing_fields(order_input):
    order_input["constraints"] = ""
    ctx = validate_project_input(order_input).input.as_prompt_context()
    assert "Known constraints: Not provided" in ctx
    assert "Order Management System" in ctx
