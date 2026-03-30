"""Webhook notification module for report generation events.

Provides POST-based webhook delivery with retry logic,
signature verification, and configurable endpoints.

For ST-NS-023-T2: Report Delivery & Dashboard Integration
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import os
import time
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


class WebhookNotifier:
    """Webhook notification handler with retry and signature support.

    Features:
    - POST delivery to configured webhook URLs
    - Retry logic with exponential backoff
    - HMAC signature verification for security
    - Configurable timeout and batch delivery

    Attributes:
        webhook_url: Primary webhook URL
        secret_key: Secret key for HMAC signature
        timeout: Request timeout in seconds
        max_retries: Maximum retry attempts
    """

    def __init__(
        self,
        webhook_url: str | None = None,
        secret_key: str | None = None,
        timeout: int = 30,
        max_retries: int = 3,
    ) -> None:
        """Initialize webhook notifier.

        Args:
            webhook_url: Webhook endpoint URL
            secret_key: Secret key for HMAC signature verification
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
        """
        self.webhook_url = webhook_url or os.getenv("WEBHOOK_URL", "")
        self.secret_key = secret_key or os.getenv("WEBHOOK_SECRET", "")
        self.timeout = timeout
        self.max_retries = max_retries

    @property
    def is_configured(self) -> bool:
        """Check if webhook URL is configured.

        Returns:
            True if webhook_url is set
        """
        return bool(self.webhook_url)

    def generate_signature(self, payload: str, timestamp: int) -> str:
        """Generate HMAC signature for payload.

        Args:
            payload: JSON payload string
            timestamp: Unix timestamp

        Returns:
            Hexadecimal signature string
        """
        if not self.secret_key:
            return ""

        message = f"{timestamp}.{payload}"
        signature = hmac.new(
            self.secret_key.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()
        return signature

    def verify_signature(
        self,
        payload: str,
        timestamp: int,
        signature: str,
    ) -> bool:
        """Verify HMAC signature from webhook response.

        Args:
            payload: Original payload string
            timestamp: Unix timestamp from request
            signature: Signature to verify

        Returns:
            True if signature is valid
        """
        if not self.secret_key:
            return True

        expected = self.generate_signature(payload, timestamp)
        return hmac.compare_digest(expected, signature)

    async def send_webhook(
        self,
        payload: dict[str, Any],
        webhook_url: str | None = None,
        wait_for_response: bool = True,
    ) -> dict[str, Any]:
        """Send webhook POST request.

        Args:
            payload: Data to send
            webhook_url: Optional override webhook URL
            wait_for_response: Whether to wait for and return response

        Returns:
            Dictionary with status and optional response data
        """
        url = webhook_url or self.webhook_url

        if not url:
            logger.warning("Webhook URL not configured, logging payload")
            logger.debug(f"Webhook payload: {payload}")
            return {"success": True, "skipped": True, "reason": "not_configured"}

        # Prepare request
        import json

        json_payload = json.dumps(payload)
        timestamp = int(time.time())
        signature = self.generate_signature(json_payload, timestamp)

        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Timestamp": str(timestamp),
            "X-Webhook-Signature": signature,
        }

        # Send with retries
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url,
                        data=json_payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=self.timeout),
                    ) as response:
                        if response.status == 200:
                            if wait_for_response:
                                response_data = await response.json()
                                return {
                                    "success": True,
                                    "status": response.status,
                                    "response": response_data,
                                }
                            return {"success": True, "status": response.status}

                        logger.warning(
                            f"Webhook returned status {response.status}, attempt {attempt + 1}/{self.max_retries}"
                        )
                        last_error = Exception(f"HTTP {response.status}")

            except TimeoutError:
                logger.warning(
                    f"Webhook timeout, attempt {attempt + 1}/{self.max_retries}"
                )
                last_error = Exception("Request timeout")
            except Exception as e:
                logger.warning(
                    f"Webhook error: {e}, attempt {attempt + 1}/{self.max_retries}"
                )
                last_error = e

            # Exponential backoff before retry
            if attempt < self.max_retries - 1:
                delay = 2**attempt
                await asyncio.sleep(delay)

        return {
            "success": False,
            "error": str(last_error),
            "attempts": self.max_retries,
        }

    async def notify_report_generated(
        self,
        report_type: str,
        report_id: str,
        report_data: dict[str, Any],
        recipients: list[str] | None = None,
    ) -> dict[str, Any]:
        """Send report generation notification.

        Args:
            report_type: Type of report (e.g., "daily", "weekly")
            report_id: Unique report identifier
            report_data: Report content data
            recipients: Optional list of notification recipients

        Returns:
            Notification result
        """
        payload = {
            "event": "report.generated",
            "report_type": report_type,
            "report_id": report_id,
            "timestamp": int(time.time()),
            "data": report_data,
        }

        if recipients:
            payload["recipients"] = recipients

        return await self.send_webhook(payload)

    async def notify_report_delivered(
        self,
        report_id: str,
        delivery_method: str,
        recipients: list[str],
        success: bool,
        error: str | None = None,
    ) -> dict[str, Any]:
        """Send report delivery notification.

        Args:
            report_id: Unique report identifier
            delivery_method: Delivery method used (e.g., "email", "webhook")
            recipients: List of delivery recipients
            success: Whether delivery was successful
            error: Optional error message

        Returns:
            Notification result
        """
        payload = {
            "event": "report.delivered",
            "report_id": report_id,
            "delivery_method": delivery_method,
            "recipients": recipients,
            "success": success,
            "timestamp": int(time.time()),
        }

        if error:
            payload["error"] = error

        return await self.send_webhook(payload)

    async def notify_anomaly_detected(
        self,
        anomaly_type: str,
        severity: str,
        message: str,
        metrics: dict[str, Any],
    ) -> dict[str, Any]:
        """Send anomaly detection notification.

        Args:
            anomaly_type: Type of anomaly detected
            severity: Anomaly severity (info, warning, critical)
            message: Human-readable message
            metrics: Anomaly metrics data

        Returns:
            Notification result
        """
        payload = {
            "event": "anomaly.detected",
            "anomaly_type": anomaly_type,
            "severity": severity,
            "message": message,
            "metrics": metrics,
            "timestamp": int(time.time()),
        }

        return await self.send_webhook(payload)

    async def batch_notify(
        self,
        notifications: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Send batch of webhook notifications concurrently.

        Args:
            notifications: List of notification specifications

        Returns:
            List of notification results
        """
        tasks = []
        for notif in notifications:
            if notif["event"] == "report.generated":
                task = self.notify_report_generated(
                    report_type=notif["report_type"],
                    report_id=notif["report_id"],
                    report_data=notif["report_data"],
                    recipients=notif.get("recipients"),
                )
            elif notif["event"] == "report.delivered":
                task = self.notify_report_delivered(
                    report_id=notif["report_id"],
                    delivery_method=notif["delivery_method"],
                    recipients=notif["recipients"],
                    success=notif["success"],
                    error=notif.get("error"),
                )
            elif notif["event"] == "anomaly.detected":
                task = self.notify_anomaly_detected(
                    anomaly_type=notif["anomaly_type"],
                    severity=notif["severity"],
                    message=notif["message"],
                    metrics=notif["metrics"],
                )
            else:
                task = self.send_webhook(notif)
            tasks.append(task)

        return await asyncio.gather(*tasks)
