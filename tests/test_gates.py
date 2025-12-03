"""
Tests for deployment gates.
"""


from nthlayer.slos.gates import DeploymentGate, GateResult


class TestDeploymentGate:
    """Test deployment gate checks."""
    
    def test_approved_healthy_budget(self):
        """Test approval with healthy budget."""
        gate = DeploymentGate()
        
        result = gate.check_deployment(
            service="payment-api",
            tier="critical",
            budget_total_minutes=1440,  # 24 hours
            budget_consumed_minutes=50,  # ~3% consumed, 97% remaining
        )
        
        assert result.result == GateResult.APPROVED
        assert result.is_approved
        assert not result.is_warning
        assert not result.is_blocked
        assert result.budget_remaining_percentage > 90
    
    def test_warning_low_budget(self):
        """Test warning with low budget (between warning and blocking)."""
        gate = DeploymentGate()
        
        result = gate.check_deployment(
            service="payment-api",
            tier="critical",
            budget_total_minutes=1440,
            budget_consumed_minutes=1200,  # 83% consumed, 17% remaining
        )
        
        assert result.result == GateResult.WARNING
        assert result.is_warning
        assert not result.is_approved
        assert not result.is_blocked
        assert result.budget_remaining_percentage < 20
        assert result.budget_remaining_percentage > 10
    
    def test_blocked_critical_budget(self):
        """Test blocking with critical budget."""
        gate = DeploymentGate()
        
        result = gate.check_deployment(
            service="payment-api",
            tier="critical",
            budget_total_minutes=1440,
            budget_consumed_minutes=1350,  # 94% consumed, 6% remaining
        )
        
        assert result.result == GateResult.BLOCKED
        assert result.is_blocked
        assert not result.is_approved
        assert not result.is_warning
        assert result.budget_remaining_percentage < 10
    
    def test_standard_tier_no_blocking(self):
        """Test that standard tier doesn't block, only warns."""
        gate = DeploymentGate()
        
        # Even with very low budget, standard tier only warns
        result = gate.check_deployment(
            service="search-api",
            tier="standard",
            budget_total_minutes=1440,
            budget_consumed_minutes=1400,  # 97% consumed, 3% remaining
        )
        
        # Should warn but not block (standard tier has no blocking threshold)
        assert result.result == GateResult.WARNING
        assert result.blocking_threshold is None
    
    def test_low_tier_advisory_only(self):
        """Test that low tier is advisory only."""
        gate = DeploymentGate()
        
        result = gate.check_deployment(
            service="test-service",
            tier="low",
            budget_total_minutes=1440,
            budget_consumed_minutes=950,  # 66% consumed, 34% remaining
        )
        
        # Low tier has higher warning threshold (30%)
        # 34% remaining should be approved (above 30% threshold)
        assert result.result == GateResult.APPROVED
        assert result.blocking_threshold is None
    
    def test_blast_radius_tracking(self):
        """Test blast radius is tracked."""
        gate = DeploymentGate()
        
        downstream = [
            {"name": "checkout-service", "criticality": "critical"},
            {"name": "analytics-service", "criticality": "low"},
            {"name": "email-service", "criticality": "high"},
        ]
        
        result = gate.check_deployment(
            service="payment-api",
            tier="critical",
            budget_total_minutes=1440,
            budget_consumed_minutes=50,
            downstream_services=downstream,
        )
        
        assert len(result.downstream_services) == 3
        assert len(result.high_criticality_downstream) == 2
        assert "checkout-service" in result.high_criticality_downstream
        assert "email-service" in result.high_criticality_downstream
        assert "analytics-service" not in result.high_criticality_downstream
    
    def test_thresholds_per_tier(self):
        """Test that thresholds are correctly set per tier."""
        gate = DeploymentGate()
        
        critical_result = gate.check_deployment(
            "svc1", "critical", 1440, 50
        )
        assert critical_result.warning_threshold == 20.0
        assert critical_result.blocking_threshold == 10.0
        
        standard_result = gate.check_deployment(
            "svc2", "standard", 1440, 50
        )
        assert standard_result.warning_threshold == 20.0
        assert standard_result.blocking_threshold is None
        
        low_result = gate.check_deployment(
            "svc3", "low", 1440, 50
        )
        assert low_result.warning_threshold == 30.0
        assert low_result.blocking_threshold is None
    
    def test_recommendations_include_blast_radius(self):
        """Test that recommendations mention blast radius."""
        gate = DeploymentGate()
        
        downstream = [
            {"name": "checkout-service", "criticality": "critical"},
        ]
        
        result = gate.check_deployment(
            service="payment-api",
            tier="critical",
            budget_total_minutes=1440,
            budget_consumed_minutes=50,
            downstream_services=downstream,
        )
        
        # Should mention blast radius in recommendations
        blast_radius_mentioned = any(
            "Blast radius" in rec or "downstream" in rec
            for rec in result.recommendations
        )
        assert blast_radius_mentioned
