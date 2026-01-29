"""Rate limiting implementation for API calls."""

import time
import threading
from collections import defaultdict, deque
from typing import Dict, Optional, Any
from dataclasses import dataclass
from enum import Enum


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    requests_per_day: int = 10000
    burst_limit: int = 10


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""
    def __init__(self, retry_after: float):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Try again in {retry_after:.1f} seconds")


class RateLimiter:
    """Rate limiter implementation with sliding window."""

    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.config = config or RateLimitConfig()
        self._lock = threading.Lock()
        self._requests: Dict[str, deque] = defaultdict(deque)

    def check_rate_limit(self, identifier: str) -> bool:
        """Check if request is allowed."""
        with self._lock:
            now = time.time()
            request_times = self._requests[identifier]

            # Remove old requests
            window_start = now - 60  # 1 minute window
            while request_times and request_times[0] < window_start:
                request_times.popleft()

            # Check minute limit
            if len(request_times) >= self.config.requests_per_minute:
                return False

            return True

    def check_hourly_limit(self, identifier: str) -> bool:
        """Check hourly rate limit."""
        with self._lock:
            now = time.time()
            request_times = self._requests[identifier]

            # Remove old requests
            window_start = now - 3600  # 1 hour window
            while request_times and request_times[0] < window_start:
                request_times.popleft()

            # Check hour limit
            if len(request_times) >= self.config.requests_per_hour:
                return False

            return True

    def check_daily_limit(self, identifier: str) -> bool:
        """Check daily rate limit."""
        with self._lock:
            now = time.time()
            request_times = self._requests[identifier]

            # Remove old requests
            window_start = now - 86400  # 24 hour window
            while request_times and request_times[0] < window_start:
                request_times.popleft()

            # Check day limit
            if len(request_times) >= self.config.requests_per_day:
                return False

            return True

    def check_burst_limit(self, identifier: str) -> bool:
        """Check burst limit."""
        with self._lock:
            request_times = self._requests[identifier]

            # Check if burst limit would be exceeded
            if len(request_times) >= self.config.burst_limit:
                return False

            return True

    def record_request(self, identifier: str) -> None:
        """Record a request."""
        with self._lock:
            now = time.time()
            self._requests[identifier].append(now)

    def wait_if_needed(self, identifier: str) -> float:
        """Wait if rate limit is exceeded, return retry after time."""
        now = time.time()

        # Check all limits
        if not self.check_burst_limit(identifier):
            raise RateLimitExceeded(1.0)

        if not self.check_rate_limit(identifier):
            # Calculate when the oldest request will expire
            request_times = self._requests[identifier]
            if request_times:
                retry_after = 60 - (now - request_times[0])
                raise RateLimitExceeded(max(0, retry_after))

        if not self.check_hourly_limit(identifier):
            retry_after = 3600 - (now - request_times[0] if request_times else 0)
            raise RateLimitExceeded(max(0, retry_after))

        if not self.check_daily_limit(identifier):
            retry_after = 86400 - (now - request_times[0] if request_times else 0)
            raise RateLimitExceeded(max(0, retry_after))

        return 0.0

    def record_and_wait(self, identifier: str) -> None:
        """Record request and wait if needed."""
        retry_after = self.wait_if_needed(identifier)
        if retry_after > 0:
            time.sleep(retry_after)
        self.record_request(identifier)


class APIRateLimiter:
    """Rate limiter specifically for API calls."""

    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.limiter = RateLimiter(config)

    def check_api_call(self, endpoint: str, identifier: str = "default") -> bool:
        """Check if API call is allowed."""
        # Different limits for different endpoints
        endpoint_key = f"{endpoint}:{identifier}"

        # Check burst limit first
        if not self.limiter.check_burst_limit(endpoint_key):
            return False

        # API-specific limits
        if "chat/completions" in endpoint:
            return self.limiter.check_rate_limit(endpoint_key)
        elif "messages" in endpoint:
            return self.limiter.check_hourly_limit(endpoint_key)
        else:
            return self.limiter.check_rate_limit(endpoint_key)

    def record_api_call(self, endpoint: str, identifier: str = "default") -> None:
        """Record API call and apply rate limiting."""
        endpoint_key = f"{endpoint}:{identifier}"
        self.limiter.record_and_wait(endpoint_key)

    def get_remaining_requests(self, endpoint: str, identifier: str = "default") -> Dict[str, int]:
        """Get remaining requests for different time windows."""
        endpoint_key = f"{endpoint}:{identifier}"
        now = time.time()
        request_times = self.limiter._requests[endpoint_key]

        # Count requests in each window
        minute_requests = sum(1 for t in request_times if t >= now - 60)
        hour_requests = sum(1 for t in request_times if t >= now - 3600)
        day_requests = sum(1 for t in request_times if t >= now - 86400)

        return {
            "per_minute": self.limiter.config.requests_per_minute - minute_requests,
            "per_hour": self.limiter.config.requests_per_hour - hour_requests,
            "per_day": self.limiter.config.requests_per_day - day_requests,
        }