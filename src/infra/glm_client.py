"""GLM4.7 client for Z.ai API integration."""

import json
import os
import time
from typing import Any

import httpx
from src.core.events import EventBus, Event, EventType
from src.security import (
    validate_api_key_format,
    validate_message_content,
    sanitize_input,
    APIRateLimiter,
    AuditLogger,
    AuditEventType,
    AuditSeverity,
    RateLimitConfigLimiter,
)


class GLMClientError(Exception):
    """GLM client error."""

    pass


class GLMClient:
    """Client for Z.ai GLM4.7 API.

    Features:
    - Retries with exponential backoff
    - Mock mode for testing
    - Event publishing for observability
    - Request timing logging
    - Input validation
    - Rate limiting
    - Audit logging
    """

    def __init__(self, event_bus: EventBus | None = None, api_key: str | None = None,
                 mock: bool = False, audit_logger: AuditLogger | None = None) -> None:
        """Initialize GLM client.

        Args:
            event_bus: Optional event bus for publishing events
            api_key: Optional API key (default: read from GLM_API_KEY env var)
            mock: Enable mock mode for testing
            audit_logger: Optional audit logger for security events
        """
        self._event_bus = event_bus or EventBus()
        self._mock_mode = mock
        self._mock_responses: dict[str, Any] = {}
        self._audit_logger = audit_logger or AuditLogger()

        # Get API key from parameter or environment (skip if in mock mode)
        if mock:
            self._api_key = "mock-key"
        elif api_key:
            self._api_key = validate_api_key_format(api_key)
        else:
            # Read from environment variable
            env_api_key = os.environ.get("GLM_API_KEY")
            if env_api_key:
                self._api_key = validate_api_key_format(env_api_key)
            else:
                raise GLMClientError("API key not found. Set GLM_API_KEY environment variable or pass api_key parameter.")

        self._base_url = "https://open.bigmodel.cn/api/paas/v4/chat/completions"

        # Initialize rate limiter with higher limits for batch processing
        rate_limit_config = RateLimitConfigLimiter(
            requests_per_minute=100,
            requests_per_hour=1000,
            requests_per_day=10000,
            burst_limit=100,  # Increased from 10 to 100 for batch processing
        )
        self._rate_limiter = APIRateLimiter(rate_limit_config)

        # Log initialization
        self._audit_logger.log_data_modification(
            "config", "glm_client", "initialize",
            details={"mock_mode": mock, "base_url": self._base_url}
        )

    def enable_mock_mode(self) -> None:
        """Enable mock mode for testing."""
        self._mock_mode = True

    def disable_mock_mode(self) -> None:
        """Disable mock mode."""
        self._mock_mode = False

    def set_mock_response(self, prompt_key: str, response: Any) -> None:
        """Set a mock response for a specific prompt key.

        Args:
            prompt_key: Key to identify the prompt (e.g., first 100 chars)
            response: Mock response to return
        """
        self._mock_responses[prompt_key] = response

    def chat(
        self,
        messages: list[dict[str, str]],
        model: str = "glm-4.7",
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> str:
        """Send a chat completion request to GLM4.7.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name (default: glm-4.7)
            temperature: Sampling temperature (0.0-1.0, default: 0.2)
            max_tokens: Maximum tokens to generate (default: 4096)

        Returns:
            Generated text response

        Raises:
            GLMClientError: If the request fails after retries
        """
        # Validate inputs
        if not messages:
            raise GLMClientError("Messages list cannot be empty")

        # Validate message structure
        for i, msg in enumerate(messages):
            if not isinstance(msg, dict):
                raise GLMClientError(f"Message {i} must be a dictionary")
            if 'role' not in msg or 'content' not in msg:
                raise GLMClientError(f"Message {i} must contain 'role' and 'content' keys")
            if msg['role'] not in ['system', 'user', 'assistant']:
                raise GLMClientError(f"Message {i} has invalid role: {msg['role']}")
            msg['content'] = validate_message_content(sanitize_input(msg['content']))

        # Validate model
        if not isinstance(model, str):
            raise GLMClientError("Model must be a string")
        if model not in ['glm-4.7', 'glm-4', 'glm-4-flashx', 'glm-4-flash', 'glm-4.7-flash']:
            self._audit_logger.log_security_alert(
                f"Unknown model specified: {model}",
                AuditSeverity.MEDIUM,
                details={"model": model}
            )

        # Validate temperature
        if not isinstance(temperature, (int, float)):
            raise GLMClientError("Temperature must be a number")
        if temperature < 0.0 or temperature > 1.0:
            raise GLMClientError("Temperature must be between 0.0 and 1.0")

        # Validate max_tokens
        if not isinstance(max_tokens, int):
            raise GLMClientError("max_tokens must be an integer")
        if max_tokens < 1 or max_tokens > 8192:
            raise GLMClientError("max_tokens must be between 1 and 8192")

        # Apply rate limiting
        if not self._mock_mode:
            try:
                self._rate_limiter.record_api_call("chat/completions")
            except Exception as e:
                self._audit_logger.log_rate_limit_exceeded(
                    "chat/completions", "client", 1.0
                )
                raise GLMClientError(f"Rate limit exceeded: {e}")

        if self._mock_mode:
            return self._mock_chat(messages)

        prompt_key = _get_prompt_key(messages)
        start_time = time.time()

        try:
            # Log API call start
            self._audit_logger.log_api_call(
                "chat/completions", "POST", 200,
                details={
                    "model": model,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "messages_count": len(messages)
                }
            )

            response = self._chat_with_retry(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            elapsed = time.time() - start_time

            # Publish success event
            self._event_bus.publish(
                Event(
                    type=EventType.STATE_GENERATED,
                    data={
                        "model": model,
                        "elapsed_seconds": round(elapsed, 2),
                        "prompt_length": len(str(messages)),
                    },
                )
            )

            # Log successful API call
            self._audit_logger.log_api_call(
                "chat/completions", "POST", 200,
                duration_ms=elapsed * 1000,
                details={"model": model, "response_length": len(response)}
            )

            return response

        except Exception as e:
            elapsed = time.time() - start_time

            # Publish error event
            self._event_bus.publish(
                Event(
                    type=EventType.ERROR,
                    data={
                        "error_message": str(e),
                        "context": "glm_client_chat",
                        "elapsed_seconds": round(elapsed, 2),
                    },
                )
            )

            # Log error
            self._audit_logger.log_security_alert(
                f"GLM API request failed: {e}",
                AuditSeverity.MEDIUM,
                details={"model": model, "elapsed_seconds": elapsed}
            )

            raise GLMClientError(f"GLM API request failed: {e}") from e

    def _chat_with_retry(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
        max_retries: int = 4,
    ) -> str:
        """Send chat request with retries and exponential backoff.

        Args:
            messages: Chat messages
            model: Model name
            temperature: Temperature
            max_tokens: Max tokens
            max_retries: Maximum retry attempts (default: 4)

        Returns:
            Response text

        Raises:
            GLMClientError: If all retries fail
        """
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                return self._single_request(messages, model, temperature, max_tokens)

            except httpx.HTTPStatusError as e:
                last_error = e
                status_code = e.response.status_code

                if attempt < max_retries:
                    if status_code == 429:
                        # Rate limit error - use much longer backoff (2-5 minutes)
                        backoff = 120 + (attempt * 60)  # 120, 180, 240, 300 seconds (2-5 minutes)
                        self._audit_logger.log_security_alert(
                            f"Rate limit hit, backing off for {backoff}s ({backoff//60}m {backoff%60}s)",
                            AuditSeverity.LOW,
                            details={"attempt": attempt, "backoff": backoff}
                        )
                        time.sleep(backoff)
                    elif status_code >= 500:
                        # Server error - retry with exponential backoff
                        backoff = 2**attempt
                        time.sleep(backoff)
                    else:
                        # Other client errors - don't retry
                        break
                else:
                    break

            except (httpx.RequestError, httpx.TimeoutException) as e:
                last_error = e
                if attempt < max_retries:
                    backoff = 2**attempt
                    time.sleep(backoff)
                else:
                    break

        raise GLMClientError(f"Request failed after {max_retries + 1} attempts: {last_error}")

    def _single_request(
        self,
        messages: list[dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        """Send a single chat request.

        Args:
            messages: Chat messages
            model: Model name
            temperature: Temperature
            max_tokens: Max tokens

        Returns:
            Response text

        Raises:
            httpx.HTTPStatusError: On HTTP errors
            httpx.RequestError: On request errors
        """
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        with httpx.Client(timeout=60.0) as client:
            response = client.post(self._base_url, headers=headers, json=payload)
            response.raise_for_status()

            data = response.json()
            return data["choices"][0]["message"]["content"]

    def _mock_chat(self, messages: list[dict[str, str]]) -> str:
        """Return mock response for testing.

        Args:
            messages: Chat messages

        Returns:
            Mock response
        """
        prompt_key = _get_prompt_key(messages)

        if prompt_key in self._mock_responses:
            return self._mock_responses[prompt_key]

        # Default mock responses based on prompt content
        content = messages[-1]["content"].lower()

        if "daily channel state" in content or "analyze the following discord messages" in content:
            # Extract channel_name and date from prompt if present
            channel_name = "test-channel"
            date = "2026-01-17"

            for msg in messages:
                if "channel #" in msg["content"].lower():
                    # Try to extract channel name
                    parts = msg["content"].split("#")
                    if len(parts) > 1:
                        channel_name = parts[1].split()[0].strip("\"'")

            return json.dumps(
                {
                    "channel_name": channel_name,
                    "date": date,
                    "topics": ["Test topic 1", "Test topic 2"],
                    "progress": {
                        "started": ["Task A"],
                        "continued": [],
                        "finished": [],
                        "blocked": [],
                    },
                    "artifacts": {
                        "links": ["https://example.com"],
                        "repos": [],
                        "docs": [],
                    },
                    "questions": [],
                    "help_requests": [],
                    "next_steps": ["Continue testing"],
                }
            )

        elif "daily channel delta" in content:
            return json.dumps(
                {
                    "channel_name": "test-channel",
                    "date": "2026-01-17",
                    "compared_to": "2026-01-16",
                    "new_topics": ["New topic"],
                    "resolved_topics": [],
                    "progress_changes": {
                        "started_now": [],
                        "finished_now": ["Task A"],
                        "new_blockers": [],
                        "resolved_blockers": [],
                    },
                    "new_links": ["https://new-example.com"],
                    "new_help_requests": [],
                }
            )

        else:
            # Return JSON for any request to avoid parsing errors
            return json.dumps(
                {
                    "response": "Mock response for general chat",
                    "status": "ok"
                }
            )


def _get_prompt_key(messages: list[dict[str, str]]) -> str:
    """Generate a key for identifying prompts in mock mode.

    Args:
        messages: Chat messages

    Returns:
        Prompt key (first 100 chars of last message)
    """
    if not messages:
        return "empty"
    content = messages[-1].get("content", "")
    return sanitize_input(content)[:100]
