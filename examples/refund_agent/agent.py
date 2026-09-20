"""A small, inspectable refund workflow with a deliberate tool-contract failure."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Protocol

from controlsurface import ControlSurface
from opentelemetry.trace import Status, StatusCode

SCHEMA_V1 = {
    "type": "object",
    "properties": {"amount": {"type": "number"}},
    "required": ["amount"],
    "additionalProperties": False,
}
SCHEMA_V2 = {
    "type": "object",
    "properties": {
        "amount": {
            "type": "object",
            "properties": {
                "value": {"type": "number"},
                "currency": {"type": "string"},
            },
            "required": ["value", "currency"],
        }
    },
    "required": ["amount"],
    "additionalProperties": False,
}

POLICIES = (
    "Duplicate charges should be verified against transaction history before refund.",
    "Never create a new payment to resolve a duplicate charge.",
    "Refunds above USD 200 require human approval.",
)
TRANSACTIONS = {
    "customer-17": [
        {"id": "pay-401", "amount": 49.00, "currency": "USD"},
        {"id": "pay-402", "amount": 49.00, "currency": "USD"},
    ]
}


class DecisionModel(Protocol):
    name: str

    def decide(self, message: str, policy: str) -> tuple[dict[str, Any], int, int]: ...


class FixtureModel:
    """Deterministic test double, never presented as a paid/live LLM call."""

    name = "fixture-decision-model"

    def decide(self, message: str, policy: str) -> tuple[dict[str, Any], int, int]:
        if "charged twice" in message.lower() or "duplicate" in message.lower():
            return (
                {"action": "verify_and_refund", "reason": "possible duplicate charge"},
                0,
                0,
            )
        return {"action": "answer", "reason": "no refund request detected"}, 0, 0


class OpenAIModel:
    """Opt-in live provider; use synthetic examples only unless data transfer is approved."""

    def __init__(self) -> None:
        from openai import OpenAI

        self.name = os.environ["CONTROL_DEMO_MODEL"]
        self.client = OpenAI()

    def decide(self, message: str, policy: str) -> tuple[dict[str, Any], int, int]:
        response = self.client.responses.create(
            model=self.name,
            instructions=(
                "You are a refund triage decision step. Return only JSON with action "
                "'verify_and_refund' or 'answer', and a short reason. Do not execute tools."
            ),
            input=f"Policy: {policy}\nCustomer message: {message}",
            store=False,
        )
        decision = json.loads(response.output_text)
        if decision.get("action") not in {"verify_and_refund", "answer"}:
            raise ValueError("Model returned unsupported action")
        usage = response.usage
        return (
            decision,
            usage.input_tokens if usage else 0,
            usage.output_tokens if usage else 0,
        )


@dataclass
class PaymentTool:
    schema_version: int

    def refund(self, amount: Any) -> dict[str, Any]:
        if self.schema_version == 1:
            if not isinstance(amount, (int, float)):
                raise TypeError("refund.amount must be a number")
            value = float(amount)
        elif self.schema_version == 2:
            if not isinstance(amount, dict) or not isinstance(
                amount.get("value"), (int, float)
            ):
                raise TypeError(
                    "refund.amount must be an object with value and currency"
                )
            if amount.get("currency") != "USD":
                raise ValueError("Unsupported refund currency")
            value = float(amount["value"])
        else:
            raise ValueError("Unknown payment tool schema version")
        if value > 200:
            raise PermissionError("Human approval required")
        return {"refund_id": "refund-verified", "amount": value, "currency": "USD"}


class RefundAgent:
    def __init__(
        self,
        model: DecisionModel,
        tool: PaymentTool,
        client: ControlSurface | None = None,
        agent_version: int = 1,
    ) -> None:
        self.model = model
        self.tool = tool
        self.client = client
        self.agent_version = agent_version

    def _span(self, name: str, kind: str, attributes: dict[str, Any] | None = None):
        from contextlib import nullcontext

        return (
            self.client.span(name, kind, attributes)
            if self.client
            else nullcontext(None)
        )

    def run(self, message: str, customer_id: str = "customer-17") -> dict[str, Any]:
        from contextlib import nullcontext

        context = (
            self.client.run(
                "RefundAgent",
                input=message,
                attributes={
                    "controlsurface.agent.name": "refund-agent",
                    "controlsurface.agent.version": str(self.agent_version),
                },
            )
            if self.client
            else nullcontext(None)
        )
        tools: list[str] = []
        steps = 0
        with context as root:
            try:
                with self._span(
                    "policy_search",
                    "retrieval",
                    {"controlsurface.retrieval.documents": len(POLICIES)},
                ):
                    policy = " ".join(POLICIES)
                steps += 1
                with self._span(
                    "decide_refund",
                    "model",
                    {
                        "gen_ai.operation.name": "chat",
                        "gen_ai.request.model": self.model.name,
                    },
                ) as model_span:
                    decision, input_tokens, output_tokens = self.model.decide(
                        message, policy
                    )
                    if model_span:
                        model_span.set_attribute(
                            "gen_ai.usage.input_tokens", input_tokens
                        )
                        model_span.set_attribute(
                            "gen_ai.usage.output_tokens", output_tokens
                        )
                steps += 1
                if decision["action"] != "verify_and_refund":
                    return {
                        "output": {"refunded": False, "reason": decision["reason"]},
                        "tools": tools,
                        "steps": steps,
                        "complete": True,
                    }
                with self._span(
                    "lookup_transactions",
                    "tool",
                    {
                        "gen_ai.tool.name": "lookup_transactions",
                    },
                ):
                    history = TRANSACTIONS.get(customer_id, [])
                tools.append("lookup_transactions")
                steps += 1
                with self._span(
                    "verify_duplicate",
                    "tool",
                    {
                        "gen_ai.tool.name": "verify_duplicate",
                    },
                ):
                    duplicate = (
                        len(history) >= 2
                        and history[-1]["amount"] == history[-2]["amount"]
                    )
                tools.append("verify_duplicate")
                steps += 1
                if not duplicate:
                    return {
                        "output": {
                            "refunded": False,
                            "reason": "No duplicate transaction",
                        },
                        "tools": tools,
                        "steps": steps,
                        "complete": True,
                    }
                amount = history[-1]["amount"]
                # Agent v1 emits the old scalar contract. Agent v2 knows the new schema.
                argument = (
                    amount
                    if self.agent_version == 1
                    else {
                        "value": amount,
                        "currency": history[-1]["currency"],
                    }
                )
                with self._span(
                    "payments.refund",
                    "tool",
                    {
                        "gen_ai.tool.name": "payments.refund",
                        "controlsurface.tool.version": str(self.tool.schema_version),
                        "controlsurface.tool.schema_version": str(
                            self.tool.schema_version
                        ),
                    },
                ):
                    refund = self.tool.refund(argument)
                tools.append("payments.refund")
                steps += 1
                return {
                    "output": {"refunded": True, "refund_id": refund["refund_id"]},
                    "tools": tools,
                    "steps": steps,
                    "complete": True,
                }
            except (TypeError, ValueError, PermissionError) as error:
                if root:
                    root.record_exception(error)
                    root.set_status(Status(StatusCode.ERROR, str(error)))
                return {
                    "output": {"refunded": False, "error": str(error)},
                    "tools": tools,
                    "steps": steps,
                    "complete": False,
                }


def healthy_candidate(input: dict[str, Any]) -> dict[str, Any]:
    return RefundAgent(FixtureModel(), PaymentTool(1), agent_version=1).run(
        input["message"]
    )


def broken_candidate(input: dict[str, Any]) -> dict[str, Any]:
    return RefundAgent(FixtureModel(), PaymentTool(2), agent_version=1).run(
        input["message"]
    )


def fixed_candidate(input: dict[str, Any]) -> dict[str, Any]:
    return RefundAgent(FixtureModel(), PaymentTool(2), agent_version=2).run(
        input["message"]
    )
