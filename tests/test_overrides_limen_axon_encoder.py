"""Per-PR override regressions for Limen-Neural/axon-encoder (GH #13, #15).

Split out of ``test_collect_and_normalize.py`` so a new extract adds its own file
instead of appending to the shared suite.
"""

from __future__ import annotations


def test_sec_title_is_security_task_type():
    from lib.normalize import task_type_for

    raw = {"pull": {"title": "sec(rng): replace insecure xorshift with rand"}}
    assert task_type_for("Limen-Neural/axon-encoder", 50, raw) == "security"


def test_domain_by_pr_on_card():
    from lib.normalize import domain_for

    card = {
        "domains": ["snn"],
        "domain_by_pr": {"50": "security", "41": "api", "37": "snn", "99": None},
    }
    assert domain_for("Limen-Neural/axon-encoder", 50, card, {}) == "security"
    assert domain_for("Limen-Neural/axon-encoder", 41, card, {}) == "api"
    assert domain_for("Limen-Neural/axon-encoder", 37, card, {}) == "snn"
    # Malformed values ignored; fall back to first card domain.
    assert domain_for("Limen-Neural/axon-encoder", 99, card, {}) == "snn"
