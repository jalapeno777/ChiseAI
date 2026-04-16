"""E2E Integration tests for Phase 3 Safety endpoints.

ST-SAFETY-001: Circuit Breaker Enhancement
ST-SAFETY-002: Retry Budget Enforcement
ST-SAFETY-003: Automated Rollback

Tests the live API endpoints for:
- Circuit breaker state transitions (CLOSED -> OPEN -> HALF_OPEN -> CLOSED)
- Retry budget operations
- Rollback endpoint responsiveness
"""

from __future__ import annotations

import time

import pytest
import requests

# Use host.docker.internal when running inside a container, localhost otherwise
BASE_URL = "http://host.docker.internal:8001/api/v1"

# Skip all tests - requires autonomous control plane service on port 8001 not available in CI
pytestmark = pytest.mark.skip(
    reason="Requires autonomous control plane service on port 8001 - not available in CI"
)


class TestCircuitBreakerLifecycle:
    """Test full circuit breaker lifecycle via live API."""

    @pytest.fixture
    def cb_name(self):
        """Generate unique circuit breaker name for test isolation."""
        return f"e2e-test-cb-{int(time.time())}"

    @pytest.fixture(autouse=True)
    def cleanup_cb(self, cb_name):
        """Cleanup circuit breaker after test."""
        yield
        try:
            requests.delete(f"{BASE_URL}/circuit-breakers/{cb_name}")
        except Exception:
            pass

    def test_create_circuit_breaker(self, cb_name):
        """Test creating a circuit breaker."""
        response = requests.post(
            f"{BASE_URL}/circuit-breakers/{cb_name}",
            json={
                "failure_threshold": 3,
                "recovery_timeout": 5,
                "half_open_max_calls": 2,
            },
        )
        assert response.status_code in [
            200,
            201,
        ], f"Failed to create CB: {response.status_code} - {response.text}"
        data = response.json()
        assert data["name"] == cb_name
        print(f"✓ Created circuit breaker: {cb_name}")

    def test_get_circuit_breaker_closed_state(self, cb_name):
        """Test getting circuit breaker in CLOSED state."""
        # Create circuit breaker first
        requests.post(
            f"{BASE_URL}/circuit-breakers/{cb_name}",
            json={
                "failure_threshold": 3,
                "recovery_timeout": 5,
                "half_open_max_calls": 2,
            },
        )

        # Get circuit breaker (should be CLOSED)
        response = requests.get(f"{BASE_URL}/circuit-breakers/{cb_name}")
        assert response.status_code == 200
        data = response.json()
        assert (
            data["state"].upper() == "CLOSED"
        ), f"Expected CLOSED, got {data['state']}"
        print(f"✓ Circuit breaker state: {data['state']}")

    def test_circuit_breaker_opens_after_force_open(self, cb_name):
        """Test circuit breaker transitions to OPEN after force-open."""
        # Create circuit breaker
        requests.post(
            f"{BASE_URL}/circuit-breakers/{cb_name}",
            json={
                "failure_threshold": 3,
                "recovery_timeout": 2,
                "half_open_max_calls": 2,
            },
        )

        # Force open the circuit
        response = requests.post(
            f"{BASE_URL}/circuit-breakers/{cb_name}/force-open",
            params={"reason": "e2e-test"},
        )
        assert response.status_code == 200
        print("✓ Forced circuit breaker open")

        # Check circuit is OPEN
        response = requests.get(f"{BASE_URL}/circuit-breakers/{cb_name}")
        data = response.json()
        assert (
            data["state"].upper() == "OPEN"
        ), f"Expected OPEN after force-open, got {data['state']}"
        print(f"✓ Circuit breaker opened: {data['state']}")

    def test_circuit_breaker_lifecycle_closed_to_open_to_closed(self, cb_name):
        """Test full lifecycle: CLOSED -> OPEN -> CLOSED via reset."""
        # Create circuit breaker
        requests.post(
            f"{BASE_URL}/circuit-breakers/{cb_name}",
            json={
                "failure_threshold": 3,
                "recovery_timeout": 2,
                "half_open_max_calls": 2,
            },
        )

        # Verify initial CLOSED state
        response = requests.get(f"{BASE_URL}/circuit-breakers/{cb_name}")
        data = response.json()
        assert data["state"].upper() == "CLOSED"
        print("✓ Initial state: CLOSED")

        # Force open
        requests.post(
            f"{BASE_URL}/circuit-breakers/{cb_name}/force-open",
            params={"reason": "e2e-test"},
        )

        # Verify OPEN state
        response = requests.get(f"{BASE_URL}/circuit-breakers/{cb_name}")
        data = response.json()
        assert data["state"].upper() == "OPEN"
        print("✓ State after force-open: OPEN")

        # Reset circuit breaker
        response = requests.post(f"{BASE_URL}/circuit-breakers/{cb_name}/reset")
        assert response.status_code == 200
        print("✓ Circuit breaker reset")

        # Verify CLOSED again
        response = requests.get(f"{BASE_URL}/circuit-breakers/{cb_name}")
        data = response.json()
        assert data["state"].upper() == "CLOSED"
        print("✓ Final state after reset: CLOSED")

    def test_circuit_breaker_force_close(self, cb_name):
        """Test force-close endpoint."""
        # Create circuit breaker
        requests.post(
            f"{BASE_URL}/circuit-breakers/{cb_name}",
            json={
                "failure_threshold": 3,
                "recovery_timeout": 2,
                "half_open_max_calls": 2,
            },
        )

        # Force open first
        requests.post(
            f"{BASE_URL}/circuit-breakers/{cb_name}/force-open",
            params={"reason": "e2e-test"},
        )

        # Verify OPEN
        response = requests.get(f"{BASE_URL}/circuit-breakers/{cb_name}")
        assert response.json()["state"].upper() == "OPEN"

        # Force close
        response = requests.post(
            f"{BASE_URL}/circuit-breakers/{cb_name}/force-close",
            params={"reason": "e2e-test"},
        )
        assert response.status_code == 200

        # Verify CLOSED
        response = requests.get(f"{BASE_URL}/circuit-breakers/{cb_name}")
        assert response.json()["state"].upper() == "CLOSED"
        print("✓ Force-close successful")


class TestRetryBudgetOperations:
    """Test retry budget operations via live API."""

    def test_get_all_budgets(self):
        """Test getting all retry budgets."""
        response = requests.get(f"{BASE_URL}/retry/budgets")
        assert (
            response.status_code == 200
        ), f"Failed to get budgets: {response.status_code} - {response.text}"
        data = response.json()
        # Response format: {"success": true, "data": {"budgets": [], "count": 0}}
        assert "success" in data or "budgets" in data or "data" in data
        print("✓ Got all retry budgets")

    def test_get_budget_for_service(self):
        """Test getting retry budget for a specific service."""
        service_name = "e2e-test-service"
        response = requests.get(f"{BASE_URL}/retry/budgets/{service_name}")
        assert (
            response.status_code == 200
        ), f"Failed to get budget: {response.status_code} - {response.text}"
        data = response.json()
        print(f"✓ Got retry budget for {service_name}: {data}")

    def test_reset_budget(self):
        """Test resetting retry budget."""
        service_name = "e2e-test-service"
        response = requests.post(f"{BASE_URL}/retry/budgets/{service_name}/reset")
        assert response.status_code == 200
        print(f"✓ Reset retry budget for {service_name}")

    def test_get_endpoint_budgets(self):
        """Test getting endpoint budgets."""
        response = requests.get(f"{BASE_URL}/retry/endpoint-budgets")
        assert response.status_code == 200
        print("✓ Got endpoint budgets")

    def test_get_retry_metrics(self):
        """Test getting retry metrics."""
        response = requests.get(f"{BASE_URL}/retry/metrics")
        assert response.status_code == 200
        data = response.json()
        print(f"✓ Got retry metrics: {list(data.keys())}")

    def test_get_retry_analytics(self):
        """Test getting retry analytics."""
        response = requests.get(f"{BASE_URL}/retry/analytics")
        assert response.status_code == 200
        print("✓ Got retry analytics")


class TestRollbackEndpoints:
    """Test rollback endpoints are responsive."""

    def test_rollback_history_endpoint(self):
        """Test rollback history endpoint."""
        response = requests.get(f"{BASE_URL}/rollback/history")
        # May return 404 if no history exists
        assert response.status_code in [200, 404]
        print(f"✓ Rollback history endpoint: {response.status_code}")

    def test_rollback_metrics_endpoint(self):
        """Test rollback metrics endpoint."""
        response = requests.get(f"{BASE_URL}/rollback/metrics")
        # May return 404 if no metrics exist
        assert response.status_code in [200, 404]
        print(f"✓ Rollback metrics endpoint: {response.status_code}")

    def test_rollback_templates_endpoint(self):
        """Test rollback templates endpoint."""
        response = requests.get(f"{BASE_URL}/rollback/templates")
        # May return 404 if no templates exist
        assert response.status_code in [200, 404]
        print(f"✓ Rollback templates endpoint: {response.status_code}")

    def test_rollback_triggers_endpoint(self):
        """Test rollback triggers endpoint."""
        response = requests.get(f"{BASE_URL}/rollback/triggers")
        # May return 404 if no triggers exist
        assert response.status_code in [200, 404]
        print(f"✓ Rollback triggers endpoint: {response.status_code}")

    def test_rollback_validate_endpoint(self):
        """Test rollback validate endpoint."""
        response = requests.post(
            f"{BASE_URL}/rollback/validate",
            json={
                "target_version": "1.0.0",
                "component": "test-component",
            },
        )
        # May return 200 or 422 depending on validation
        assert response.status_code in [200, 422, 400]
        print(f"✓ Rollback validate endpoint: {response.status_code}")


class TestCircuitBreakerBulkOperations:
    """Test circuit breaker bulk operations."""

    def test_get_all_circuit_breakers(self):
        """Test getting all circuit breakers."""
        response = requests.get(f"{BASE_URL}/circuit-breakers")
        assert response.status_code == 200
        data = response.json()
        assert "circuit_breakers" in data or "count" in data
        print(f"✓ Got all circuit breakers: {data.get('count', 'N/A')} total")

    def test_get_all_health(self):
        """Test getting health for all circuit breakers."""
        response = requests.get(f"{BASE_URL}/circuit-breakers/health/all")
        assert response.status_code == 200
        data = response.json()
        assert "overall_healthy" in data
        print(f"✓ Got all health: overall_healthy={data.get('overall_healthy')}")


class TestCircuitBreakerGroups:
    """Test circuit breaker group operations.

    NOTE: The /groups endpoint has a routing conflict with /{name} in the API.
    The /{name} route matches first, so these tests are marked as expected
    failures until the API routing is fixed.
    """

    @pytest.fixture
    def group_name(self):
        """Generate unique group name."""
        return f"e2e-test-group-{int(time.time())}"

    @pytest.fixture
    def cb_name(self):
        """Generate unique circuit breaker name."""
        return f"e2e-test-cb-group-{int(time.time())}"

    @pytest.mark.xfail(reason="API routing conflict: /{name} matches before /groups")
    def test_list_groups(self):
        """Test listing circuit breaker groups."""
        response = requests.get(f"{BASE_URL}/circuit-breakers/groups")
        assert response.status_code == 200
        data = response.json()
        assert "groups" in data or "count" in data
        print(f"✓ Listed groups: {data}")

    @pytest.mark.xfail(reason="API routing conflict: /{name} matches before /groups")
    def test_create_and_delete_group(self, group_name, cb_name):
        """Test creating and deleting a group."""
        # Create a circuit breaker first
        requests.post(
            f"{BASE_URL}/circuit-breakers/{cb_name}",
            json={"failure_threshold": 3},
        )

        # Create group
        response = requests.post(
            f"{BASE_URL}/circuit-breakers/groups",
            params={
                "name": group_name,
                "member_names": [cb_name],
                "cascade_open": True,
                "cascade_close": False,
            },
        )
        assert response.status_code in [200, 201]
        print(f"✓ Created group: {group_name}")

        # Get group
        response = requests.get(f"{BASE_URL}/circuit-breakers/groups/{group_name}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == group_name
        print(f"✓ Got group: {data['name']}")

        # Delete group
        response = requests.delete(f"{BASE_URL}/circuit-breakers/groups/{group_name}")
        assert response.status_code in [200, 204]
        print(f"✓ Deleted group: {group_name}")

        # Cleanup CB
        requests.delete(f"{BASE_URL}/circuit-breakers/{cb_name}")


def run_standalone_tests():
    """Run tests in standalone mode (without pytest)."""
    print("=" * 60)
    print("Phase 3 Safety E2E Integration Tests")
    print("=" * 60)

    # Test 1: Circuit Breaker Lifecycle
    print("\n1. Testing Circuit Breaker Lifecycle...")
    cb_name = f"e2e-test-cb-{int(time.time())}"

    try:
        # Create
        response = requests.post(
            f"{BASE_URL}/circuit-breakers/{cb_name}",
            json={
                "failure_threshold": 3,
                "recovery_timeout": 5,
                "half_open_max_calls": 2,
            },
        )
        assert response.status_code in [200, 201], f"Create failed: {response.text}"
        print(f"  ✓ Created circuit breaker: {cb_name}")

        # Get (CLOSED)
        response = requests.get(f"{BASE_URL}/circuit-breakers/{cb_name}")
        data = response.json()
        assert data["state"].upper() == "CLOSED"
        print(f"  ✓ Initial state: {data['state']}")

        # Force open
        response = requests.post(
            f"{BASE_URL}/circuit-breakers/{cb_name}/force-open",
            params={"reason": "e2e-test"},
        )
        assert response.status_code == 200
        print("  ✓ Forced circuit breaker open")

        # Check OPEN
        response = requests.get(f"{BASE_URL}/circuit-breakers/{cb_name}")
        data = response.json()
        assert data["state"].upper() == "OPEN"
        print(f"  ✓ State after force-open: {data['state']}")

        # Reset
        response = requests.post(f"{BASE_URL}/circuit-breakers/{cb_name}/reset")
        assert response.status_code == 200
        print("  ✓ Reset circuit breaker")

        # Check CLOSED again
        response = requests.get(f"{BASE_URL}/circuit-breakers/{cb_name}")
        data = response.json()
        assert data["state"].upper() == "CLOSED"
        print(f"  ✓ Final state: {data['state']}")

        # Cleanup
        requests.delete(f"{BASE_URL}/circuit-breakers/{cb_name}")

    except Exception as e:
        print(f"  ✗ Circuit breaker test failed: {e}")
        # Cleanup on failure
        try:
            requests.delete(f"{BASE_URL}/circuit-breakers/{cb_name}")
        except Exception:
            pass
        raise

    # Test 2: Retry Budget Operations
    print("\n2. Testing Retry Budget Operations...")

    try:
        service_name = "e2e-test-service"

        # Get budget
        response = requests.get(f"{BASE_URL}/retry/budgets/{service_name}")
        assert response.status_code == 200
        print(f"  ✓ Got retry budget for {service_name}")

        # Reset budget
        response = requests.post(f"{BASE_URL}/retry/budgets/{service_name}/reset")
        assert response.status_code == 200
        print("  ✓ Reset retry budget")

        # Get all budgets
        response = requests.get(f"{BASE_URL}/retry/budgets")
        assert response.status_code == 200
        print("  ✓ Got all retry budgets")

    except Exception as e:
        print(f"  ✗ Retry budget test failed: {e}")
        raise

    # Test 3: Rollback Endpoints
    print("\n3. Testing Rollback Endpoints...")

    try:
        # History endpoint (may return 404 if no history)
        response = requests.get(f"{BASE_URL}/rollback/history")
        assert response.status_code in [200, 404]
        print(f"  ✓ Rollback history endpoint: {response.status_code}")

        # Metrics endpoint (may return 404 if no metrics)
        response = requests.get(f"{BASE_URL}/rollback/metrics")
        assert response.status_code in [200, 404]
        print(f"  ✓ Rollback metrics endpoint: {response.status_code}")

        # Templates endpoint (may return 404 if no templates)
        response = requests.get(f"{BASE_URL}/rollback/templates")
        assert response.status_code in [200, 404]
        print(f"  ✓ Rollback templates endpoint: {response.status_code}")

        # Triggers endpoint (may return 404 if no triggers)
        response = requests.get(f"{BASE_URL}/rollback/triggers")
        assert response.status_code in [200, 404]
        print(f"  ✓ Rollback triggers endpoint: {response.status_code}")

    except Exception as e:
        print(f"  ✗ Rollback test failed: {e}")
        raise

    print("\n" + "=" * 60)
    print("✅ ALL E2E TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    run_standalone_tests()
