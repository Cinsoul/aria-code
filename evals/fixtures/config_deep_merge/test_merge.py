"""One warehouse changing its carrier timeout must not change everyone's."""

import copy

from merge import DEFAULTS, merge_config


def test_nested_keys_merge():
    merged = merge_config(DEFAULTS, {"carrier": {"timeout": 60}})
    assert merged["carrier"] == {"name": "SF", "timeout": 60, "retries": 3}
    assert merged["label"] == {"size": "4x6", "dpi": 203}


def test_lists_are_replaced_not_joined():
    assert merge_config(DEFAULTS, {"warehouses": ["PEK"]})["warehouses"] == ["PEK"]


def test_an_explicit_none_is_kept():
    assert merge_config(DEFAULTS, {"label": None})["label"] is None


def test_neither_input_changes():
    before = copy.deepcopy(DEFAULTS)
    override = {"carrier": {"timeout": 60}}
    merge_config(DEFAULTS, override)
    assert DEFAULTS == before
    assert override == {"carrier": {"timeout": 60}}


def test_changing_the_result_leaves_the_defaults_alone():
    before = copy.deepcopy(DEFAULTS)
    merged = merge_config(DEFAULTS, {"carrier": {"timeout": 60}})
    merged["carrier"]["name"] = "JD"
    merged["label"]["dpi"] = 300
    merged["warehouses"].append("CAN")
    assert DEFAULTS == before
