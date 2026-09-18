"""Per-record source-license closure evaluation."""

from __future__ import annotations

from typing import Any

from .license_closure_eval_decls import add_coverage_reasons, add_digest_reasons
from .license_closure_eval_family import add_family_reasons
from .license_closure_eval_identity import add_identity_reasons, load_license_state
from .license_closure_eval_result import duplicate_id_row, finish_eval
from .license_closure_eval_state import EvalAcc


def _evaluate_record(acc: EvalAcc) -> dict[str, Any]:
    add_identity_reasons(acc)
    load_license_state(acc)
    add_digest_reasons(acc)
    add_coverage_reasons(acc)
    add_family_reasons(acc)
    return finish_eval(acc)


def _duplicate_id_row(row: dict[str, Any]) -> dict[str, Any]:
    return duplicate_id_row(row)
