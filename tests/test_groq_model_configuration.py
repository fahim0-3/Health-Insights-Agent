"""Regression checks for Groq model identifiers used by the application."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_MANAGER = (PROJECT_ROOT / "src" / "agents" / "model_manager.py").read_text(
    encoding="utf-8"
)
CHAT_AGENT = (PROJECT_ROOT / "src" / "agents" / "chat_agent.py").read_text(
    encoding="utf-8"
)


def test_analysis_uses_current_groq_gpt_oss_model_ids():
    assert '"openai/gpt-oss-20b"' in MODEL_MANAGER
    assert '"openai/gpt-oss-120b"' in MODEL_MANAGER
    assert "llama3-70b-8192" not in MODEL_MANAGER
    assert "llama-3.3-70b-versatile" not in MODEL_MANAGER


def test_chat_uses_current_groq_gpt_oss_model_id():
    assert 'self.model_name = "openai/gpt-oss-20b"' in CHAT_AGENT
