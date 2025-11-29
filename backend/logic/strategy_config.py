# fixed_asset_ai/logic/strategy_config.py
"""
Tax Strategy Configuration Module

Centralizes all depreciation strategy definitions and logic.
Single source of truth for strategy names, descriptions, and behavior.

Strategies control how Section 179 and Bonus Depreciation are applied
to current-year asset additions.

References:
- IRC §179 - Section 179 expensing election
- IRC §168(k) - Bonus depreciation
- TCJA phase-down schedule
"""

from typing import Dict, List, Tuple
from dataclasses import dataclass


# ==============================================================================
# STRATEGY DEFINITIONS
# ==============================================================================

@dataclass(frozen=True)
class Strategy:
    """Immutable strategy configuration."""
    key: str                # Internal identifier
    label: str              # Display name (shown in UI)
    description: str        # Help text for users
    apply_179: bool         # Whether to apply Section 179
    apply_bonus: bool       # Whether to apply Bonus Depreciation


# Strategy instances - single source of truth
AGGRESSIVE = Strategy(
    key="aggressive",
    label="Aggressive (179 + Bonus)",
    description="Maximize Year 1 deductions using Section 179 first, then Bonus.",
    apply_179=True,
    apply_bonus=True,
)

BALANCED = Strategy(
    key="balanced",
    label="Balanced (Bonus Only)",
    description="Apply Bonus Depreciation only. Good for lower taxable income.",
    apply_179=False,
    apply_bonus=True,
)

CONSERVATIVE = Strategy(
    key="conservative",
    label="Conservative (MACRS Only)",
    description="Standard MACRS depreciation spread over recovery period.",
    apply_179=False,
    apply_bonus=False,
)


# ==============================================================================
# STRATEGY LOOKUP
# ==============================================================================

# All strategies in display order
ALL_STRATEGIES: Tuple[Strategy, ...] = (AGGRESSIVE, BALANCED, CONSERVATIVE)

# Lookup by label (for backwards compatibility with existing string-based code)
STRATEGY_BY_LABEL: Dict[str, Strategy] = {s.label: s for s in ALL_STRATEGIES}

# Lookup by key (for programmatic access)
STRATEGY_BY_KEY: Dict[str, Strategy] = {s.key: s for s in ALL_STRATEGIES}


def get_strategy_labels() -> List[str]:
    """Get list of strategy labels for UI dropdown."""
    return [s.label for s in ALL_STRATEGIES]


def get_strategy_help() -> str:
    """Get combined help text for strategy dropdown."""
    return " | ".join(f"{s.label.split(' (')[0]}: {s.description.split('.')[0]}." for s in ALL_STRATEGIES)


def get_strategy(label: str) -> Strategy:
    """
    Get strategy by label.

    Args:
        label: Strategy label (e.g., "Aggressive (179 + Bonus)")

    Returns:
        Strategy dataclass with all configuration

    Raises:
        KeyError: If strategy label not found
    """
    if label not in STRATEGY_BY_LABEL:
        valid = ", ".join(get_strategy_labels())
        raise KeyError(f"Unknown strategy '{label}'. Valid options: {valid}")
    return STRATEGY_BY_LABEL[label]


def should_apply_179(strategy_label: str) -> bool:
    """Check if strategy should apply Section 179."""
    return get_strategy(strategy_label).apply_179


def should_apply_bonus(strategy_label: str) -> bool:
    """Check if strategy should apply Bonus Depreciation."""
    return get_strategy(strategy_label).apply_bonus
