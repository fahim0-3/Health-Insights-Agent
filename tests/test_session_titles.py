"""Tests for patient-report session titles."""

from pathlib import Path

from utils.session_titles import build_report_title


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROMPTS = (PROJECT_ROOT / "src" / "config" / "prompts.py").read_text(encoding="utf-8")
ANALYSIS_FORM = (
    PROJECT_ROOT / "src" / "components" / "analysis_form.py"
).read_text(encoding="utf-8")


def test_patient_report_title_uses_a_clean_possessive_name():
    assert build_report_title("Karan") == "Karan's Report"
    assert build_report_title("  Karan   Mehta ") == "Karan Mehta's Report"
    assert build_report_title("James") == "James' Report"


def test_missing_patient_name_has_a_safe_fallback_title():
    assert build_report_title("") == "Patient Report"


def test_analysis_prompt_requests_bullet_lists_not_tables():
    assert "Do not use Markdown\ntables" in PROMPTS


def test_successful_analysis_updates_the_chat_session_title():
    assert "update_session_title" in ANALYSIS_FORM
    assert "build_report_title(patient_name)" in ANALYSIS_FORM
