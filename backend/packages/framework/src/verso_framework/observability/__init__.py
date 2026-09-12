from contextvars import ContextVar

trace_id_var: ContextVar[str] = ContextVar("verso_trace_id", default="")


def current_trace_id() -> str:
    return trace_id_var.get()
