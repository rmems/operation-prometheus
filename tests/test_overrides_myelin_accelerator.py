"""Per-PR override regressions for rmems/myelin-accelerator (GH #21).

Split out of ``test_collect_and_normalize.py`` so a new extract adds its own file
instead of appending to the shared suite.
"""

from __future__ import annotations


def test_linked_issue_override_table_entries():
    from lib.normalize import LINKED_ISSUE_OVERRIDE

    assert LINKED_ISSUE_OVERRIDE[("rmems/myelin-accelerator", 18)] == (16, 13, 12, 10, 11)
    assert LINKED_ISSUE_OVERRIDE[("rmems/myelin-accelerator", 26)] == (9,)


def test_myelin_accelerator_linked_issue_overrides_in_normalize_record():
    """GH #21: PR #18/#26 issue URLs come from LINKED_ISSUE_OVERRIDE via normalize_record."""
    from lib.normalize import normalize_record

    base = {
        "linked_issues": [],
        "reviews": [],
        "review_comments": [],
        "issue_comments": [],
        "files": [{"filename": "src/lib.rs", "status": "modified", "patch": "+x\n"}],
        "checks": {},
        "commits": [],
        "pull": {
            "state": "closed",
            "merged": True,
            "draft": False,
            "body": "No close keywords here.",
        },
    }
    raw18 = {
        **base,
        "source": {"repo": "rmems/myelin-accelerator", "pr_number": 18},
        "pull": {
            **base["pull"],
            "title": "Implement #16, #13, #12, #10, #11: License, CI, Bitpacking",
        },
    }
    urls18 = normalize_record(raw18, {})["source_urls"]
    assert urls18[0] == "https://github.com/rmems/myelin-accelerator/pull/18"
    assert urls18[1:] == [
        "https://github.com/rmems/myelin-accelerator/issues/16",
        "https://github.com/rmems/myelin-accelerator/issues/13",
        "https://github.com/rmems/myelin-accelerator/issues/12",
        "https://github.com/rmems/myelin-accelerator/issues/10",
        "https://github.com/rmems/myelin-accelerator/issues/11",
    ]

    raw26 = {
        **base,
        "source": {"repo": "rmems/myelin-accelerator", "pr_number": 26},
        "pull": {
            **base["pull"],
            "title": "feat: packed ternary GEMV/GEMM kernels and CUDA 13.3.1 CI",
        },
    }
    urls26 = normalize_record(raw26, {})["source_urls"]
    assert urls26 == [
        "https://github.com/rmems/myelin-accelerator/pull/26",
        "https://github.com/rmems/myelin-accelerator/issues/9",
    ]


def test_myelin_accelerator_wip_prs_task_type_feature():
    """GH #21: WIP titles for #6/#7 must resolve to feature via TASK_TYPE_OVERRIDE."""
    from lib.normalize import task_type_for

    for pr in (6, 7):
        raw = {
            "pull": {
                "title": "[WIP] Update repository with Corinth Canal CUDA and cust codes"
            }
        }
        assert task_type_for("rmems/myelin-accelerator", pr, raw) == "feature"
