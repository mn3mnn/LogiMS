"""
Logging utilities for structured and consistent logging across the application.

All logging operations are wrapped in error handling to ensure that logging
failures do not affect application behavior.
"""
import logging
import time
import functools
from typing import Any, Callable
from django.conf import settings


# Fallback logger for logging errors
_fallback_logger = logging.getLogger('logims.logging_errors')


def _safe_log(func):
    """
    Decorator to make logging functions fail-safe.
    Catches any exceptions during logging and logs them to a fallback logger.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # Use fallback logger to report the logging error
            try:
                _fallback_logger.error(
                    f"Logging error in {func.__name__}: {str(e)}",
                    exc_info=False  # Avoid recursion
                )
            except Exception:
                # If even the fallback fails, silently pass to avoid breaking the app
                pass
    return wrapper


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name.

    Args:
        name: Name of the logger (usually __name__)

    Returns:
        Logger instance
    """
    try:
        return logging.getLogger(name)
    except Exception:
        # Return fallback logger if getting logger fails
        return _fallback_logger


def log_execution_time(logger: logging.Logger = None):
    """
    Decorator to log the execution time of a function.
    Logging errors will not affect function execution.

    Usage:
        @log_execution_time()
        def my_function():
            pass

    Args:
        logger: Logger instance to use. If None, will use the module's logger
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal logger
            if logger is None:
                try:
                    logger = logging.getLogger(func.__module__)
                except Exception:
                    logger = _fallback_logger

            start_time = time.time()
            func_name = func.__qualname__

            # Log start (safe)
            try:
                logger.info(f"Starting execution: {func_name}")
            except Exception:
                pass

            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                # Log completion (safe)
                try:
                    logger.info(
                        f"Completed execution: {func_name} | "
                        f"Duration: {execution_time:.2f}s"
                    )
                except Exception:
                    pass
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                # Log error (safe)
                try:
                    logger.error(
                        f"Failed execution: {func_name} | "
                        f"Duration: {execution_time:.2f}s | "
                        f"Error: {str(e)}",
                        exc_info=True
                    )
                except Exception:
                    pass
                raise

        return wrapper
    return decorator


def log_db_query_count(logger: logging.Logger = None):
    """
    Decorator to log the number of database queries executed by a function.
    Useful for identifying N+1 query problems.
    Logging errors will not affect function execution.

    Usage:
        @log_db_query_count()
        def my_view(request):
            pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            nonlocal logger
            if logger is None:
                try:
                    logger = logging.getLogger(func.__module__)
                except Exception:
                    logger = _fallback_logger

            try:
                from django.db import connection, reset_queries
                from django.conf import settings

                # Enable query logging
                old_debug = settings.DEBUG
                settings.DEBUG = True
                reset_queries()

                try:
                    result = func(*args, **kwargs)
                    query_count = len(connection.queries)

                    # Log query count (safe)
                    try:
                        if query_count > 50:
                            logger.warning(
                                f"High query count in {func.__qualname__}: {query_count} queries"
                            )
                        else:
                            logger.info(
                                f"Query count for {func.__qualname__}: {query_count} queries"
                            )
                    except Exception:
                        pass

                    return result
                finally:
                    settings.DEBUG = old_debug
            except Exception:
                # If DB query logging fails, just run the function normally
                return func(*args, **kwargs)

        return wrapper
    return decorator


class ContextLogger:
    """
    Context manager for logging with additional context information.
    Logging errors will not affect the context execution.

    Usage:
        with ContextLogger(logger, "Processing file", file_id=123):
            # do work
            pass
    """

    def __init__(self, logger: logging.Logger, operation: str, **context):
        self.logger = logger or _fallback_logger
        self.operation = operation
        self.context = context
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()
        # Safe logging on enter
        try:
            context_str = " | ".join(f"{k}={v}" for k, v in self.context.items())
            self.logger.info(f"Starting: {self.operation} | {context_str}")
        except Exception:
            pass
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Safe logging on exit
        try:
            duration = time.time() - self.start_time
            context_str = " | ".join(f"{k}={v}" for k, v in self.context.items())

            if exc_type is None:
                self.logger.info(
                    f"Completed: {self.operation} | "
                    f"Duration: {duration:.2f}s | {context_str}"
                )
            else:
                self.logger.error(
                    f"Failed: {self.operation} | "
                    f"Duration: {duration:.2f}s | {context_str} | "
                    f"Error: {exc_val}",
                    exc_info=True
                )
        except Exception:
            pass

        return False  # Don't suppress exceptions


@_safe_log
def log_user_action(action: str, user, **details):
    """
    Log a user action with consistent formatting.
    Fails silently if logging error occurs.

    Args:
        action: Description of the action
        user: User instance or username
        **details: Additional details to log
    """
    logger = logging.getLogger("logims.users")

    username = getattr(user, "username", str(user))
    user_id = getattr(user, "id", None)

    details_str = " | ".join(f"{k}={v}" for k, v in details.items())
    log_msg = f"User Action: {action} | User: {username} (ID: {user_id})"

    if details_str:
        log_msg += f" | {details_str}"

    logger.info(log_msg)


@_safe_log
def log_api_call(view_name: str, method: str, user, **details):
    """
    Log an API call with consistent formatting.
    Fails silently if logging error occurs.

    Args:
        view_name: Name of the view or endpoint
        method: HTTP method
        user: User instance
        **details: Additional details (status_code, query_params, etc.)
    """
    logger = logging.getLogger("logims")

    username = getattr(user, "username", "anonymous") if user else "anonymous"
    user_id = getattr(user, "id", None) if user else None

    details_str = " | ".join(f"{k}={v}" for k, v in details.items())
    log_msg = (
        f"API Call: {method} {view_name} | "
        f"User: {username} (ID: {user_id})"
    )

    if details_str:
        log_msg += f" | {details_str}"

    logger.info(log_msg)


@_safe_log
def log_model_change(action: str, model_name: str, instance_id: Any, user, **details):
    """
    Log a model change (create, update, delete) with consistent formatting.
    Fails silently if logging error occurs.

    Args:
        action: 'create', 'update', or 'delete'
        model_name: Name of the model
        instance_id: ID of the instance
        user: User who made the change
        **details: Additional details about the change
    """
    logger = logging.getLogger(f"logims.models.{model_name.lower()}")

    username = getattr(user, "username", "system") if user else "system"
    user_id = getattr(user, "id", None) if user else None

    details_str = " | ".join(f"{k}={v}" for k, v in details.items())
    log_msg = (
        f"Model {action.upper()}: {model_name} | "
        f"ID: {instance_id} | "
        f"User: {username} (ID: {user_id})"
    )

    if details_str:
        log_msg += f" | {details_str}"

    logger.info(log_msg)


@_safe_log
def log_error(error: Exception, context: str = None, **details):
    """
    Log an error with context and details.
    Fails silently if logging error occurs.

    Args:
        error: Exception instance
        context: Context description
        **details: Additional details
    """
    logger = logging.getLogger("logims.errors")

    details_str = " | ".join(f"{k}={v}" for k, v in details.items())
    log_msg = f"Error: {type(error).__name__}: {str(error)}"

    if context:
        log_msg = f"{context} | {log_msg}"

    if details_str:
        log_msg += f" | {details_str}"

    logger.error(log_msg, exc_info=True)

