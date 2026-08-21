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


def test_sensitivity_uses_all_low_high_combinations():
    details = {
        "Test Field": {
            "Actual CAPEX": 90_000_000.0,
            "Actual OPEX": 8_000_000.0,
        }
    }
    base = {
        "carbon_credit": 20.0,
        "government_subsidy": 0.0,
        "tax_incentive": 0.0,
        "storage_fee": 5.0,
        "carbon_price": 50.0,
        "discount_rate": 8.0,
        "inflation_rate": 2.5,
        "project_lifetime": 20,
        "injection_rate_mtpa": 1.0,
    }
    ranges = {
        "capex": (85_000_000.0, 100_000_000.0),
        "opex": (5_000_000.0, 15_000_000.0),
        "discount_rate": (6.0, 10.0),
        "inflation_rate": (1.5, 3.5),
        "injection_rate_mtpa": (0.8, 1.2),
        "project_lifetime": (15, 25),
        "carbon_credit": (10.0, 30.0),
    }
    result, scenarios = eng.sensitivity_oat(["Test Field"], details, base, ranges)
    assert len(scenarios["Test Field"]) == 14
    row = result.iloc[0]
    assert row["Sensitivity NPV Min"] < row["Sensitivity NPV Max"]
    assert row["Sensitivity IRR Min (%)"] < row["Sensitivity IRR Max (%)"]
    assert row["Sensitivity Payback Min (years)"] < row["Sensitivity Payback Max (years)"]



def test_sensitivity_includes_all_revenue_drivers():
    details = {
        "Test Field": {
            "Actual CAPEX": 90_000_000.0,
            "Actual OPEX": 8_000_000.0,
        }
    }
    base = {
        "carbon_credit": 20.0,
        "government_subsidy": 5.0,
        "tax_incentive": 3.0,
        "storage_fee": 5.0,
        "carbon_price": 50.0,
        "discount_rate": 8.0,
        "inflation_rate": 2.5,
        "project_lifetime": 20,
        "injection_rate_mtpa": 1.0,
    }
    ranges = {
        "capex": (85_000_000.0, 100_000_000.0),
        "opex": (5_000_000.0, 15_000_000.0),
        "carbon_price": (40.0, 70.0),
        "carbon_credit": (10.0, 30.0),
        "government_subsidy": (0.0, 10.0),
        "tax_incentive": (0.0, 8.0),
        "storage_fee": (2.0, 8.0),
        "discount_rate": (6.0, 10.0),
        "inflation_rate": (1.5, 3.5),
        "injection_rate_mtpa": (0.8, 1.2),
        "project_lifetime": (15, 25),
    }
    result, scenarios = eng.sensitivity_oat(["Test Field"], details, base, ranges)
    sdf = scenarios["Test Field"]
    assert len(sdf) == 22, f"Expected 22 OAT scenarios, got {len(sdf)}"
    assert set(sdf["Parameter"]) == {
        "CAPEX", "OPEX", "Carbon Price", "Carbon Credits",
        "Government Subsidy", "Tax Incentive", "Storage Fee",
        "Discount Rate", "Inflation Rate", "CO2 Injection Rate", "Project Lifetime",
    }
    row = result.iloc[0]
    assert row["Sensitivity NPV Min"] < row["Sensitivity NPV Max"]
    assert row["Sensitivity IRR Min (%)"] < row["Sensitivity IRR Max (%)"]
    assert row["Sensitivity Payback Min (years)"] < row["Sensitivity Payback Max (years)"]
    # Confirm the newly added revenue drivers actually change revenue.
    cp = sdf[sdf["Parameter"] == "Carbon Price"].sort_values("Case")
    assert cp.iloc[0]["Revenue (Year 1)"] != cp.iloc[1]["Revenue (Year 1)"]
    gs = sdf[sdf["Parameter"] == "Government Subsidy"].sort_values("Case")
    assert gs.iloc[0]["Revenue (Year 1)"] != gs.iloc[1]["Revenue (Year 1)"]
    ti = sdf[sdf["Parameter"] == "Tax Incentive"].sort_values("Case")
    assert ti.iloc[0]["Revenue (Year 1)"] != ti.iloc[1]["Revenue (Year 1)"]
    sf = sdf[sdf["Parameter"] == "Storage Fee"].sort_values("Case")
    assert sf.iloc[0]["Revenue (Year 1)"] != sf.iloc[1]["Revenue (Year 1)"]


def test_phase1_eliminated_fields_are_excluded_from_phase2():
    details = {
        "Passed Field": {"Passed": True},
        "Eliminated Field": {"Passed": False},
        "Another Passed Field": {"Passed": True},
    }
    qualified = eng.phase1_qualified_field_names(details)
    assert qualified == ["Passed Field", "Another Passed Field"]
    assert "Eliminated Field" not in qualified



def test_phase2_session_state_is_initialised_and_reset():
    """Regression test for the Streamlit Phase-2 AttributeError."""
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    wanted = {"init_state", "reset_phase1_results", "reset_phase2"}
    nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in wanted]

    class FakeSessionState(dict):
        def __getattr__(self, name):
            try:
                return self[name]
            except KeyError as exc:
                raise AttributeError(name) from exc

        def __setattr__(self, name, value):
            self[name] = value

    class FakeStreamlit:
        def __init__(self):
            self.session_state = FakeSessionState()

    fake_st = FakeStreamlit()
    ns = {"st": fake_st, "pd": pd}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ROOT / "app.py"), "exec"), ns)

    ns["init_state"]()
    assert "phase2_selected_fields" in fake_st.session_state
    assert fake_st.session_state["phase2_selected_fields"] == []

    # Simulate a stale selection and ensure a new Phase-1 run clears it.
    fake_st.session_state["phase2_selected_fields"] = ["Field A"]
    ns["reset_phase1_results"]()
    assert fake_st.session_state["phase2_selected_fields"] == []

    # Simulate another stale selection and ensure Phase-2 reset clears it too.
    fake_st.session_state["phase2_selected_fields"] = ["Field B"]
    ns["reset_phase2"]()
    assert fake_st.session_state["phase2_selected_fields"] == []


def test_phase2_eligibility_excludes_phase1_failed_fields():
    details = {
        "Passed Field": {"Passed": True},
        "Failed Field": {"Passed": False},
        "Missing Passed Flag": {},
    }
    eligible = eng.phase1_qualified_field_names(details)
    assert eligible == ["Passed Field"]
    assert "Failed Field" not in eligible
    assert "Missing Passed Flag" not in eligible


if __name__ == "__main__":
    test_reference()
    test_field_upload()
    test_csv_upload()
    test_revenue_and_economics()
    test_saw_first_and_hard_cutoff_fallback()
    test_sensitivity_uses_all_low_high_combinations()
    test_sensitivity_includes_all_revenue_drivers()
    test_phase1_eliminated_fields_are_excluded_from_phase2()
    test_phase2_session_state_is_initialised_and_reset()
    test_phase2_eligibility_excludes_phase1_failed_fields()
    print("ALL CCS FRAMEWORK OFFLINE REGRESSION TESTS PASSED")
