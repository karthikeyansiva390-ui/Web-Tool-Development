"""Offline regression tests for the CCS Streamlit framework.

These tests do not launch Streamlit. They test the reference parser, the field
workbook shape, SAW-first/hard-cutoff fallback behavior, and Phase-2 revenue
calculation using the actual sample/reference workbooks supplied with the project.
"""
from __future__ import annotations

import ast
import io
from pathlib import Path
import re
import types

import pandas as pd

ROOT = Path(__file__).parent
SAMPLE_FIELD = Path("/mnt/data/Field Data - 1(2).xlsx")
REFERENCE = Path("/mnt/data/Reference Data sheet (with values)(2).xlsx")

import ccs_engine as eng


def load_app_functions():
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    wanted = {
        "_find_header_row", "_clean_import_table", "parse_field_upload",
        "validate_manual_value", "is_qualitative_spec", "qualitative_reference_choices",
    }
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in wanted]
    ns = {
        "pd": pd, "io": io, "re": re,
        "Any": object, "Path": Path,
        "CATEGORIES": eng.CATEGORIES,
        "norm_text": eng.norm_text,
        "is_missing": eng.is_missing,
        "parse_number_strict": eng.parse_number_strict,
        "split_choices": eng.split_choices,
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ROOT / "app.py"), "exec"), ns)
    return ns


def test_reference():
    ref = eng.parse_reference(REFERENCE.read_bytes(), REFERENCE.name)
    assert sum(len(ref["categories"][c]) for c in eng.CATEGORIES) == 68
    assert all(ref["categories"][c] for c in eng.CATEGORIES)
    return ref


def test_field_upload():
    ref = test_reference()
    ns = load_app_functions()
    parsed, errors = ns["parse_field_upload"](SAMPLE_FIELD.read_bytes(), SAMPLE_FIELD.name, ref)
    assert errors == [], errors
    assert set(parsed["values"]) == set(eng.CATEGORIES)
    assert parsed["actual_capex"] == ""
    assert parsed["actual_opex"] == ""



def test_csv_upload():
    ref = test_reference()
    ns = load_app_functions()
    sample_param = ref["categories"]["Technical"][0]["parameter"]
    csv = f"Category,Parameter,Value,Unit/Type\nTechnical,{sample_param},12,mD\n".encode()
    parsed, errors = ns["parse_field_upload"](csv, "field.csv", ref)
    assert errors == [], errors
    assert parsed["values"]["Technical"][sample_param] == "12"

def test_revenue_and_economics():
    # 1 Mt/year * ($20 credit + $50 carbon price) = $70 million/year.
    npv, irr, pb, revenue, cashflows = eng.project_cashflows(
        actual_capex=100_000_000,
        actual_opex=10_000_000,
        carbon_credit=20,
        government_subsidy=0,
        tax_incentive=0,
        storage_fee=0,
        discount_rate_pct=8,
        inflation_rate_pct=0,
        project_lifetime=10,
        injection_rate_mtpa=1,
        carbon_price=50,
    )
    assert abs(revenue - 70_000_000) < 1e-6
    assert len(cashflows) == 11


def test_phase1_failed_fields_are_permanently_excluded_from_phase2():
    details = {
        "Passed Field": {"Passed": True},
        "Failed Field": {"Passed": False},
        "Missing Flag Field": {},
    }
    assert eng.phase1_qualified_fields(details) == ["Passed Field"]


def test_saw_first_and_hard_cutoff_fallback():
    spec = {
        "parameter": "Test", "data_type": "mD", "hard_cutoff": "> 50",
        "ahp_weight_normalized": 1.0,
        "saw_ranges": [(0,10,1),(10,20,2),(20,30,3),(30,40,4),(40,50,5)],
    }
    r1 = eng.evaluate_parameter(45, "mD", spec)
    assert r1["pass"] is True and r1["saw_score"] == 5

    r2 = eng.evaluate_parameter(55, "mD", spec)
    assert r2["pass"] is True and r2["saw_score"] is None and r2["weighted_score"] is None

    r3 = eng.evaluate_parameter(-5, "mD", spec)
    assert r3["pass"] is False


if __name__ == "__main__":
    test_reference()
    test_field_upload()
    test_csv_upload()
    test_revenue_and_economics()
    test_phase1_failed_fields_are_permanently_excluded_from_phase2()
    test_saw_first_and_hard_cutoff_fallback()
    print("ALL CCS FRAMEWORK OFFLINE REGRESSION TESTS PASSED")
