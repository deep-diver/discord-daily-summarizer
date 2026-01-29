"""Audit logging system for security events."""

import json
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum
import threading


class AuditEventType(Enum):
    """Types of audit events."""
    SECURITY_ALERT = "security_alert"
    AUTHENTICATION_SUCCESS = "authentication_success"
    AUTHENTICATION_FAILURE = "authentication_failure"
    API_CALL = "api_call"
    CREDENTIAL_ACCESS = "credential_access"
    CREDENTIAL_ROTATION = "credential_rotation"
    INPUT_VALIDATION_FAILURE = "input_validation_failure"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    DATA_ACCESS = "data_access"
    DATA_MODIFICATION = "data_modification"
    ERROR = "error"
    CONFIG_CHANGE = "config_change"


class AuditSeverity(Enum):
    """Audit severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """Audit event data structure."""
    event_type: AuditEventType
    severity: AuditSeverity
    timestamp: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    resource: Optional[str] = None
    action: Optional[str] = None
    details: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    request_id: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None


class AuditLogger:
    """Audit logger for security events."""

    def __init__(self, log_file: str = "audit.log", max_size_mb: int = 100,
                 backup_count: int = 5, console_level: str = "INFO"):
        """Initialize audit logger.

        Args:
            log_file: Path to audit log file
            max_size_mb: Maximum log file size in MB
            backup_count: Number of backup files to keep
            console_level: Console logging level
        """
        self.log_file = Path(log_file)
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.backup_count = backup_count
        self._lock = threading.Lock()
        self._enabled = True

        # Create log directory if it doesn't exist
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        # Setup logger
        self.logger = logging.getLogger('audit_logger')
        self.logger.setLevel(logging.DEBUG)

        # Remove existing handlers
        self.logger.handlers.clear()

        # File handler with rotation
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(
            self.log_file,
            maxBytes=self.max_size_bytes,
            backupCount=self.backup_count
        )
        file_handler.setLevel(logging.INFO)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(getattr(logging, console_level.upper()))

        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)

        # Add handlers
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

    def log_event(self, event: AuditEvent) -> None:
        """Log an audit event.

        Args:
            event: AuditEvent to log
        """
        if not self._enabled:
            return

        with self._lock:
            try:
                # Convert event to JSON
                event_dict = asdict(event)
                event_json = json.dumps(event_dict, default=str)

                # Log based on severity
                if event.severity == AuditSeverity.CRITICAL:
                    self.logger.critical(event_json)
                elif event.severity == AuditSeverity.HIGH:
                    self.logger.error(event_json)
                elif event.severity == AuditSeverity.MEDIUM:
                    self.logger.warning(event_json)
                elif event.severity == AuditSeverity.LOW:
                    self.logger.info(event_json)
                else:
                    self.logger.info(event_json)

            except Exception as e:
                # Fallback logging if JSON fails
                self.logger.error(f"Failed to log audit event: {e}")
                self.logger.info(f"Raw event: {event}")

    def log_security_alert(self, message: str, severity: AuditSeverity = AuditSeverity.MEDIUM,
                          details: Optional[Dict[str, Any]] = None, **kwargs) -> None:
        """Log a security alert.

        Args:
            message: Alert message
            severity: Alert severity
            details: Additional details
            **kwargs: Additional event parameters
        """
        event = AuditEvent(
            event_type=AuditEventType.SECURITY_ALERT,
            severity=severity,
            timestamp=datetime.now().isoformat(),
            details={"message": message, **(details or {})},
            **kwargs
        )
        self.log_event(event)

    def log_authentication(self, success: bool, user_id: str,
                          ip_address: Optional[str] = None,
                          user_agent: Optional[str] = None,
                          session_id: Optional[str] = None) -> None:
        """Log authentication event.

        Args:
            success: Whether authentication was successful
            user_id: User ID
            ip_address: Client IP address
            user_agent: User agent string
            session_id: Session ID
        """
        event = AuditEvent(
            event_type=AuditEventType.AUTHENTICATION_SUCCESS if success else AuditEventType.AUTHENTICATION_FAILURE,
            severity=AuditSeverity.LOW if success else AuditSeverity.MEDIUM,
            timestamp=datetime.now().isoformat(),
            user_id=user_id,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
            success=success,
            error_message=None if success else "Authentication failed"
        )
        self.log_event(event)

    def log_api_call(self, endpoint: str, method: str, status_code: int,
                    user_id: Optional[str] = None, ip_address: Optional[str] = None,
                    request_id: Optional[str] = None, duration_ms: Optional[float] = None,
                    details: Optional[Dict[str, Any]] = None) -> None:
        """Log API call.

        Args:
            endpoint: API endpoint
            method: HTTP method
            status_code: HTTP status code
            user_id: User ID
            ip_address: Client IP address
            request_id: Request ID
            duration_ms: Request duration in milliseconds
            details: Additional details
        """
        event = AuditEvent(
            event_type=AuditEventType.API_CALL,
            severity=AuditSeverity.LOW,
            timestamp=datetime.now().isoformat(),
            user_id=user_id,
            ip_address=ip_address,
            request_id=request_id,
            action=f"{method} {endpoint}",
            details={
                "endpoint": endpoint,
                "method": method,
                "status_code": status_code,
                "duration_ms": duration_ms,
                **(details or {})
            }
        )
        self.log_event(event)

    def log_credential_access(self, credential_key: str, action: str,
                           user_id: Optional[str] = None,
                           ip_address: Optional[str] = None,
                           success: bool = True,
                           details: Optional[Dict[str, Any]] = None) -> None:
        """Log credential access event.

        Args:
            credential_key: Credential key
            action: Action performed (get, set, delete)
            user_id: User ID
            ip_address: Client IP address
            success: Whether operation was successful
            details: Additional details
        """
        event = AuditEvent(
            event_type=AuditEventType.CREDENTIAL_ACCESS,
            severity=AuditSeverity.HIGH,
            timestamp=datetime.now().isoformat(),
            user_id=user_id,
            ip_address=ip_address,
            resource=credential_key,
            action=action,
            success=success,
            details={
                "credential_key": credential_key,
                "action": action,
                **(details or {})
            }
        )
        self.log_event(event)

    def log_input_validation_failure(self, field: str, value: str,
                                   error: str, user_id: Optional[str] = None,
                                   ip_address: Optional[str] = None,
                                   request_id: Optional[str] = None) -> None:
        """Log input validation failure.

        Args:
            field: Field name
            value: Invalid value
            error: Error message
            user_id: User ID
            ip_address: Client IP address
            request_id: Request ID
        """
        event = AuditEvent(
            event_type=AuditEventType.INPUT_VALIDATION_FAILURE,
            severity=AuditSeverity.MEDIUM,
            timestamp=datetime.now().isoformat(),
            user_id=user_id,
            ip_address=ip_address,
            request_id=request_id,
            details={
                "field": field,
                "value": value,
                "error": error
            }
        )
        self.log_event(event)

    def log_rate_limit_exceeded(self, endpoint: str, identifier: str,
                               retry_after: float, user_id: Optional[str] = None,
                               ip_address: Optional[str] = None) -> None:
        """Log rate limit exceeded event.

        Args:
            endpoint: API endpoint
            identifier: Rate limit identifier
            retry_after: Seconds to wait before retry
            user_id: User ID
            ip_address: Client IP address
        """
        event = AuditEvent(
            event_type=AuditEventType.RATE_LIMIT_EXCEEDED,
            severity=AuditSeverity.LOW,
            timestamp=datetime.now().isoformat(),
            user_id=user_id,
            ip_address=ip_address,
            resource=endpoint,
            details={
                "endpoint": endpoint,
                "identifier": identifier,
                "retry_after": retry_after
            }
        )
        self.log_event(event)

    def log_data_access(self, resource_type: str, resource_id: str,
                       action: str, user_id: Optional[str] = None,
                       ip_address: Optional[str] = None,
                       request_id: Optional[str] = None,
                       details: Optional[Dict[str, Any]] = None) -> None:
        """Log data access event.

        Args:
            resource_type: Type of resource
            resource_id: Resource ID
            action: Action performed
            user_id: User ID
            ip_address: Client IP address
            request_id: Request ID
            details: Additional details
        """
        event = AuditEvent(
            event_type=AuditEventType.DATA_ACCESS,
            severity=AuditSeverity.LOW,
            timestamp=datetime.now().isoformat(),
            user_id=user_id,
            ip_address=ip_address,
            request_id=request_id,
            resource=f"{resource_type}:{resource_id}",
            action=action,
            details={
                "resource_type": resource_type,
                "resource_id": resource_id,
                "action": action,
                **(details or {})
            }
        )
        self.log_event(event)

    def log_data_modification(self, resource_type: str, resource_id: str,
                            action: str, user_id: Optional[str] = None,
                            ip_address: Optional[str] = None,
                            request_id: Optional[str] = None,
                            details: Optional[Dict[str, Any]] = None) -> None:
        """Log data modification event.

        Args:
            resource_type: Type of resource
            resource_id: Resource ID
            action: Action performed
            user_id: User ID
            ip_address: Client IP address
            request_id: Request ID
            details: Additional details
        """
        event = AuditEvent(
            event_type=AuditEventType.DATA_MODIFICATION,
            severity=AuditSeverity.MEDIUM,
            timestamp=datetime.now().isoformat(),
            user_id=user_id,
            ip_address=ip_address,
            request_id=request_id,
            resource=f"{resource_type}:{resource_id}",
            action=action,
            details={
                "resource_type": resource_type,
                "resource_id": resource_id,
                "action": action,
                **(details or {})
            }
        )
        self.log_event(event)

    def get_events(self, event_type: Optional[AuditEventType] = None,
                  start_time: Optional[datetime] = None,
                  end_time: Optional[datetime] = None,
                  limit: int = 100) -> List[Dict[str, Any]]:
        """Get audit events with filtering.

        Args:
            event_type: Filter by event type
            start_time: Filter by start time
            end_time: Filter by end time
            limit: Maximum number of events to return

        Returns:
            List of audit events
        """
        events = []
        try:
            with open(self.log_file, 'r') as f:
                for line in f:
                    try:
                        # Parse log line (assuming JSON format)
                        # This is a simplified parser - in production use a proper log parser
                        if " - audit_logger - " in line:
                            json_part = line.split(" - audit_logger - ")[1].strip()
                            if json_part.startswith('{'):
                                event_data = json.loads(json_part)
                                # Convert to dict
                                if isinstance(event_data, str):
                                    event_data = json.loads(event_data)

                                # Filter events
                                if event_type and event_data.get('event_type') != event_type.value:
                                    continue

                                if start_time and datetime.fromisoformat(event_data['timestamp']) < start_time:
                                    continue

                                if end_time and datetime.fromisoformat(event_data['timestamp']) > end_time:
                                    continue

                                events.append(event_data)

                                if len(events) >= limit:
                                    break
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue

        except FileNotFoundError:
            pass

        return events[:limit]

    def enable(self) -> None:
        """Enable audit logging."""
        self._enabled = True

    def disable(self) -> None:
        """Disable audit logging."""
        self._enabled = False

    def clear_logs(self) -> None:
        """Clear audit logs."""
        with self._lock:
            if self.log_file.exists():
                self.log_file.unlink()
            # Clear backup logs
            for i in range(self.backup_count):
                backup_file = self.log_file.with_suffix(f'.{i}')
                if backup_file.exists():
                    backup_file.unlink()