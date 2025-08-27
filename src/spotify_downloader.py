import logging
import functools
import traceback
from typing import Any, Callable, Dict, Iterable, Optional, Sequence, Tuple, Type, Union

logger = logging.getLogger(__name__)


def _is_exception_type_tuple(obj: Any) -> bool:
    """
    Return True if obj is a tuple containing only exception types.
    
    Checks that obj is a tuple and that every element is a class subclassing BaseException.
    
    Returns:
        bool: True if obj is a tuple of exception types, otherwise False.
    """
    if not isinstance(obj, tuple):
        return False
    return all(isinstance(t, type) and issubclass(t, BaseException) for t in obj)


def _sanitize_param_value(key: str, value: Any) -> Any:
    """
    Return a sanitized value for logging: redact sensitive keys and truncate long strings.
    
    This function inspects the parameter name `key` (must be a str) for common sensitive indicators
    (e.g. "password", "token", "api_key", "auth", "secret", "credential"). If any indicator is
    present in `key` (case-insensitive), the function returns the literal "<REDACTED>".
    If `key` is not a string, the original `value` is returned unchanged.
    
    For non-redacted string values longer than 200 characters, the function returns a truncated
    version (first 200 characters) with the suffix "...<truncated>" to avoid log flooding.
    All other values are returned unchanged.
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
    Return a sanitized representation of `params` suitable for logging.
    
    If `params` is None, returns None. If it's a dict, returns a new dict with values redacted or truncated for sensitive keys via _sanitize_param_value. If it's a list or tuple, returns a sequence of the same type where:
    - dict elements are recursively sanitized,
    - strings longer than 200 characters are truncated to 200 characters and appended with "...<truncated>",
    - other elements are kept as-is.
    
    For any other input types, returns the original value unchanged (caller is responsible for not logging secrets).
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
    Invoke func(*args) and handle specified exceptions with sanitized, structured logging.
    
    If any exception whose type is listed in `exceptions` is raised, this function logs a sanitized record
    containing the function name, sanitized positional arguments, and an optionally sanitized `context`.
    When an expected exception is caught the function either returns `fallback` (default) or re-raises
    the original exception if `reraise` is True.
    
    Parameters:
        func (Callable[..., Any]): The callable to invoke.
        *args (Any): Positional arguments forwarded to `func`.
        exceptions (Optional[Union[Type[BaseException], Tuple[Type[BaseException], ...]]]): Exception
            type or tuple of exception types to catch. If None, no exceptions are caught. Defaults to
            `Exception`.
        fallback (Any): Value returned when an expected exception is caught and `reraise` is False.
        reraise (bool): If True, re-raise the caught exception after logging; otherwise return `fallback`.
        context (Optional[Dict[str, Any]]): Optional context dictionary included in the log; when
            `sanitize_context_keys` is True and `context` is a dict, keys and values will be sanitized to
            avoid exposing secrets.
        sanitize_context_keys (bool): Whether to sanitize/redact potentially sensitive keys in `context`.
    
    Returns:
        Any: The result of `func(*args)` if no expected exception is raised, otherwise `fallback` (unless
        `reraise` is True).
    
    Raises:
        TypeError: If `exceptions` is not an exception type, a tuple of exception types, or None.
        Exception: Re-raises any caught exception when `reraise` is True (preserves the original exception).
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
    Return a decorator that wraps a callable with controlled exception handling and optional enriched context for logs.
    
    The returned decorator wraps the target function so that when it is called:
    - Exceptions matching `exceptions` are intercepted and handled by `call_with_handling`.
    - On a matched exception, the wrapper either returns `fallback` or re-raises depending on `reraise`.
    - If provided, `context_provider(*args, **kwargs)` is called to produce contextual information included in the log context; failures in the context provider are ignored and do not prevent the wrapped call.
    - If keyword arguments are present when the wrapped function is invoked, their keys are added to the log context under "kwargs_keys" (values are not included here; `call_with_handling` will sanitize values if needed).
    
    Parameters:
        exceptions: Exception type or tuple of exception types to catch; defaults to `Exception`.
        fallback: Value to return when a specified exception is caught and `reraise` is False.
        reraise: If True, re-raise caught exceptions after logging; otherwise suppress and return `fallback`.
        context_provider: Optional callable called as `context_provider(*args, **kwargs)` to supply extra context (should return a dict or any value). Exceptions raised by this callable are ignored.
    
    Returns:
        A decorator that can be applied to a function to provide the described safe call behavior.
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        """
        Wrap the given function so it is executed via call_with_handling with optional contextual enrichment.
        
        The returned wrapper:
        - Attempts to obtain additional context by calling `context_provider(*args, **kwargs)` if a provider was supplied; if the provider raises, the error is logged at DEBUG and execution proceeds without it.
        - Builds a combined context that merges the provider result (if any) — if the provider returns a non-dict value it is stored under the key `"context"` — and, if keyword arguments were passed, a `"kwargs_keys"` entry listing their keys.
        - Invokes `call_with_handling` to execute the original function with the configured `exceptions`, `fallback`, `reraise`, and `logger_to_use` behavior, ensuring arguments and context are sanitized in logs.
        
        Parameters:
            func: The callable to wrap.
        
        Returns:
            A callable with the same signature as `func` that applies the configured safe execution and logging behavior.
        """
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