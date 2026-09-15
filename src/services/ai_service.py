import streamlit as st
from agents.analysis_agent import AnalysisAgent
from services.medical_safety import add_medical_disclaimer, urgent_care_response
from services.report_cache import build_report_cache_key
from utils.app_logging import get_logger, log_exception
# from agents.chat_agent import ChatAgent


logger = get_logger(__name__)


def init_analysis_state():
    """Initialize analysis-related session state variables."""
    if "analysis_agent" not in st.session_state:
        st.session_state.analysis_agent = AnalysisAgent()

    if "chat_agent" not in st.session_state:
        try:
            from agents.chat_agent import ChatAgent

            # Check if GROQ_API_KEY exists before initializing
            if "GROQ_API_KEY" not in st.secrets:
                st.session_state.chat_agent = None
                st.session_state.chat_agent_error = "GROQ_API_KEY not found in secrets. Please add it to .streamlit/secrets.toml"
            else:
                st.session_state.chat_agent = ChatAgent()
                st.session_state.chat_agent_error = None
        except KeyError as error:
            # Missing secret key
            st.session_state.chat_agent = None
            log_exception(logger, "chat_agent_configuration_missing", error, component="ai_service")
            st.session_state.chat_agent_error = "Chat configuration is incomplete. Please check the app setup."
        except ImportError as error:
            # Import error (missing dependencies)
            st.session_state.chat_agent = None
            log_exception(logger, "chat_agent_dependency_missing", error, component="ai_service")
            st.session_state.chat_agent_error = "Chat dependencies are unavailable. Please check the app setup."
        except Exception as error:
            # Other initialization errors
            st.session_state.chat_agent = None
            log_exception(logger, "chat_agent_initialization_failed", error, component="ai_service")
            st.session_state.chat_agent_error = "Chat is temporarily unavailable. Please try again later."


def check_rate_limit():
    # Ensure analysis agent is initialized
    init_analysis_state()
    return st.session_state.analysis_agent.check_rate_limit()


def generate_analysis(data, system_prompt, check_only=False, session_id=None):
    """Generate analysis if within rate limits."""
    # Ensure analysis agent is initialized
    init_analysis_state()

    # For check_only, we just need to check rate limits
    if check_only:
        return st.session_state.analysis_agent.check_rate_limit()

    # Call analyze_report without the chat_history parameter
    return st.session_state.analysis_agent.analyze_report(
        data=data, system_prompt=system_prompt, check_only=False
    )


def get_chat_response(query, context_text, chat_history):
    """Generate chat response using RAG."""
    urgent_response = urgent_care_response(query)
    if urgent_response:
        return urgent_response

    init_analysis_state()

    # Check if chat agent was successfully initialized
    if st.session_state.chat_agent is None:
        error_msg = st.session_state.get(
            "chat_agent_error",
            "Chat functionality is currently unavailable. Please check your GROQ_API_KEY configuration in .streamlit/secrets.toml",
        )
        return f"Error: {error_msg}"

    # Handle empty context - try to extract from chat history if available
    if not context_text and chat_history:
        # First, try to find the stored report text in system messages
        for msg in chat_history:
            if msg.get("role") == "system" and "__REPORT_TEXT__" in msg.get(
                "content", ""
            ):
                # Extract report text from system message
                content = msg.get("content", "")
                start_idx = content.find("__REPORT_TEXT__\n") + len("__REPORT_TEXT__\n")
                end_idx = content.find("\n__END_REPORT_TEXT__")
                if start_idx > len("__REPORT_TEXT__\n") - 1 and end_idx > start_idx:
                    context_text = content[start_idx:end_idx]
                    break

        # If still no context, try to extract from the first analysis message
        if not context_text:
            for msg in reversed(chat_history):
                if msg["role"] == "assistant" and len(msg.get("content", "")) > 100:
                    # This might be the analysis - use it as partial context
                    # But we'll still work without vector store if needed
                    context_text = msg["content"][:5000]  # Limit context size
                    break

    # Handle empty context_text - create a minimal vector store or skip RAG
    if not context_text:
        # If no context, we'll use chat history only
        # Create a dummy vector store with minimal content to avoid errors
        context_text = "No report context available. Relying on chat history only."

    user_id = st.session_state.get("user", {}).get("id")
    session_id = st.session_state.get("current_session", {}).get("id")
    if not user_id or not session_id:
        return "Error: Your session is unavailable. Please sign in again."

    cache_key = build_report_cache_key(user_id, session_id, context_text)
    if "vector_store" not in st.session_state or st.session_state.get(
        "vector_store_cache_key"
    ) != cache_key:
        try:
            with st.spinner("Processing context..."):
                st.session_state.vector_store = (
                    st.session_state.chat_agent.initialize_vector_store(context_text)
                )
                st.session_state.vector_store_cache_key = cache_key
        except Exception as error:
            log_exception(logger, "vector_store_initialization_failed", error, component="ai_service")
            # If vector store creation fails, create a minimal one
            st.warning("Could not prepare report context. Using chat history only.")
            try:
                st.session_state.vector_store = (
                    st.session_state.chat_agent.initialize_vector_store(
                        "No report context available."
                    )
                )
                st.session_state.vector_store_cache_key = cache_key
            except Exception as fallback_error:
                log_exception(logger, "fallback_vector_store_initialization_failed", fallback_error, component="ai_service")
                # Last resort - return error
                return "Error: Could not prepare report context. Please try again."

    response = st.session_state.chat_agent.get_response(
        query, st.session_state.vector_store, chat_history
    )
    if response.startswith("Error:"):
        return response
    return add_medical_disclaimer(response)
