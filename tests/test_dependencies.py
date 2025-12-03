"""
Tests for dependency correlation.
"""

from datetime import datetime, timedelta

from nthlayer.slos.dependencies import (
    Dependency,
    DependencyCorrelator,
    detect_circular_dependencies,
    validate_dependencies,
)


class TestDependencyCorrelator:
    """Test dependency correlation."""
    
    def test_attribution_disabled(self):
        """Test that attribution can be disabled (startup mode)."""
        correlator = DependencyCorrelator(enabled=False)
        
        now = datetime.now()
        incidents = [
            {
                "duration_minutes": 10,
                "start_time": now,
                "end_time": now + timedelta(minutes=10),
            }
        ]
        
        result = correlator.calculate_attribution(
            "payment-api",
            incidents,
            [],
            {},
        )
        
        assert not result.attribution_enabled
        assert result.total_consumed_minutes == 10
        assert result.direct_consumed_minutes == 10
        assert result.inherited_consumed_minutes == 0
        assert len(result.inherited_impacts) == 0
    
    def test_attribution_enabled(self):
        """Test inherited impact calculation."""
        correlator = DependencyCorrelator(enabled=True)
        
        now = datetime.now()
        
        # Downstream incident (payment-api)
        incidents = [
            {
                "duration_minutes": 10,
                "start_time": now,
                "end_time": now + timedelta(minutes=10),
                "summary": "High error rate",
            }
        ]
        
        # Critical dependency
        deps = [
            Dependency("auth-service", "critical"),
        ]
        
        # Upstream incident (auth-service) - started earlier
        upstream_incidents = {
            "auth-service": [
                {
                    "duration_minutes": 12,
                    "start_time": now - timedelta(minutes=2),
                    "end_time": now + timedelta(minutes=10),
                    "summary": "Database timeout",
                }
            ]
        }
        
        result = correlator.calculate_attribution(
            "payment-api",
            incidents,
            deps,
            upstream_incidents,
        )
        
        assert result.attribution_enabled
        assert result.inherited_consumed_minutes > 0
        assert len(result.inherited_impacts) == 1
        
        impact = result.inherited_impacts[0]
        assert impact.upstream_service == "auth-service"
        assert impact.criticality == "critical"
        assert impact.correlation_confidence > 0.8
    
    def test_no_correlation_for_low_criticality(self):
        """Test that low criticality deps don't get attributed."""
        correlator = DependencyCorrelator(enabled=True)
        
        now = datetime.now()
        
        incidents = [
            {
                "duration_minutes": 10,
                "start_time": now,
                "end_time": now + timedelta(minutes=10),
            }
        ]
        
        # Low criticality dependency
        deps = [
            Dependency("cache-service", "low"),
        ]
        
        upstream_incidents = {
            "cache-service": [
                {
                    "duration_minutes": 10,
                    "start_time": now,
                    "end_time": now + timedelta(minutes=10),
                    "summary": "Cache miss",
                }
            ]
        }
        
        result = correlator.calculate_attribution(
            "payment-api",
            incidents,
            deps,
            upstream_incidents,
        )
        
        # Should not attribute low criticality deps
        assert result.inherited_consumed_minutes == 0
        assert len(result.inherited_impacts) == 0
    
    def test_correlation_confidence(self):
        """Test correlation confidence calculation."""
        correlator = DependencyCorrelator(enabled=True)
        
        now = datetime.now()
        
        # Test high overlap + causation (upstream started first)
        incidents = [
            {
                "duration_minutes": 10,
                "start_time": now,
                "end_time": now + timedelta(minutes=10),
            }
        ]
        
        deps = [Dependency("auth-service", "critical")]
        
        upstream_incidents = {
            "auth-service": [
                {
                    "duration_minutes": 12,
                    "start_time": now - timedelta(minutes=2),  # Started 2min earlier
                    "end_time": now + timedelta(minutes=10),
                    "summary": "Outage",
                }
            ]
        }
        
        result = correlator.calculate_attribution(
            "payment-api",
            incidents,
            deps,
            upstream_incidents,
        )
        
        # Should have high confidence (100% overlap + causation bonus)
        assert len(result.inherited_impacts) == 1
        assert result.inherited_impacts[0].correlation_confidence > 0.9


class TestValidateDependencies:
    """Test dependency validation."""
    
    def test_valid_dependencies(self):
        """Test validation passes for valid deps."""
        deps = [
            Dependency("auth-service", "high"),
            Dependency("cache-service", "low"),
        ]
        
        all_services = {"payment-api", "auth-service", "cache-service"}
        
        errors, warnings = validate_dependencies(
            "payment-api",
            deps,
            all_services,
        )
        
        assert len(errors) == 0
        assert len(warnings) == 0
    
    def test_missing_dependency(self):
        """Test warning for missing dependency."""
        deps = [
            Dependency("nonexistent-service", "high"),
        ]
        
        all_services = {"payment-api"}
        
        errors, warnings = validate_dependencies(
            "payment-api",
            deps,
            all_services,
        )
        
        assert len(errors) == 0
        assert len(warnings) == 1
        assert "nonexistent-service" in warnings[0]
    
    def test_self_dependency(self):
        """Test error for self-dependency."""
        deps = [
            Dependency("payment-api", "high"),
        ]
        
        all_services = {"payment-api"}
        
        errors, warnings = validate_dependencies(
            "payment-api",
            deps,
            all_services,
        )
        
        assert len(errors) == 1
        assert "cannot depend on itself" in errors[0]


class TestCircularDependencies:
    """Test circular dependency detection."""
    
    def test_no_circular_deps(self):
        """Test detection with no cycles."""
        service_deps = {
            "A": ["B", "C"],
            "B": ["C"],
            "C": [],
        }
        
        cycles = detect_circular_dependencies(service_deps)
        
        assert len(cycles) == 0
    
    def test_simple_circular_dep(self):
        """Test simple A→B→A cycle."""
        service_deps = {
            "A": ["B"],
            "B": ["A"],
        }
        
        cycles = detect_circular_dependencies(service_deps)
        
        assert len(cycles) > 0
    
    def test_complex_circular_dep(self):
        """Test A→B→C→A cycle."""
        service_deps = {
            "A": ["B"],
            "B": ["C"],
            "C": ["A"],
        }
        
        cycles = detect_circular_dependencies(service_deps)
        
        assert len(cycles) > 0
