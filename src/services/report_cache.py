"""Privacy-safe keys for short-lived, in-memory report processing caches."""

from hashlib import sha256


def build_report_cache_key(user_id, session_id, report_text):
    """Return a cache key isolated by owner, chat session, and report content.

    The report text itself is never included in the key. A digest prevents two
    reports with the same length from reusing the wrong vector store.
    """
    if not user_id or not session_id:
        raise ValueError("A user ID and chat session ID are required for caching")

    content_hash = sha256(report_text.encode("utf-8")).hexdigest()
    return f"{user_id}:{session_id}:{content_hash}"
