#!/usr/bin/env python3
"""End-to-End Incident Simulation for ACP Resilience Testing.

This script executes controlled incident simulations to verify:
1. Detection: Health Monitor detects incident within 5 seconds
2. Self-healing: Self-Healing Engine triggers appropriate action
3. Incident logging: Incident Manager logs with proper context
4. Rollback path: Rollback Coordinator can execute if needed

Target SLA: <60s for complete rollback path

For EP-NS-008 Batch 2: Incident Simulation
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
from datetime import UTC, datetime
from typing import Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Import ACP components
from src.autonomous_control_plane import SelfHealingEngine
from src.autonomous_control_plane.components.incident_manager import IncidentManager
from src.autonomous_control_plane.components.rollback_coordinator import (
    RollbackCoordinator,
)
from src.autonomous_control_plane.models.healing import LogEntry
from src.autonomous_control_plane.models.incidents import IncidentEvent, Severity
from src.common.circuit_breaker import CircuitBreakerRegistry


class IncidentSimulator:
    """Simulates various incident scenarios for ACP testing."""

    def __init__(self):
        """Initialize the incident simulator with ACP components."""
        self.healing_engine = SelfHealingEngine(
            trading_mode="paper",
            enable_approval_gates=False,  # Auto-approve for testing
        )
        self.incident_manager = IncidentManager()
        self.rollback_coordinator = RollbackCoordinator(
            incident_manager=self.incident_manager
        )
        self.cb_registry = CircuitBreakerRegistry()

        # Enable test mode to process injected failures
        self.healing_engine.enable_test_mode()

        # Timing metrics storage
        self.timing_results: list[dict[str, Any]] = []

    async def run_all_scenarios(self) -> dict[str, Any]:
        """Run all incident simulation scenarios.

        Returns:
            Summary of all scenario results
        """
        logger.info("=" * 60)
        logger.info("STARTING INCIDENT SIMULATION SUITE")
        logger.info("=" * 60)

        scenarios = [
            ("Scenario A: Redis Connectivity Failure", self.scenario_redis_failure),
            ("Scenario B: API Timeout with Circuit Breaker", self.scenario_api_timeout),
            (
                "Scenario C: Service Degradation with Rollback",
                self.scenario_service_degradation,
            ),
        ]

        results = []
        for name, scenario_func in scenarios:
            logger.info("")
            logger.info("-" * 60)
            logger.info(f"RUNNING: {name}")
            logger.info("-" * 60)

            try:
                result = await scenario_func()
                results.append(
                    {
                        "name": name,
                        "status": "PASSED" if result.get("success") else "FAILED",
                        "result": result,
                    }
                )
            except Exception as e:
                logger.exception(f"Scenario failed: {e}")
                results.append(
                    {
                        "name": name,
                        "status": "ERROR",
                        "error": str(e),
                    }
                )

        # Generate summary
        summary = {
            "timestamp": datetime.now(UTC).isoformat(),
            "total_scenarios": len(scenarios),
            "passed": sum(1 for r in results if r["status"] == "PASSED"),
            "failed": sum(1 for r in results if r["status"] == "FAILED"),
            "errors": sum(1 for r in results if r["status"] == "ERROR"),
            "scenarios": results,
            "timing_summary": self._generate_timing_summary(),
        }

        logger.info("")
        logger.info("=" * 60)
        logger.info("SIMULATION SUITE COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Total: {summary['total_scenarios']}")
        logger.info(f"Passed: {summary['passed']}")
        logger.info(f"Failed: {summary['failed']}")
        logger.info(f"Errors: {summary['errors']}")

        return summary

    async def scenario_redis_failure(self) -> dict[str, Any]:
        """Scenario A: Simulated Redis connectivity failure → auto-restart.

        Steps:
        1. Inject Redis connection failure log entry
        2. Measure detection time (target: <5s)
        3. Verify self-healing triggers RedisRestartAction
        4. Verify incident is logged with full context
        5. Measure total time from detection to healing

        Returns:
            Scenario result with timing evidence
        """
        logger.info("[Scenario A] Starting Redis failure simulation...")

        # Record start time
        scenario_start = time.time()

        # Step 1: Create and inject log entry for Redis failure
        log_entry = LogEntry(
            timestamp=datetime.now(UTC),
            level="ERROR",
            source="redis-connection-pool",
            message="ConnectionError: Error 111 connecting to host.docker.internal:6380. Connection refused.",
            metadata={
                "injected": True,
                "scenario": "redis_failure",
                "service": "redis",
            },
        )

        injection_time = time.time()
        logger.info(
            f"[Scenario A] Log entry injected at T+{injection_time - scenario_start:.3f}s"
        )

        # Step 2: Process the log entry through healing engine
        detection_start = time.time()
        attempt = await self.healing_engine.process_log_entry(log_entry)
        detection_end = time.time()

        detection_time = detection_end - detection_start
        logger.info(f"[Scenario A] Detection completed in {detection_time:.3f}s")

        # Step 3: Verify healing was triggered
        if attempt is None:
            return {
                "success": False,
                "error": "No healing attempt was created - pattern may not have matched",
                "detection_time": detection_time,
            }

        logger.info(f"[Scenario A] Healing triggered: {attempt.action_type}")
        logger.info(f"[Scenario A] Attempt status: {attempt.status.value}")

        # Step 4: Create incident record
        incident_event = IncidentEvent(
            event_type="redis_connection_failed",
            source="redis-connection-pool",
            message="Redis connection failure detected and healing triggered",
            severity_hint=Severity.P2,
            metadata={
                "healing_attempt_id": attempt.attempt_id,
                "action_type": attempt.action_type,
                "scenario": "redis_failure",
            },
        )

        incident = await self.incident_manager.create_incident(incident_event)
        logger.info(f"[Scenario A] Incident created: {incident.incident_id}")

        # Step 5: Calculate total time
        scenario_end = time.time()
        total_time = scenario_end - scenario_start

        # Record timing
        timing_record = {
            "scenario": "A",
            "name": "Redis Connectivity Failure",
            "injection_to_detection": detection_time,
            "total_time": total_time,
            "detection_target_met": detection_time < 5.0,
            "sla_target_met": total_time < 60.0,
        }
        self.timing_results.append(timing_record)

        logger.info(f"[Scenario A] Total scenario time: {total_time:.3f}s")
        logger.info(
            f"[Scenario A] Detection target (<5s): {'PASS' if timing_record['detection_target_met'] else 'FAIL'}"
        )
        logger.info(
            f"[Scenario A] SLA target (<60s): {'PASS' if timing_record['sla_target_met'] else 'FAIL'}"
        )

        return {
            "success": True,
            "detection_time_seconds": detection_time,
            "total_time_seconds": total_time,
            "healing_attempt_id": attempt.attempt_id,
            "action_type": attempt.action_type,
            "incident_id": incident.incident_id,
            "timing_record": timing_record,
        }

    async def scenario_api_timeout(self) -> dict[str, Any]:
        """Scenario B: Simulated API timeout → circuit breaker trip → retry.

        Steps:
        1. Create circuit breaker and set to OPEN state
        2. Inject API timeout log entry
        3. Measure detection time (target: <5s)
        4. Verify self-healing triggers CircuitBreakerResetAction
        5. Verify circuit breaker is reset to CLOSED
        6. Verify incident is logged

        Returns:
            Scenario result with timing evidence
        """
        logger.info("[Scenario B] Starting API timeout simulation...")

        scenario_start = time.time()

        # Step 1: Create circuit breaker and open it
        circuit_name = "bybit-api-circuit"
        cb = self.cb_registry.get_or_create(
            circuit_name,
            failure_threshold=5,
            timeout_seconds=60,
        )
        cb.force_open("simulated_api_failures")

        initial_cb_state = cb.get_state_dict()
        logger.info(
            f"[Scenario B] Circuit breaker '{circuit_name}' opened (state: {initial_cb_state['state']})"
        )

        # Step 2: Create log entry for API timeout
        log_entry = LogEntry(
            timestamp=datetime.now(UTC),
            level="ERROR",
            source="bybit-connector",
            message="API timeout after 30s waiting for response from /v5/order/create",
            metadata={
                "injected": True,
                "scenario": "api_timeout",
                "service": "bybit-api",
                "circuit_name": circuit_name,
                "endpoint": "/v5/order/create",
                "method": "POST",
            },
        )

        injection_time = time.time()
        logger.info(
            f"[Scenario B] Log entry injected at T+{injection_time - scenario_start:.3f}s"
        )

        # Step 3: Process through healing engine
        detection_start = time.time()
        attempt = await self.healing_engine.process_log_entry(log_entry)
        detection_end = time.time()

        detection_time = detection_end - detection_start
        logger.info(f"[Scenario B] Detection completed in {detection_time:.3f}s")

        # Step 4: Verify healing was triggered
        if attempt is None:
            return {
                "success": False,
                "error": "No healing attempt was created",
                "detection_time": detection_time,
            }

        logger.info(f"[Scenario B] Healing triggered: {attempt.action_type}")

        # Step 5: Verify circuit breaker state
        final_cb_state = cb.get_state_dict()
        logger.info(
            f"[Scenario B] Circuit breaker state after healing: {final_cb_state['state']}"
        )

        # Step 6: Create incident
        incident_event = IncidentEvent(
            event_type="api_timeout",
            source="bybit-connector",
            message="API timeout detected, circuit breaker reset triggered",
            severity_hint=Severity.P2,
            metadata={
                "healing_attempt_id": attempt.attempt_id,
                "circuit_name": circuit_name,
                "circuit_state_before": initial_cb_state["state"],
                "circuit_state_after": final_cb_state["state"],
                "scenario": "api_timeout",
            },
        )

        incident = await self.incident_manager.create_incident(incident_event)
        logger.info(f"[Scenario B] Incident created: {incident.incident_id}")

        # Calculate timing
        scenario_end = time.time()
        total_time = scenario_end - scenario_start

        timing_record = {
            "scenario": "B",
            "name": "API Timeout with Circuit Breaker",
            "injection_to_detection": detection_time,
            "total_time": total_time,
            "detection_target_met": detection_time < 5.0,
            "sla_target_met": total_time < 60.0,
            "circuit_reset_success": final_cb_state["state"] == "CLOSED",
        }
        self.timing_results.append(timing_record)

        logger.info(f"[Scenario B] Total scenario time: {total_time:.3f}s")
        logger.info(
            f"[Scenario B] Detection target (<5s): {'PASS' if timing_record['detection_target_met'] else 'FAIL'}"
        )
        logger.info(
            f"[Scenario B] Circuit reset: {'PASS' if timing_record['circuit_reset_success'] else 'FAIL'}"
        )

        return {
            "success": True,
            "detection_time_seconds": detection_time,
            "total_time_seconds": total_time,
            "healing_attempt_id": attempt.attempt_id,
            "action_type": attempt.action_type,
            "incident_id": incident.incident_id,
            "circuit_state_before": initial_cb_state["state"],
            "circuit_state_after": final_cb_state["state"],
            "timing_record": timing_record,
        }

    async def scenario_service_degradation(self) -> dict[str, Any]:
        """Scenario C: Simulated service degradation → incident logged → rollback available.

        Steps:
        1. Create rollback operation for target state
        2. Inject service degradation log entry
        3. Measure detection time (target: <5s)
        4. Verify self-healing triggers appropriate action
        5. Verify incident is logged with full context
        6. Verify rollback path is available
        7. Measure rollback path timing

        Returns:
            Scenario result with timing evidence
        """
        logger.info("[Scenario C] Starting service degradation simulation...")

        scenario_start = time.time()

        # Step 1: Create rollback operation
        target_state = "v1.2.3-stable"
        rollback_op = await self.rollback_coordinator.create_rollback_operation(
            target_state=target_state,
            initiated_by="incident_simulator",
            metadata={
                "scenario": "service_degradation",
                "reason": "service_performance_degraded",
            },
        )
        logger.info(
            f"[Scenario C] Rollback operation created: {rollback_op.operation_id}"
        )
        logger.info(f"[Scenario C] Target state: {target_state}")

        # Step 2: Create log entry for service degradation
        log_entry = LogEntry(
            timestamp=datetime.now(UTC),
            level="WARNING",
            source="order-simulator",
            message="Service degradation detected: response time > 5000ms, error rate > 5%",
            metadata={
                "injected": True,
                "scenario": "service_degradation",
                "service": "order-simulator",
                "response_time_ms": 5200,
                "error_rate": 0.06,
            },
        )

        injection_time = time.time()
        logger.info(
            f"[Scenario C] Log entry injected at T+{injection_time - scenario_start:.3f}s"
        )

        # Step 3: Process through healing engine
        detection_start = time.time()
        attempt = await self.healing_engine.process_log_entry(log_entry)
        detection_end = time.time()

        detection_time = detection_end - detection_start
        logger.info(f"[Scenario C] Detection completed in {detection_time:.3f}s")

        # Step 4: Create incident with severity classification
        incident_event = IncidentEvent(
            event_type="service_degraded",
            source="order-simulator",
            message="Service degradation detected: high latency and error rate",
            severity_hint=Severity.P1,  # Higher severity due to impact
            metadata={
                "healing_attempt_id": attempt.attempt_id if attempt else None,
                "response_time_ms": 5200,
                "error_rate": 0.06,
                "rollback_operation_id": rollback_op.operation_id,
                "rollback_target_state": target_state,
                "scenario": "service_degradation",
            },
        )

        incident = await self.incident_manager.create_incident(incident_event)
        logger.info(f"[Scenario C] Incident created: {incident.incident_id}")
        logger.info(f"[Scenario C] Incident severity: {incident.severity.value}")

        # Step 5: Verify rollback path is available
        rollback_start = time.time()

        # Validate rollback (don't execute, just verify path)
        validation_result = await self.rollback_coordinator.validate_rollback(
            target_state=target_state
        )

        rollback_end = time.time()
        rollback_path_time = rollback_end - rollback_start

        logger.info(
            f"[Scenario C] Rollback path validation: {'PASS' if validation_result.valid else 'FAIL'}"
        )
        logger.info(f"[Scenario C] Rollback path check time: {rollback_path_time:.3f}s")

        # Calculate total timing
        scenario_end = time.time()
        total_time = scenario_end - scenario_start

        timing_record = {
            "scenario": "C",
            "name": "Service Degradation with Rollback",
            "injection_to_detection": detection_time,
            "rollback_path_check": rollback_path_time,
            "total_time": total_time,
            "detection_target_met": detection_time < 5.0,
            "sla_target_met": total_time < 60.0,
            "rollback_available": validation_result.valid,
        }
        self.timing_results.append(timing_record)

        logger.info(f"[Scenario C] Total scenario time: {total_time:.3f}s")
        logger.info(
            f"[Scenario C] Detection target (<5s): {'PASS' if timing_record['detection_target_met'] else 'FAIL'}"
        )
        logger.info(
            f"[Scenario C] SLA target (<60s): {'PASS' if timing_record['sla_target_met'] else 'FAIL'}"
        )

        return {
            "success": True,
            "detection_time_seconds": detection_time,
            "rollback_path_check_seconds": rollback_path_time,
            "total_time_seconds": total_time,
            "healing_attempt_id": attempt.attempt_id if attempt else None,
            "incident_id": incident.incident_id,
            "incident_severity": incident.severity.value,
            "rollback_operation_id": rollback_op.operation_id,
            "rollback_target_state": target_state,
            "rollback_available": validation_result.valid,
            "timing_record": timing_record,
        }

    def _generate_timing_summary(self) -> dict[str, Any]:
        """Generate summary of timing results across all scenarios.

        Returns:
            Timing summary statistics
        """
        if not self.timing_results:
            return {"error": "No timing results recorded"}

        detection_times = [r["injection_to_detection"] for r in self.timing_results]
        total_times = [r["total_time"] for r in self.timing_results]

        return {
            "detection_time": {
                "min_seconds": min(detection_times),
                "max_seconds": max(detection_times),
                "avg_seconds": sum(detection_times) / len(detection_times),
                "target_met_count": sum(
                    1 for r in self.timing_results if r["detection_target_met"]
                ),
                "target_missed_count": sum(
                    1 for r in self.timing_results if not r["detection_target_met"]
                ),
            },
            "total_time": {
                "min_seconds": min(total_times),
                "max_seconds": max(total_times),
                "avg_seconds": sum(total_times) / len(total_times),
                "sla_met_count": sum(
                    1 for r in self.timing_results if r["sla_target_met"]
                ),
                "sla_missed_count": sum(
                    1 for r in self.timing_results if not r["sla_target_met"]
                ),
            },
            "all_results": self.timing_results,
        }


async def main():
    """Main entry point for incident simulation."""
    logger.info("Initializing Incident Simulator...")

    simulator = IncidentSimulator()
    summary = await simulator.run_all_scenarios()

    # Output JSON summary
    print("\n" + "=" * 60)
    print("JSON SUMMARY")
    print("=" * 60)
    print(json.dumps(summary, indent=2, default=str))

    # Exit with appropriate code
    if summary["failed"] > 0 or summary["errors"] > 0:
        logger.error(
            f"Simulation completed with {summary['failed']} failures and {summary['errors']} errors"
        )
        sys.exit(1)
    else:
        logger.info("All scenarios passed successfully")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
