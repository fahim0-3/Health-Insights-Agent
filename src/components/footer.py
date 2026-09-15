import streamlit as st


def show_footer(in_sidebar=False):
    """Render a neutral application footer."""
    margin_top = "0" if in_sidebar else "2rem"
    st.markdown(
        f"""
        <div style="
            text-align: center;
            padding: 0.75rem;
            margin-top: {margin_top};
            border-top: 1px solid rgba(100, 181, 246, 0.15);
            color: #1976D2;
            font-size: 0.75rem;
        ">
            <span>Health Insights Agent</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
