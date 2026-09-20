"""SPDX expression parsing and license-family classification."""

from __future__ import annotations

from typing import Any

from .license_closure_expr_family import _token_family
from .license_closure_expr_tokens import _expression_tokens
from .license_closure_ids_const import CLOSED_FAMILIES


def classify_license_family(
    identifier: str | None, *, has_custom_evidence: bool = False
) -> str:
    """Classify a declared identifier without guessing a replacement license."""
    tokens = _expression_tokens(identifier) if identifier is not None else None
    if tokens is None:
        return "unknown" if identifier is not None else "missing"
    if not tokens:
        return "missing"
    return _token_family(tokens, has_custom_evidence)


def _closed_release_family(
    identifier: Any,
    declared_family: Any,
    *,
    has_custom_evidence: bool = False,
) -> bool:
    family = classify_license_family(
        identifier, has_custom_evidence=has_custom_evidence
    )
    return family in CLOSED_FAMILIES and family == declared_family
