import os
from pathlib import Path

import yaml
from jsonschema import Draft7Validator


PRESET_IDS = [
    "summarizer",
    "meeting_notes",
    "extractor",
    "classifier",
    "triage",
]


def load_preset_yaml(preset_id: str) -> dict:
    """Helper to load a preset YAML by id from app/presets (package data)."""
    presets_dir = Path(__file__).parent.parent / "app" / "presets"
    preset_path = presets_dir / f"{preset_id}.yaml"
    assert preset_path.exists(), f"Preset file not found: {preset_path}"

    with preset_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert isinstance(data, dict), "Preset YAML must deserialize to a mapping"
    return data


def test_all_presets_have_required_fields():
    """
    Each preset YAML must expose the core runtime contract fields.

    Required top-level keys:
    - id
    - version
    - primitive
    - input_schema
    - output_schema
    - prompt
    """
    for preset_id in PRESET_IDS:
        preset = load_preset_yaml(preset_id)

        for key in ["id", "version", "primitive", "input_schema", "output_schema", "prompt"]:
            assert key in preset, f"Preset '{preset_id}' missing required field '{key}'"

        assert preset["id"] == preset_id, "Preset id must match filename"


def test_all_preset_schemas_are_valid_draft7():
    """input_schema and output_schema must be valid JSON Schema Draft-07 documents."""
    for preset_id in PRESET_IDS:
        preset = load_preset_yaml(preset_id)

        input_schema = preset["input_schema"]
        output_schema = preset["output_schema"]

        # Will raise jsonschema.exceptions.SchemaError if invalid
        Draft7Validator.check_schema(input_schema)
        Draft7Validator.check_schema(output_schema)


def test_meeting_notes_schema_shapes():
    """meeting_notes.action_items is array of { owner, task, deadline }."""
    preset = load_preset_yaml("meeting_notes")
    output_schema = preset["output_schema"]

    properties = output_schema.get("properties", {})
    action_items = properties.get("action_items")
    assert action_items is not None, "meeting_notes.output_schema must define 'action_items'"
    assert action_items.get("type") == "array"

    items = action_items.get("items", {})
    assert items.get("type") == "object"
    item_props = items.get("properties", {})

    for field in ["owner", "task", "deadline"]:
        assert field in item_props, f"action_items item must include '{field}'"


def test_triage_schema_shapes():
    """triage.mailbox_context is a string."""
    preset = load_preset_yaml("triage")

    input_schema = preset["input_schema"]
    in_props = input_schema.get("properties", {})
    mailbox_ctx = in_props.get("mailbox_context")
    assert mailbox_ctx is not None, "triage.input_schema must define 'mailbox_context'"
    assert mailbox_ctx.get("type") == "string"


def test_classifier_schema_shapes():
    """
    classifier.items is array of { id, content }
    and classifications is array of { item_id, category, confidence }.
    """
    preset = load_preset_yaml("classifier")

    input_schema = preset["input_schema"]
    output_schema = preset["output_schema"]

    in_props = input_schema.get("properties", {})
    items = in_props.get("items")
    assert items is not None, "classifier.input_schema must define 'items'"
    assert items.get("type") == "array"

    item_schema = items.get("items", {})
    assert item_schema.get("type") == "object"
    item_props = item_schema.get("properties", {})
    for field in ["id", "content"]:
        assert field in item_props, f"classifier.items element must include '{field}'"

    out_props = output_schema.get("properties", {})
    classifications = out_props.get("classifications")
    assert classifications is not None, "classifier.output_schema must define 'classifications'"
    assert classifications.get("type") == "array"

    class_schema = classifications.get("items", {})
    assert class_schema.get("type") == "object"
    class_props = class_schema.get("properties", {})
    for field in ["item_id", "category", "confidence"]:
        assert field in class_props, f"classifications element must include '{field}'"


def test_extractor_schema_shapes():
    """
    extractor input.schema is mapping of field_name -> description,
    and output has { data, confidence }.

    NOTE: This is intentionally a looser contract because the exact
    structure of the extracted data is preset-specific. We only require:
    - input_schema.properties.schema: object with arbitrary keys
    - output_schema.properties has 'data' and 'confidence' keys.
    """
    preset = load_preset_yaml("extractor")

    input_schema = preset["input_schema"]
    output_schema = preset["output_schema"]

    in_props = input_schema.get("properties", {})
    schema_field = in_props.get("schema")
    assert schema_field is not None, "extractor.input_schema must define 'schema'"
    assert schema_field.get("type") == "object"

    out_props = output_schema.get("properties", {})
    for field in ["data", "confidence"]:
        assert field in out_props, f"extractor.output_schema must include '{field}'"

