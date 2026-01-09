"""Tests for identity resolution module."""

import pytest
from nthlayer.identity import (
    IdentityMatch,
    IdentityResolver,
    NormalizationRule,
    ServiceIdentity,
    extract_from_pattern,
    extract_service_name,
    normalize_service_name,
)


class TestServiceIdentity:
    """Tests for ServiceIdentity model."""

    def test_basic_identity(self):
        """Test creating basic identity."""
        identity = ServiceIdentity(canonical_name="payment")
        assert identity.canonical_name == "payment"
        assert identity.aliases == set()  # aliases is a set, not list
        assert identity.external_ids == {}
        assert identity.attributes == {}
        assert identity.confidence == 1.0

    def test_identity_with_aliases(self):
        """Test identity with aliases."""
        identity = ServiceIdentity(
            canonical_name="payment",
            aliases={"payment-service", "payments"},  # Use set
        )
        assert "payment-service" in identity.aliases
        assert "payments" in identity.aliases

    def test_matches_canonical_name(self):
        """Test matches() with canonical name."""
        identity = ServiceIdentity(canonical_name="payment")
        assert identity.matches("payment") is True
        assert identity.matches("other") is False

    def test_matches_alias(self):
        """Test matches() with alias."""
        identity = ServiceIdentity(
            canonical_name="payment",
            aliases={"payments", "payment-service"},
        )
        assert identity.matches("payments") is True
        assert identity.matches("payment-service") is True
        assert identity.matches("unknown") is False

    def test_matches_external_id(self):
        """Test matches() with external ID."""
        identity = ServiceIdentity(
            canonical_name="payment",
            external_ids={"kubernetes": "payment-api-deployment"},
        )
        assert identity.matches("payment-api-deployment", provider="kubernetes") is True
        assert identity.matches("payment-api-deployment", provider="other") is False

    def test_matches_normalized_form(self):
        """Test matches() with normalized form."""
        # payment-api-prod normalizes to "payment"
        identity = ServiceIdentity(canonical_name="payment")
        assert identity.matches("payment-api-prod") is True
        assert identity.matches("payment-service") is True

    def test_merge_from(self):
        """Test merging two identities."""
        identity1 = ServiceIdentity(
            canonical_name="payment",
            aliases={"payments"},  # Use set
            attributes={"team": "platform"},
        )
        identity2 = ServiceIdentity(
            canonical_name="payment",
            aliases={"payment-service"},  # Use set
            external_ids={"kubernetes": "payment-deployment"},
            attributes={"tier": "critical"},
        )

        identity1.merge_from(identity2)

        assert "payments" in identity1.aliases
        assert "payment-service" in identity1.aliases
        assert identity1.external_ids["kubernetes"] == "payment-deployment"
        assert identity1.attributes["team"] == "platform"
        assert identity1.attributes["tier"] == "critical"

    def test_to_dict(self):
        """Test serialization to dict."""
        identity = ServiceIdentity(
            canonical_name="payment",
            aliases={"payments"},
            external_ids={"k8s": "payment-deploy"},
            attributes={"tier": "critical"},
        )

        data = identity.to_dict()
        assert data["canonical_name"] == "payment"
        assert "payments" in data["aliases"]
        assert data["external_ids"]["k8s"] == "payment-deploy"
        assert data["attributes"]["tier"] == "critical"


class TestNormalizeServiceName:
    """Tests for service name normalization."""

    def test_basic_normalization(self):
        """Test basic name normalization - removes common suffixes."""
        # normalize_service_name lowercases but doesn't strip whitespace
        assert normalize_service_name("Payment") == "payment"
        assert normalize_service_name("payment") == "payment"

    def test_removes_api_suffix(self):
        """Test that -api suffix is removed."""
        assert normalize_service_name("payment-api") == "payment"
        assert normalize_service_name("user-api") == "user"

    def test_removes_service_suffix(self):
        """Test that -service suffix is removed."""
        assert normalize_service_name("payment-service") == "payment"
        assert normalize_service_name("user-service") == "user"

    def test_remove_environment_suffix(self):
        """Test removing environment suffixes."""
        assert normalize_service_name("payment-prod") == "payment"
        assert normalize_service_name("payment-staging") == "payment"
        assert normalize_service_name("payment-dev") == "payment"

    def test_remove_version_suffix(self):
        """Test removing version suffixes."""
        assert normalize_service_name("payment-v1") == "payment"
        assert normalize_service_name("payment-v2") == "payment"

    def test_remove_type_prefix(self):
        """Test removing type prefixes."""
        assert normalize_service_name("svc-payment") == "payment"
        assert normalize_service_name("app-payment") == "payment"

    def test_extract_java_package(self):
        """Test extracting from Java package names."""
        # com.company.payment -> payment (after removing package prefix)
        result = normalize_service_name("com.company.payment")
        assert result == "payment"

    def test_custom_rules(self):
        """Test with custom normalization rules."""
        custom_rules = [
            NormalizationRule(
                pattern=r"-legacy$", replacement="", description="Remove legacy suffix"
            ),
        ]
        # Use 'rules=' parameter (not 'custom_rules=')
        result = normalize_service_name("payment-legacy", rules=custom_rules)
        assert result == "payment"


class TestExtractFromPattern:
    """Tests for pattern-based extraction."""

    def test_backstage_pattern(self):
        """Test extracting from Backstage patterns."""
        pattern = r"^(?:component|service|api):(?P<namespace>[^/]+)/(?P<name>.+)$"
        result = extract_from_pattern(
            "component:default/payment-api",
            pattern,
            "name",
        )
        assert result == "payment-api"

    def test_kubernetes_pattern(self):
        """Test extracting from Kubernetes namespace/name patterns."""
        pattern = r"^(?P<namespace>[^/]+)/(?P<name>.+)$"
        result = extract_from_pattern(
            "default/payment-api",
            pattern,
            "name",
        )
        assert result == "payment-api"

    def test_no_match(self):
        """Test with no match returns None."""
        pattern = r"^component:(?P<namespace>[^/]+)/(?P<name>.+)$"
        result = extract_from_pattern("payment-api", pattern, "name")
        assert result is None


class TestExtractServiceName:
    """Tests for service name extraction from various formats."""

    def test_backstage_extraction(self):
        """Test extracting from Backstage format."""
        result = extract_service_name("component:default/payment-api", "backstage")
        assert result == "payment"  # normalized

    def test_consul_extraction(self):
        """Test extracting from Consul format."""
        result = extract_service_name("dc1.payment-prod", "consul")
        assert result == "payment"  # normalized

    def test_simple_name(self):
        """Test simple name normalization."""
        result = extract_service_name("payment-api", "unknown")
        assert result == "payment"  # normalized


class TestIdentityResolver:
    """Tests for IdentityResolver class."""

    @pytest.fixture
    def resolver(self):
        """Create resolver with sample identities."""
        resolver = IdentityResolver()

        payment = ServiceIdentity(
            canonical_name="payment",
            aliases={"payments", "payment-service", "payment-api"},
            external_ids={"kubernetes": "payment-api-deployment"},
            attributes={"team": "platform", "tier": "critical"},
        )
        user = ServiceIdentity(
            canonical_name="user",
            aliases={"users", "user-service"},
        )

        resolver.register(payment)
        resolver.register(user)

        return resolver

    def test_resolve_exact_match(self, resolver):
        """Test resolving by exact canonical name."""
        match = resolver.resolve("payment")
        assert match is not None
        assert match.identity is not None
        assert match.identity.canonical_name == "payment"
        assert match.match_type == "exact"
        assert match.confidence >= 0.95

    def test_resolve_alias_match(self, resolver):
        """Test resolving by alias."""
        match = resolver.resolve("payments")
        assert match is not None
        assert match.identity is not None
        assert match.identity.canonical_name == "payment"
        assert match.match_type == "alias"

    def test_resolve_normalized_match(self, resolver):
        """Test resolving by normalized name."""
        # payment-api-prod normalizes to "payment"
        match = resolver.resolve("payment-api-prod")
        assert match is not None
        assert match.identity is not None
        assert match.identity.canonical_name == "payment"
        # Could be exact (if normalized to "payment") or normalized match type
        assert match.match_type in ("exact", "normalized")

    def test_resolve_external_id_match(self, resolver):
        """Test resolving by external ID."""
        match = resolver.resolve("payment-api-deployment", provider="kubernetes")
        assert match is not None
        assert match.identity is not None
        assert match.identity.canonical_name == "payment"
        assert match.match_type == "external_id"

    def test_resolve_no_match(self, resolver):
        """Test resolving unknown service."""
        match = resolver.resolve("completely-unknown")
        assert match is not None
        assert match.identity is None
        assert match.match_type == "none"
        assert match.confidence == 0.0

    def test_register_identity(self, resolver):
        """Test registering new identity."""
        checkout = ServiceIdentity(canonical_name="checkout")
        resolver.register(checkout)

        match = resolver.resolve("checkout")
        assert match is not None
        assert match.identity is not None
        assert match.identity.canonical_name == "checkout"

    def test_add_explicit_mapping(self, resolver):
        """Test adding explicit mapping."""
        resolver.add_mapping("legacy-payment", "payment")

        match = resolver.resolve("legacy-payment")
        assert match is not None
        assert match.identity is not None
        assert match.identity.canonical_name == "payment"
        assert match.match_type == "explicit_mapping"

    def test_register_from_discovery(self, resolver):
        """Test registering identity from discovery."""
        # register_from_discovery creates/updates an identity
        identity = resolver.register_from_discovery(
            raw_name="checkout-deployment",
            provider="kubernetes",
            attributes={"team": "checkout", "tier": "standard"},
        )

        # The returned identity should be valid
        assert identity is not None
        assert identity.external_ids.get("kubernetes") == "checkout-deployment"
        assert "checkout-deployment" in identity.aliases
        assert identity.attributes.get("team") == "checkout"

    def test_caching(self, resolver):
        """Test that resolution results are cached."""
        # First resolution
        match1 = resolver.resolve("payment")
        # Second resolution should return cached result
        match2 = resolver.resolve("payment")

        assert match1 == match2

    def test_clear_cache(self, resolver):
        """Test clearing the cache."""
        # Populate cache
        resolver.resolve("payment")
        assert len(resolver._cache) > 0

        # Clear cache
        resolver.clear_cache()
        assert len(resolver._cache) == 0


class TestIdentityMatch:
    """Tests for IdentityMatch model."""

    def test_basic_match(self):
        """Test creating basic match."""
        identity = ServiceIdentity(canonical_name="payment")
        match = IdentityMatch(
            query="payments",
            provider=None,
            identity=identity,
            match_type="alias",
            confidence=0.9,
        )

        assert match.query == "payments"
        assert match.identity is not None
        assert match.identity.canonical_name == "payment"
        assert match.match_type == "alias"
        assert match.confidence == 0.9
        assert match.found is True

    def test_no_match(self):
        """Test match with no identity."""
        match = IdentityMatch(
            query="unknown",
            provider=None,
            identity=None,
            match_type="none",
            confidence=0.0,
        )

        assert match.identity is None
        assert match.match_type == "none"
        assert match.confidence == 0.0
        assert match.found is False
