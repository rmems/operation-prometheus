"""Markdown/HTML license-disclosure fail-closed cases."""

from __future__ import annotations


from license_closure_fixtures import (
    spdx_known_bundle,
)
from license_closure_helpers import _assert_schema, _report


def test_html_comment_is_not_markdown_disclosure():
    bundle = spdx_known_bundle()
    bundle["markdown"] = "## License / provenance\n\n<!-- MIT -->\n"
    report = _report(bundle)
    _assert_schema(report)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_commented_license_heading_is_not_markdown_disclosure():
    bundle = spdx_known_bundle()
    bundle["markdown"] = "<!--\n## License / provenance\n-->\nMIT\n"
    report = _report(bundle)
    _assert_schema(report)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_fenced_license_heading_is_not_markdown_disclosure():
    bundle = spdx_known_bundle()
    bundle["markdown"] = "```\n## License / provenance\nMIT\n```\n"
    report = _report(bundle)
    _assert_schema(report)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_h1_after_license_section_is_not_disclosure():
    bundle = spdx_known_bundle()
    bundle["markdown"] = "## License / provenance\n\nNo license\n# Appendix\nMIT\n"
    report = _report(bundle)
    _assert_schema(report)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_markdown_link_destination_is_not_disclosure():
    bundle = spdx_known_bundle()
    bundle["markdown"] = (
        "## License / provenance\n\n[license details](https://example.test/MIT)\n"
    )
    report = _report(bundle)
    _assert_schema(report)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_markdown_link_text_is_disclosure():
    bundle = spdx_known_bundle()
    bundle["markdown"] = (
        "## License / provenance\n\n[MIT](https://example.test/license)\n"
    )
    report = _report(bundle)
    _assert_schema(report)
    assert report["closed"] is True


def test_hidden_html_is_not_markdown_disclosure():
    bundle = spdx_known_bundle()
    bundle["markdown"] = "## License / provenance\n\n<span hidden>MIT</span>\n"
    report = _report(bundle)
    _assert_schema(report)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_hidden_license_heading_is_not_markdown_disclosure():
    bundle = spdx_known_bundle()
    bundle["markdown"] = "<div hidden>\n## License / provenance\nMIT\n</div>\n"
    report = _report(bundle)
    _assert_schema(report)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_void_tag_inside_hidden_html_is_not_markdown_disclosure():
    bundle = spdx_known_bundle()
    bundle["markdown"] = "<div hidden>\n<br/>\n## License / provenance\nMIT\n</div>\n"
    report = _report(bundle)
    _assert_schema(report)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_script_html_is_not_markdown_disclosure():
    bundle = spdx_known_bundle()
    bundle["markdown"] = "## License / provenance\n\n<script>MIT</script>\n"
    report = _report(bundle)
    _assert_schema(report)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_visible_html_is_markdown_disclosure():
    bundle = spdx_known_bundle()
    bundle["markdown"] = "## License / provenance\n\n<p>MIT</p>\n"
    report = _report(bundle)
    _assert_schema(report)
    assert report["closed"] is True


def test_multiline_reference_title_is_not_markdown_disclosure():
    bundle = spdx_known_bundle()
    bundle["markdown"] = (
        '## License / provenance\n\n[details]: https://example.test/license\n  "MIT"\n'
    )
    report = _report(bundle)
    _assert_schema(report)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


def test_indented_h2_after_license_section_is_not_disclosure():
    bundle = spdx_known_bundle()
    bundle["markdown"] = "## License / provenance\nNo license\n ## Appendix\nMIT\n"
    report = _report(bundle)
    _assert_schema(report)
    assert "card_disclosure_missing" in report["quarantined"][0]["reason_codes"]
    assert report["released_positives"] == []


