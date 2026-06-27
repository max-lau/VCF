"""
ParaIQ AI Observability — Langfuse 4.x integration.
"""
import os
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '.env'))
from langfuse import Langfuse
from langfuse.types import TraceContext
from typing import Optional

_langfuse: Optional[Langfuse] = None
_langfuse_enabled: Optional[bool] = None

def _langfuse_is_configured() -> bool:
    """Check if Langfuse env vars are present."""
    return bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))

def get_langfuse() -> Optional[Langfuse]:
    global _langfuse, _langfuse_enabled
    if _langfuse_enabled is None:
        _langfuse_enabled = _langfuse_is_configured()
    if not _langfuse_enabled:
        return None
    if _langfuse is None:
        _langfuse = Langfuse(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
            host=os.getenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")
        )
    return _langfuse

def trace_claude_call(
    client,
    name: str,
    model: str,
    messages: list,
    max_tokens: int,
    user_id: str = "unknown",
    session_id: str = None,
    tags: list = None,
    firm_id: str = "default",
    **kwargs
):
    """
    Drop-in wrapper for client.messages.create() with Langfuse 4.x tracing.
    Falls back to a plain call if Langfuse is not configured.
    Returns (response, trace_id).
    """
    lf = get_langfuse()
    if lf is None:
        # Langfuse not configured — make a plain call
        response = client.messages.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            **kwargs
        )
        return response, None
    trace_id = lf.create_trace_id()
    ctx = TraceContext(trace_id=trace_id)
    with lf.start_as_current_observation(
        trace_context=ctx,
        name=name,
        as_type="generation",
        input=messages,
        model=model,
        metadata={"user_id": user_id, "session_id": session_id, "firm_id": firm_id, "tags": tags or ["paraiq"]},
    ) as obs:
        try:
            response = client.messages.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                **kwargs
            )
            output_text = response.content[0].text if response.content else ""
            obs.update(
                output=output_text,
                usage_details={
                    "input":  response.usage.input_tokens,
                    "output": response.usage.output_tokens,
                },
                level="DEFAULT"
            )
            lf.flush()
            return response, trace_id
        except Exception as e:
            obs.update(output="error", level="ERROR")
            lf.flush()
            raise
