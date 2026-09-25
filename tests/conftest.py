"""Shared fixtures: a realistic, internally consistent order-tracking analysis.

The data mirrors what the AI pipeline should produce, so tests exercise the
models with realistic business content rather than placeholder strings.
"""

import copy

import pytest

ORDER_TRACKING_INPUT = {
    "project_name": "Online Order Tracking",
    "request": (
        "We want customers to be able to track their orders online because our "
        "customer service team receives too many calls asking about order status."
    ),
    "industry": "E-commerce / Retail",
    "stakeholders": "Customer service team, customers",
    "existing_systems": "Order Management System (OMS)",
    "constraints": "",
}

ORDER_TRACKING_STAGES = {
    "problem": {
        "problem_statement": (
            "Customers cannot see order status themselves, so they call customer "
            "service, creating high call volume for a routine enquiry."
        ),
        "objectives": [
            {"id": "BO-01", "description": "Reduce order-status calls to customer service",
             "success_measure": "", "basis": "Stated"},
            {"id": "BO-02", "description": "Give customers self-service visibility of order status",
             "basis": "Stated"},
        ],
        "target_users": ["Customers", "Customer service agents"],
        "current_state": "Customers phone customer service; agents look up the order in the OMS.",
        "future_state": "Customers check status online; agents handle only exceptions.",
        "ambiguities": ["Whether customers must log in to see an order"],
        "is_too_vague": False,
    },
    "requirements": {
        "functional": [
            {"id": "FR-001", "description": "The system shall allow customers to enter an order number.",
             "priority": "Must Have", "rationale": "Entry point for self-service lookup.",
             "objective_ids": ["BO-02"], "basis": "Inferred"},
            {"id": "FR-002", "description": "The system shall validate the order number.",
             "priority": "Must Have", "rationale": "Prevents errors and data exposure.",
             "objective_ids": ["BO-02"], "basis": "Inferred"},
            {"id": "FR-003", "description": "The system shall display the current order status.",
             "priority": "Must Have", "rationale": "Answers the question customers currently call about.",
             "objective_ids": ["BO-01", "BO-02"], "basis": "Stated"},
        ],
        "non_functional": [
            {"id": "NFR-001", "category": "Data Privacy",
             "description": "Order details shall only be shown to a verified requester.",
             "priority": "Must Have",
             "rationale": "Order data includes personal information such as delivery address.",
             "objective_ids": ["BO-02"], "basis": "Assumed"},
        ],
    },
    "stories": {
        "stories": [
            {"id": "US-001", "role": "customer", "want": "to look up my order by its order number",
             "so_that": "I know when it will arrive without calling customer service",
             "priority": "Must Have", "business_value": "Deflects routine calls",
             "requirement_ids": ["FR-001", "FR-002", "FR-003"]},
        ]
    },
    "criteria": {
        "criteria": [
            {"id": "AC-001", "story_id": "US-001", "title": "Valid order number",
             "scenario_type": "Positive", "given": "a customer has a valid order number",
             "when": "the customer submits the order number",
             "then": "the system displays the current order status"},
            {"id": "AC-002", "story_id": "US-001", "title": "Unknown order number",
             "scenario_type": "Negative", "given": "a customer enters an order number that does not exist",
             "when": "the customer submits it",
             "then": "the system shows a clear 'order not found' message without revealing other orders"},
        ]
    },
    "test_cases": {
        "test_cases": [
            {"id": "TC-001", "requirement_ids": ["FR-001", "FR-003"], "criterion_ids": ["AC-001"],
             "scenario": "Look up a valid order", "scenario_type": "Positive",
             "preconditions": ["Order 10045 exists with status 'Shipped'"],
             "steps": ["Open the tracking page", "Enter 10045", "Select Track"],
             "expected_result": "Status 'Shipped' is displayed", "priority": "High"},
            {"id": "TC-002", "requirement_ids": ["FR-002"], "criterion_ids": ["AC-002"],
             "scenario": "Look up a non-existent order", "scenario_type": "Negative",
             "steps": ["Open the tracking page", "Enter 99999", "Select Track"],
             "expected_result": "'Order not found' message; no order data shown", "priority": "High"},
            {"id": "TC-003", "requirement_ids": ["NFR-001"], "criterion_ids": [],
             "scenario": "Order details hidden from an unverified requester", "scenario_type": "Negative",
             "steps": ["Open the tracking page", "Enter a valid order number with the wrong email", "Select Track"],
             "expected_result": "No order details are displayed", "priority": "High"},
        ]
    },
    "questions": {
        "questions": [
            {"id": "Q-01", "question": "Must customers sign in to track an order?", "category": "Critical",
             "area": "Security", "rationale": "Determines how order data is protected."},
            {"id": "Q-02", "question": "How often does the OMS update order status?", "category": "Important",
             "area": "Data"},
            {"id": "Q-03", "question": "Should the page match current branding?", "category": "Nice to Know",
             "area": "Usability"},
        ]
    },
    "stakeholders": {
        "stakeholders": [
            {"id": "SH-01", "name": "Customers", "type": "External", "interest": "Know when their order arrives",
             "influence": "Low", "impact": "High", "basis": "Stated"},
            {"id": "SH-02", "name": "Customer Service Team", "type": "Internal",
             "interest": "Fewer routine status calls", "influence": "Medium", "impact": "High", "basis": "Stated"},
            {"id": "SH-03", "name": "Data Protection Officer", "type": "Internal",
             "interest": "Order data is shown only to the right person", "influence": "High", "impact": "Low",
             "basis": "Assumed", "potentially_missing": True},
        ]
    },
    "process": {
        "sufficient_detail": True,
        "current_state": [
            {"id": "CS-01", "actor": "Customer", "description": "Calls customer service", "is_manual": True},
            {"id": "CS-02", "actor": "Agent", "description": "Looks up order in OMS", "is_manual": True,
             "is_bottleneck": True},
            {"id": "CS-03", "actor": "Agent", "description": "Reads status to customer", "is_manual": True},
        ],
        "future_state": [
            {"id": "FS-01", "actor": "Customer", "description": "Enters order number online"},
            {"id": "FS-02", "actor": "System", "description": "Retrieves status from OMS"},
            {"id": "FS-03", "actor": "System", "description": "Displays status"},
        ],
        "bottlenecks": ["Agents handle every status request by phone"],
        "automation_opportunities": ["Self-service lookup replaces CS-01 to CS-03"],
    },
    "risks": {
        "risks": [
            {"id": "RK-01", "description": "OMS status lags reality, so customers still call",
             "source": "Data", "likelihood": "Medium", "impact": "High",
             "mitigation": "Confirm OMS update frequency before design"},
        ],
        "assumptions": [
            {"id": "AS-01", "description": "The OMS can be queried in real time",
             "impact_if_wrong": "A data sync or cache would be needed", "validate_with": "IT"},
        ],
        "edge_cases": ["Order split into multiple shipments", "Order cancelled after dispatch"],
    },
    "use_cases": {
        "use_cases": [
            {"id": "UC-01", "name": "Check Order Status", "primary_actor": "Customer",
             "goal": "Find out where an order is",
             "main_flow": ["Customer enters order number", "System validates it", "System shows status"],
             "exceptions": [{"name": "2a. Order not found", "steps": ["System shows not-found message"]}],
             "requirement_ids": ["FR-001", "FR-002", "FR-003"]},
        ]
    },
}

# Stage key on Analysis -> stage name used by the generators and the fake client.
STAGE_NAMES = {
    "questions": "clarifying_questions", "problem": "business_problem", "stakeholders": "stakeholders",
    "process": "process_analysis", "risks": "risk_analysis", "requirements": "requirements",
    "stories": "user_stories", "use_cases": "use_cases", "criteria": "acceptance_criteria",
    "test_cases": "test_cases",
}


@pytest.fixture
def order_input() -> dict:
    return copy.deepcopy(ORDER_TRACKING_INPUT)


@pytest.fixture
def order_stages() -> dict:
    return copy.deepcopy(ORDER_TRACKING_STAGES)


@pytest.fixture
def fake_responses(order_stages) -> dict:
    """Every stage's canned AI response, keyed by generator stage name."""
    return {STAGE_NAMES[key]: payload for key, payload in order_stages.items()}
