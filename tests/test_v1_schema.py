import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.validate_jsonl import validate_file, load_schema
import jsonschema

V0_SCHEMA_PATH = Path("schemas/pr_trajectory.schema.json")
V1_SCHEMA_PATH = Path("schemas/trajectory_v1.schema.json")

def get_validators():
    v0_schema = load_schema(V0_SCHEMA_PATH)
    v0_validator = jsonschema.Draft7Validator(v0_schema)
    v1_schema = load_schema(V1_SCHEMA_PATH)
    v1_validator = jsonschema.Draft7Validator(v1_schema)
    return v0_validator, v1_validator

def test_v1_valid_software():
    v0, v1 = get_validators()
    errors = validate_file(Path("tests/fixtures/v1/software_valid.jsonl"), v0, v1, strict_policy=True)
    assert not errors, f"Expected valid software, got {errors}"

def test_v1_valid_research():
    v0, v1 = get_validators()
    errors = validate_file(Path("tests/fixtures/v1/research_valid.jsonl"), v0, v1, strict_policy=True)
    assert not errors, f"Expected valid research, got {errors}"

def test_v1_missing_snapshot():
    v0, v1 = get_validators()
    errors = validate_file(Path("tests/fixtures/v1/missing_snapshot.jsonl"), v0, v1, strict_policy=True)
    assert any("missing required code snapshots" in e for e in errors), f"Expected missing snapshot error, got {errors}"

def test_v1_malformed_hash():
    v0, v1 = get_validators()
    errors = validate_file(Path("tests/fixtures/v1/malformed_hash.jsonl"), v0, v1, strict_policy=True)
    assert any("badhash" in e or "pattern" in e for e in errors), f"Expected malformed hash error, got {errors}"

def test_v1_future_leakage():
    v0, v1 = get_validators()
    errors = validate_file(Path("tests/fixtures/v1/future_leakage.jsonl"), v0, v1, strict_policy=True)
    assert any("future-event leakage" in e for e in errors), f"Expected future leakage error, got {errors}"

def test_v1_nonterminal_positive():
    v0, v1 = get_validators()
    errors = validate_file(Path("tests/fixtures/v1/nonterminal_positive.jsonl"), v0, v1, strict_policy=True)
    assert any("nonterminal record incorrectly represented" in e for e in errors), f"Expected nonterminal error, got {errors}"

def test_v1_invented_actor():
    v0, v1 = get_validators()
    errors = validate_file(Path("tests/fixtures/v1/invented_actor.jsonl"), v0, v1, strict_policy=True)
    assert any("wizard" in e or "actor type" in e for e in errors), f"Expected actor error, got {errors}"

