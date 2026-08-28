import sys
from pathlib import Path
import jsonschema

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.validate_jsonl import validate_file, load_schema  # noqa: E402

V0_SCHEMA_PATH = _REPO_ROOT / "schemas" / "pr_trajectory.schema.json"
V1_SCHEMA_PATH = _REPO_ROOT / "schemas" / "trajectory_v1.schema.json"
FIXTURES_DIR = _REPO_ROOT / "tests" / "fixtures" / "v1"


def get_validators():
    v0_schema = load_schema(V0_SCHEMA_PATH)
    v0_validator = jsonschema.Draft7Validator(
        v0_schema, format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER
    )
    v1_schema = load_schema(V1_SCHEMA_PATH)
    v1_validator = jsonschema.Draft7Validator(
        v1_schema, format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER
    )
    return v0_validator, v1_validator


def test_v1_valid_software():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "software_valid.jsonl", v0, v1, strict_policy=True)
    assert not errors, f"Expected valid software, got {errors}"


def test_v1_valid_research():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "research_valid.jsonl", v0, v1, strict_policy=True)
    assert not errors, f"Expected valid research, got {errors}"


def test_v1_missing_snapshot():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "missing_snapshot.jsonl", v0, v1, strict_policy=True)
    assert any("missing required code snapshots" in e for e in errors), f"Expected missing snapshot error, got {errors}"


def test_v1_malformed_hash():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "malformed_hash.jsonl", v0, v1, strict_policy=True)
    assert any("badhash" in e or "pattern" in e for e in errors), f"Expected malformed hash error, got {errors}"


def test_v1_future_leakage():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "future_leakage.jsonl", v0, v1, strict_policy=True)
    assert any("future-event leakage" in e for e in errors), f"Expected future leakage error, got {errors}"


def test_v1_future_leakage_mixed_offset():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "future_leakage_offset.jsonl", v0, v1, strict_policy=True)
    assert any("future-event leakage" in e for e in errors), f"Expected future leakage error, got {errors}"


def test_v1_nonterminal_positive():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "nonterminal_positive.jsonl", v0, v1, strict_policy=True)
    assert any("nonterminal record incorrectly represented" in e for e in errors), f"Expected nonterminal error, got {errors}"


def test_v1_missing_typed_payload():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "missing_payload.jsonl", v0, v1, strict_policy=True)
    assert any("software_payload" in e or "allOf" in e for e in errors), f"Expected missing payload error, got {errors}"


def test_v1_invented_actor():
    v0, v1 = get_validators()
    errors = validate_file(FIXTURES_DIR / "invented_actor.jsonl", v0, v1, strict_policy=True)
    assert any("wizard" in e or "actor type" in e for e in errors), f"Expected actor error, got {errors}"
