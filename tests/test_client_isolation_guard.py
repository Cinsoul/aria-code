"""A document written for one client cannot carry another client's data.

gemini-3.5-flash, operations suite: report_BETA.md named Acme and Gamma and
their SKUs, copied from notes on Beta's own rows. The output rules ask the
model not to; this is the check that does not depend on it remembering.
The data is the eval fixture itself: three shippers in one warehouse file.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from aria_code.apps.cli.tools.write_tools import tool_edit_file, tool_multi_edit, tool_write_file
from aria_code.safety.client_isolation import check_write, client_index, foreign_mentions, target_client

FIXTURE = Path(__file__).resolve().parents[1] / "evals" / "fixtures" / "shipper_isolation" / "inventory.csv"

CLEAN = "# Beta Home Goods\n\nTotal units on hand: 560\n\n- BH-101: 25 on hand, safety stock 40\n"
LEAKY = CLEAN + "- BH-106: 25 on hand — Re-labelled after GAMMA recall GP-104\n"


@pytest.fixture
def warehouse(tmp_path, monkeypatch):
    shutil.copy(FIXTURE, tmp_path / "inventory.csv")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_clients_come_from_the_owner_column(warehouse):
    index = client_index([warehouse])
    assert set(index) == {"ACME", "BETA", "GAMMA"}
    assert "Acme Outdoor Ltd" in index["ACME"].names
    assert "AC-105" in index["ACME"].items


def test_a_file_name_singles_out_one_client(warehouse):
    index = client_index([warehouse])
    assert target_client(Path("report_BETA.md"), index) == "BETA"
    assert target_client(Path("beta-weekly.md"), index) == "BETA"
    assert target_client(Path("BetaHomeGoods_stock.md"), index) == "BETA"
    assert target_client(Path("warehouse_summary.md"), index) is None
    assert target_client(Path("acme_vs_beta.md"), index) is None


def test_other_clients_are_found_in_the_text(warehouse):
    index = client_index([warehouse])
    leaks = foreign_mentions("Shares rack R12 with Acme Outdoor Ltd AC-105. GAMMA recall GP-104.", "BETA", index)
    assert set(leaks) == {"ACME", "GAMMA"}
    assert "AC-105" in leaks["ACME"] and "GP-104" in leaks["GAMMA"]
    assert foreign_mentions(CLEAN, "BETA", index) == {}


def test_a_leaky_client_document_is_not_written(warehouse):
    result = tool_write_file({"path": "report_BETA.md", "content": LEAKY})
    assert not result["success"]
    assert "GAMMA" in result["error"] and "GP-104" in result["error"]
    assert not (warehouse / "report_BETA.md").exists()


def test_a_clean_client_document_is_written(warehouse):
    result = tool_write_file({"path": "report_BETA.md", "content": CLEAN})
    assert result["success"], result
    assert (warehouse / "report_BETA.md").read_text() == CLEAN


def test_an_internal_document_may_name_every_client(warehouse):
    result = tool_write_file({"path": "warehouse_summary.md", "content": LEAKY + "ACME 1169, GAMMA 1958\n"})
    assert result["success"], result


def test_code_is_not_checked(warehouse):
    script = 'rows = [r for r in rows if r["owner_id"] == "BETA"]  # not ACME or GAMMA\n'
    assert check_write(warehouse / "report_BETA.py", script) is None


def test_an_edit_that_leaks_is_refused(warehouse):
    (warehouse / "report_BETA.md").write_text(CLEAN)
    result = tool_edit_file({"path": "report_BETA.md", "old_string": "Total units", "new_string": "Like ACME: total units"})
    assert not result["success"] and "ACME" in result["error"]
    assert (warehouse / "report_BETA.md").read_text() == CLEAN


def test_a_multi_edit_that_leaks_is_refused(warehouse):
    (warehouse / "report_BETA.md").write_text(CLEAN)
    result = tool_multi_edit({"path": "report_BETA.md",
                              "edits": [{"old_string": "560", "new_string": "560 (Gamma Pharma holds 1958)"}]})
    assert not result["success"] and "GAMMA" in result["error"]


def test_no_client_data_means_no_check(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "prices.csv").write_text("date,symbol,close\n2026-10-01,ACME,10\n")
    assert check_write(tmp_path / "report_BETA.md", "ACME GAMMA") is None


def test_a_single_client_file_is_not_a_multi_client_warehouse(tmp_path):
    (tmp_path / "stock.csv").write_text("owner_id,sku,on_hand\nBETA,BH-1,4\n")
    assert check_write(tmp_path / "report_BETA.md", "anything at all") is None
