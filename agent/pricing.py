"""Cost of a call, from the dated and sourced prices in eval/pricing.yaml (never hard-coded)."""

from pathlib import Path
from typing import Any

import yaml

PRICING_PATH = Path("eval/pricing.yaml")


def load_pricing(path: Path = PRICING_PATH) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["models"]


def cost_usd(
    pricing: dict[str, Any], model: str, input_tokens: int, output_tokens: int
) -> float | None:
    """Cost in USD; None when the model has no recorded price."""
    price = pricing.get(model)
    if price is None:
        return None
    total = input_tokens * price["input_per_mtok"] + output_tokens * price["output_per_mtok"]
    return round(total / 1_000_000, 6)
