"""Tests for deterministic medical-safety guardrails."""

from pathlib import Path

from config.prompts import MEDICAL_SAFETY_INSTRUCTIONS, SPECIALIST_PROMPTS
from services.medical_safety import (
    MEDICAL_DISCLAIMER,
    URGENT_CARE_MESSAGE,
    add_medical_disclaimer,
    needs_urgent_care,
    urgent_care_response,
)


AI_SERVICE_SOURCE = (Path(__file__).resolve().parents[1] / "src" / "services" / "ai_service.py").read_text(
    encoding="utf-8"
)


def test_clear_emergency_symptoms_are_not_sent_to_the_ai_chat_flow():
    for message in (
        "I have crushing chest pain",
        "My father has trouble breathing",
        "She has sudden one-sided weakness and slurred speech",
        "There is severe bleeding that will not stop",
        "I think I took an overdose",
    ):
        assert needs_urgent_care(message)
        assert urgent_care_response(message) == URGENT_CARE_MESSAGE


def test_everyday_report_question_does_not_trigger_emergency_response():
    message = "What does a mildly high cholesterol result usually mean?"

    assert not needs_urgent_care(message)
    assert urgent_care_response(message) is None


def test_standard_disclaimer_is_added_once_to_normal_ai_content():
    response = add_medical_disclaimer("Your clinician can help interpret this value.")

    assert MEDICAL_DISCLAIMER in response
    assert response.count("**Medical safety note:**") == 1
    assert add_medical_disclaimer(response) == response


def test_existing_model_safety_note_is_not_duplicated():
    model_response = "**Medical safety note**: This is general information."

    assert add_medical_disclaimer(model_response) == model_response


def test_prompts_use_educational_language_and_not_a_diagnosis_heading():
    analysis_prompt = SPECIALIST_PROMPTS["comprehensive_analyst"]

    assert "### AI Generated Diagnosis:" not in analysis_prompt
    assert "Findings to discuss with a clinician" in analysis_prompt
    assert "not a\nmedical diagnosis" in MEDICAL_SAFETY_INSTRUCTIONS


def test_urgent_screening_happens_before_ai_components_are_initialized():
    chat_function = AI_SERVICE_SOURCE.split("def get_chat_response", 1)[1]

    assert chat_function.index("urgent_care_response(query)") < chat_function.index(
        "init_analysis_state()"
    )
