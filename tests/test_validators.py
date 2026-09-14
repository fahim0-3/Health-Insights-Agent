"""Tests for the validation rules used by the signup and upload flows."""

import pytest

from utils.validators import (
    validate_email,
    validate_password,
    validate_pdf_content,
    validate_pdf_file,
    validate_signup_fields,
)


class UploadedFile:
    """Small stand-in for Streamlit's uploaded-file object."""

    def __init__(self, size, content_type):
        self.size = size
        self.type = content_type


@pytest.mark.parametrize(
    ("password", "expected_message"),
    [
        ("Short1a", "Password must be at least 8 characters long"),
        ("lowercase1", "Password must contain at least one uppercase letter"),
        ("UPPERCASE1", "Password must contain at least one lowercase letter"),
        ("NoNumberHere", "Password must contain at least one number"),
    ],
)
def test_validate_password_rejects_invalid_passwords(password, expected_message):
    assert validate_password(password) == (False, expected_message)


def test_validate_password_accepts_valid_password():
    assert validate_password("SecurePass1") == (True, None)


@pytest.mark.parametrize(
    "email",
    ["person@example.com", "person.name@example.co.uk"],
)
def test_validate_email_accepts_valid_addresses(email):
    assert validate_email(email) is True


@pytest.mark.parametrize("email", ["not-an-email", "person@", "@example.com"])
def test_validate_email_rejects_invalid_addresses(email):
    assert validate_email(email) is False


@pytest.mark.parametrize(
    ("fields", "expected_message"),
    [
        (("", "person@example.com", "SecurePass1", "SecurePass1"), "Please fill in all fields"),
        (("Person", "invalid", "SecurePass1", "SecurePass1"), "Please enter a valid email address"),
        (("Person", "person@example.com", "SecurePass1", "DifferentPass1"), "Passwords do not match"),
        (("Person", "person@example.com", "short", "short"), "Password must be at least 8 characters long"),
    ],
)
def test_validate_signup_fields_rejects_invalid_submissions(fields, expected_message):
    assert validate_signup_fields(*fields) == (False, expected_message)


def test_validate_signup_fields_accepts_complete_valid_submission():
    assert validate_signup_fields("Person", "person@example.com", "SecurePass1", "SecurePass1") == (True, None)


def test_validate_pdf_file_rejects_missing_file():
    assert validate_pdf_file(None) == (False, "No file uploaded")


def test_validate_pdf_file_rejects_oversized_file():
    oversized_pdf = UploadedFile(20 * 1024 * 1024 + 1, "application/pdf")
    is_valid, message = validate_pdf_file(oversized_pdf)

    assert is_valid is False
    assert "exceeds the 20MB limit" in message


def test_validate_pdf_file_rejects_non_pdf_content_type():
    assert validate_pdf_file(UploadedFile(1024, "text/plain")) == (
        False,
        "Invalid file type. Please upload a PDF file",
    )


def test_validate_pdf_file_accepts_pdf_within_limit():
    assert validate_pdf_file(UploadedFile(20 * 1024 * 1024, "application/pdf")) == (True, None)


def test_validate_pdf_content_rejects_short_text():
    assert validate_pdf_content("blood report") == (
        False,
        "Extracted text is too short. Please ensure the PDF contains valid text.",
    )


def test_validate_pdf_content_rejects_non_medical_text():
    text = "This document describes a holiday itinerary with travel dates and hotel details. " * 2
    assert validate_pdf_content(text) == (
        False,
        "The uploaded file doesn't appear to be a medical report. Please upload a valid medical report.",
    )


def test_validate_pdf_content_accepts_medical_report_text():
    text = (
        "Laboratory blood test report for patient. Results include hemoglobin, WBC, "
        "platelet count, glucose, and a reference range for each measurement."
    )
    assert validate_pdf_content(text) == (True, None)
