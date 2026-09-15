"""Human-readable titles for report chat sessions."""


def build_report_title(patient_name):
    """Create a concise title from the name entered with a report."""
    cleaned_name = " ".join(str(patient_name or "").split())[:60]
    if not cleaned_name:
        return "Patient Report"
    possessive = "'" if cleaned_name.lower().endswith("s") else "'s"
    return f"{cleaned_name}{possessive} Report"
