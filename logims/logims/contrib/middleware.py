"""
Custom middleware for logging requests and responses.

All logging operations are wrapped in error handling to ensure that
middleware failures do not affect request processing.
"""
import logging
import time
import json
from django.utils.deprecation import MiddlewareMixin
from django.urls import resolve


logger = logging.getLogger("logims.requests")
_fallback_logger = logging.getLogger("logims.middleware_errors")


class RequestLoggingMiddleware(MiddlewareMixin):
    """
    Middleware to log all incoming requests and outgoing responses.
    Tracks request duration, user, status code, and other metadata.

    Logging errors will not affect request processing.
    """

    def process_request(self, request):
        """Log the incoming request and store start time."""
        # Always set start time, even if logging fails
        request._start_time = time.time()

        # Safe logging
        try:
            # Get user info
            user = getattr(request, 'user', None)
            username = getattr(user, 'username', 'anonymous') if user else 'anonymous'
            user_id = getattr(user, 'id', None) if user else None

            # Get request details
            method = request.method
            path = request.path
            query_params = dict(request.GET) if request.GET else {}

            # Get client IP
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                ip = x_forwarded_for.split(',')[0]
            else:
                ip = request.META.get('REMOTE_ADDR')

            # Try to get view name
            try:
                resolved = resolve(request.path_info)
                view_name = f"{resolved.view_name}"
            except Exception:
                view_name = "unknown"

            log_data = {
                "method": method,
                "path": path,
                "view": view_name,
                "user": username,
                "user_id": user_id,
                "ip": ip,
            }

            if query_params:
                log_data["query_params"] = query_params

            log_msg = " | ".join(f"{k}={v}" for k, v in log_data.items())
            logger.info(f"Incoming Request | {log_msg}")
        except Exception as e:
            # Log to fallback logger, but don't break request processing
            try:
                _fallback_logger.error(f"Error logging request: {str(e)}", exc_info=False)
            except Exception:
                pass

    def process_response(self, request, response):
        """Log the outgoing response with duration."""
        # Safe logging - don't break response processing
        try:
            # Calculate request duration
            if hasattr(request, '_start_time'):
                duration = time.time() - request._start_time
            else:
                duration = 0

            # Get user info
            user = getattr(request, 'user', None)
            username = getattr(user, 'username', 'anonymous') if user else 'anonymous'
            user_id = getattr(user, 'id', None) if user else None

            # Get view name
            try:
                resolved = resolve(request.path_info)
                view_name = f"{resolved.view_name}"
            except Exception:
                view_name = "unknown"

            log_data = {
                "method": request.method,
                "path": request.path,
                "view": view_name,
                "status": response.status_code,
                "duration": f"{duration:.3f}s",
                "user": username,
                "user_id": user_id,
            }

            log_msg = " | ".join(f"{k}={v}" for k, v in log_data.items())

            # Log at different levels based on status code
            if response.status_code >= 500:
                logger.error(f"Response (Server Error) | {log_msg}")
            elif response.status_code >= 400:
                logger.warning(f"Response (Client Error) | {log_msg}")
            else:
                logger.info(f"Response | {log_msg}")

            # Log slow requests
            if duration > 5.0:
                logger.warning(
                    f"Slow Request Detected | {log_msg} | "
                    f"Threshold exceeded: {duration:.3f}s > 5.0s"
                )
        except Exception as e:
            # Log to fallback logger, but don't break response
            try:
                _fallback_logger.error(f"Error logging response: {str(e)}", exc_info=False)
            except Exception:
                pass

        return response

    def process_exception(self, request, exception):
        """Log any unhandled exceptions."""
        # Safe logging - don't interfere with exception handling
        try:
            duration = time.time() - getattr(request, '_start_time', time.time())

            user = getattr(request, 'user', None)
            username = getattr(user, 'username', 'anonymous') if user else 'anonymous'
            user_id = getattr(user, 'id', None) if user else None

            try:
                resolved = resolve(request.path_info)
                view_name = f"{resolved.view_name}"
            except Exception:
                view_name = "unknown"

            log_data = {
                "method": request.method,
                "path": request.path,
                "view": view_name,
                "duration": f"{duration:.3f}s",
                "user": username,
                "user_id": user_id,
                "exception": type(exception).__name__,
                "message": str(exception),
            }

            log_msg = " | ".join(f"{k}={v}" for k, v in log_data.items())
            logger.error(f"Request Exception | {log_msg}", exc_info=True)
        except Exception as e:
            # Log to fallback logger, but don't break exception handling
            try:
                _fallback_logger.error(f"Error logging exception: {str(e)}", exc_info=False)
            except Exception:
                pass


class PerformanceLoggingMiddleware(MiddlewareMixin):
    """
    Middleware to log performance metrics for database queries.
    Only active when DEBUG=True to avoid overhead in production.

    Logging errors will not affect request processing.
    """

    def process_request(self, request):
        """Store initial state."""
        # Always set these, even if logging fails
        request._start_time = time.time()

        try:
            from django.db import connection
            request._queries_count_start = len(connection.queries)
        except Exception:
            request._queries_count_start = 0

    def process_response(self, request, response):
        """Log performance metrics."""
        # Safe logging - don't break response processing
        try:
            from django.conf import settings
            from django.db import connection

            # Only log in debug mode
            if not settings.DEBUG:
                return response

            duration = time.time() - getattr(request, '_start_time', time.time())
            queries_count_start = getattr(request, '_queries_count_start', 0)
            queries_count = len(connection.queries) - queries_count_start

            # Only log if there were queries or it took significant time
            if queries_count > 0 or duration > 1.0:
                try:
                    resolved = resolve(request.path_info)
                    view_name = f"{resolved.view_name}"
                except Exception:
                    view_name = "unknown"

                log_data = {
                    "view": view_name,
                    "path": request.path,
                    "method": request.method,
                    "queries": queries_count,
                    "duration": f"{duration:.3f}s",
                }

                # Log slow queries
                slow_queries = [
                    q for q in connection.queries[queries_count_start:]
                    if float(q.get('time', 0)) > 0.1
                ]

                if slow_queries:
                    log_data["slow_queries"] = len(slow_queries)

                log_msg = " | ".join(f"{k}={v}" for k, v in log_data.items())

                if queries_count > 50 or duration > 2.0 or slow_queries:
                    logger.warning(f"Performance Issue | {log_msg}")
                else:
                    logger.debug(f"Performance Metrics | {log_msg}")
        except Exception as e:
            # Log to fallback logger, but don't break response
            try:
                _fallback_logger.error(f"Error logging performance metrics: {str(e)}", exc_info=False)
            except Exception:
                pass

        return response

