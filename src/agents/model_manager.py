import groq
import streamlit as st
from enum import Enum
import logging
import time
from utils.app_logging import get_logger, log_event, log_exception

logger = get_logger(__name__)

class ModelTier(Enum):
    PRIMARY = "primary"
    SECONDARY = "secondary"

class ModelManager:
    """
    Manages AI model selection, fallback, and rate limits.
    Implements an agent-based approach for model management.
    """

    MODEL_CONFIG = {
        ModelTier.PRIMARY: {
            "provider": "groq",
            "model": "openai/gpt-oss-20b",
            "max_tokens": 2000,
            "temperature": 0.7
        },
        ModelTier.SECONDARY: {
            "provider": "groq",
            "model": "openai/gpt-oss-120b",
            "max_tokens": 2000,
            "temperature": 0.7
        },
    }

    def __init__(self):
        self.clients = {}
        self._initialize_clients()

    def _initialize_clients(self):
        """Initialize API clients for each provider."""
        try:
            self.clients["groq"] = groq.Groq(api_key=st.secrets["GROQ_API_KEY"])
        except Exception as error:
            log_exception(
                logger,
                "ai_client_initialization_failed",
                error,
                component="model_manager",
                provider="groq",
            )

    def generate_analysis(self, data, system_prompt, retry_count=0):
        """
        Generate analysis using the best available model with automatic fallback.
        Implements agent-based decision making for model selection.
        """
        if retry_count > 1:
            return {"success": False, "error": "All models failed after multiple retries"}

        # Determine which model tier to use based on retry count
        if retry_count == 0:
            tier = ModelTier.PRIMARY
        else:
            tier = ModelTier.SECONDARY

        model_config = self.MODEL_CONFIG[tier]
        provider = model_config["provider"]
        model = model_config["model"]

        # Check if we have a client for this provider
        if provider not in self.clients:
            log_event(
                logger,
                "ai_client_unavailable",
                level=logging.ERROR,
                component="model_manager",
                provider=provider,
            )
            return self.generate_analysis(data, system_prompt, retry_count + 1)

        try:
            client = self.clients[provider]
            log_event(
                logger,
                "analysis_generation_started",
                component="model_manager",
                provider=provider,
                model=model,
            )

            if provider == "groq":
                completion = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": str(data)}
                    ],
                    temperature=model_config["temperature"],
                    max_tokens=model_config["max_tokens"]
                )

                return {
                    "success": True,
                    "content": completion.choices[0].message.content,
                    "model_used": f"{provider}/{model}"
                }

        except Exception as error:
            log_exception(
                logger,
                "analysis_generation_failed",
                error,
                component="model_manager",
                provider=provider,
                model=model,
            )
            # Try next model in hierarchy
            return self.generate_analysis(data, system_prompt, retry_count + 1)

        return {"success": False, "error": "Analysis failed with all available models"}
