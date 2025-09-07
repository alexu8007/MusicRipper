import logging
import functools
import traceback
from typing import Any, Callable, Dict, Iterable, Optional, Sequence, Tuple, Type, Union

logger = logging.getLogger(__name__)


def _is_exception_type_tuple(obj: Any) -> bool:
    """Return True if obj is a tuple of Exception types."""
    if not isinstance(obj, tuple):
        return False
    return all(isinstance(t, type) and issubclass(t, BaseException) for t in obj)


def _sanitize_param_value(key: str, value: Any) -> Any:
    """
    Redact values for keys that look sensitive.
    This function intentionally opts for conservative redaction to avoid leaking secrets.
    """
    if not isinstance(key, str):
        return value
    sensitive_indicators = ("password", "pwd", "secret", "token", "api_key", "apikey", "auth", "credential")
    lower_key = key.lower()
    for indicator in sensitive_indicators:
        if indicator in lower_key:
            return "<REDACTED>"
    # For long strings, shorten to avoid log flooding
    if isinstance(value, str) and len(value) > 200:
        return value[:200] + "...<truncated>"
    return value


def _sanitize_params(params: Optional[Union[Dict[str, Any], Sequence[Any]]]) -> Any:
    """
    Produce a sanitized copy of params suitable for logging.
    If params is a mapping, redact sensitive keys. If it's a sequence, represent items safely.
    """
    if params is None:
        return None
    if isinstance(params, dict):
        return {k: _sanitize_param_value(k, v) for k, v in params.items()}
    # For sequences (like args), try to represent each element safely
    if isinstance(params, (list, tuple)):
        sanitized = []
        for idx, val in enumerate(params):
            if isinstance(val, dict):
                sanitized.append(_sanitize_params(val))
            elif isinstance(val, str) and len(val) > 200:
                sanitized.append(val[:200] + "...<truncated>")
            else:
                sanitized.append(val)
        return type(params)(sanitized)
    # Fallback: return as-is (caller should ensure not to log secrets)
    return params


def call_with_handling(
    func: Callable[..., Any],
    /,
    *args: Any,
    exceptions: Optional[Union[Type[BaseException], Tuple[Type[BaseException], ...]]] = Exception,
    fallback: Any = None,
    reraise: bool = False,
    logger_to_use: Optional[logging.Logger] = None,
    context: Optional[Dict[str, Any]] = None,
    sanitize_context_keys: bool = True,
) -> Any:
    """
    Call func(*args) and handle expected exceptions explicitly.

    Parameters:
    - func: callable to invoke.
    - args: positional arguments passed to func.
    - exceptions: exception type or tuple of exception types to catch. Defaults to Exception.
                  Provide precise expected exceptions where possible.
    - fallback: value to return if an expected exception is caught and reraise is False.
    - reraise: if True, re-raise the caught exception after logging; otherwise return fallback.
    - logger_to_use: optional logger; if None the module-level logger is used.
    - context: optional dict of context information to include in logs (will be sanitized).
    - sanitize_context_keys: whether to sanitize/redact sensitive keys in context.

    Behavior:
    - Only exceptions matching 'exceptions' are caught; others propagate.
    - Caught exceptions are logged with structured context and sanitized parameters.
    - When reraise is True, the original exception is re-raised to preserve semantics.
    - When reraise is False, fallback is returned (preserves previous silent-failure fallback).
    """
    chosen_logger = logger_to_use or logger

    # Normalize exceptions argument to a tuple of Exception types
    if exceptions is None:
        exceptions_tuple: Tuple[Type[BaseException], ...] = tuple()
    elif isinstance(exceptions, type) and issubclass(exceptions, BaseException):
        exceptions_tuple = (exceptions,)
    elif _is_exception_type_tuple(exceptions):
        exceptions_tuple = exceptions  # type: ignore
    else:
        raise TypeError("exceptions must be an Exception type or a tuple of Exception types")

    try:
        return func(*args)
    except exceptions_tuple as exc:
        # Prepare structured log context without exposing secrets
        sanitized_context = None
        try:
            if context is not None and sanitize_context_keys and isinstance(context, dict):
                sanitized_context = _sanitize_params(context)
            else:
                sanitized_context = context
        except Exception:
            # If sanitization itself fails, fallback to brief context to avoid crashing logging
            sanitized_context = {"context_sanitization_error": True}

        safe_args = None
        try:
            safe_args = _sanitize_params(args)
        except Exception:
            safe_args = "<args_sanitization_failed>"

        log_record = {
            "function": getattr(func, "__name__", repr(func)),
            "args": safe_args,
            "context": sanitized_context,
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
        }

        # Use structured logging where possible; include stack trace for diagnostics
        chosen_logger.warning(
            "Caught expected exception in call_with_handling",
            extra={"call_info": log_record, "stack": traceback.format_exc()},
        )

        if reraise:
            raise
        return fallback


def safe_call(
    exceptions: Optional[Union[Type[BaseException], Tuple[Type[BaseException], ...]]] = Exception,
    fallback: Any = None,
    reraise: bool = False,
    logger_to_use: Optional[logging.Logger] = None,
    context_provider: Optional[Callable[..., Optional[Dict[str, Any]]]] = None,
):
    """
    Decorator to wrap a function call with explicit exception handling.

    Example:
    @safe_call(exceptions=(KeyError, ValueError), fallback=None, reraise=False)
    def myfunc(...):
        ...

    The decorator will catch only the specified exceptions, log a warning with sanitized inputs,
    and either return the fallback or re-raise depending on reraise.

    Parameters:
    - exceptions: exception type or tuple to catch.
    - fallback: value to return on caught exception when reraise is False.
    - reraise: whether to re-raise the exception after logging.
    - logger_to_use: optional logger instance to use for logging.
    - context_provider: optional callable that receives the same args/kwargs and returns a dict
                        of contextual information to include in logs (should avoid secrets).
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            ctx = None
            if context_provider is not None:
                try:
                    ctx = context_provider(*args, **kwargs)
                except Exception as e:
                    # If context provider fails, log that failure but proceed with sanitized call
                    (logger_to_use or logger).debug(
                        "context_provider raised an exception; proceeding without it: %s", str(e)
                    )
                    ctx = None
            # Pass a combined context that includes limited kwargs and provided context
            combined_context = {}
            if ctx:
                combined_context.update(ctx if isinstance(ctx, dict) else {"context": ctx})
            if kwargs:
                # Include keys of kwargs but sanitize their values in call_with_handling
                combined_context.setdefault("kwargs_keys", list(kwargs.keys()))
            return call_with_handling(
                func,
                *args,
                exceptions=exceptions,
                fallback=fallback,
                reraise=reraise,
                logger_to_use=logger_to_use,
                context=combined_context,
            )
        return wrapper
    return decorator