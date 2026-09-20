def refund_candidate(input):
    if input["message"] == "duplicate charge":
        return {
            "output": {"refunded": True},
            "tools": ["lookup_transactions", "verify_duplicate"],
            "complete": True,
            "steps": 3,
            "cost_nano_usd": 1000000,
        }
    raise ValueError("Unknown scenario")


def custom_evaluator(input, expected, actual):
    return actual["output"].get("refunded") is True
