"""
Tests for PagerDuty integration.
"""

from unittest.mock import Mock, patch

from nthlayer.integrations.pagerduty import PagerDutyClient


class TestPagerDutyClient:
    """Test PagerDuty client."""
    
    @patch('nthlayer.integrations.pagerduty.httpx.Client')
    def test_find_existing_service(self, mock_client_class):
        """Test finding existing service."""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        mock_response = Mock()
        mock_response.json.return_value = {
            "services": [
                {
                    "id": "PXXXXXX",
                    "name": "payment-api",
                    "html_url": "https://test.pagerduty.com/services/PXXXXXX",
                    "escalation_policy": {"id": "EPXXXXX"},
                }
            ]
        }
        mock_client.get.return_value = mock_response
        
        # Test
        client = PagerDutyClient("test_key")
        result = client.setup_service("payment-api")
        
        assert result.success
        assert result.service_id == "PXXXXXX"
        assert not result.created_service
        assert result.warnings
    
    @patch('nthlayer.integrations.pagerduty.httpx.Client')
    def test_create_new_service(self, mock_client_class):
        """Test creating new service."""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        # Service doesn't exist
        get_service_response = Mock()
        get_service_response.json.return_value = {"services": []}
        
        # Get current user for default policy
        get_user_response = Mock()
        get_user_response.json.return_value = {
            "user": {"id": "UXXXXXX", "name": "Test User"}
        }
        
        # Create escalation policy
        create_ep_response = Mock()
        create_ep_response.json.return_value = {
            "escalation_policy": {"id": "EPXXXXX", "name": "payment-api-escalation"}
        }
        
        # Create service
        create_service_response = Mock()
        create_service_response.json.return_value = {
            "service": {
                "id": "PXXXXXX",
                "name": "payment-api",
                "html_url": "https://test.pagerduty.com/services/PXXXXXX",
            }
        }
        
        # Configure mock to return different responses
        mock_client.get.side_effect = [get_service_response, get_user_response]
        mock_client.post.side_effect = [create_ep_response, create_service_response]
        
        # Test
        client = PagerDutyClient("test_key")
        result = client.setup_service("payment-api")
        
        assert result.success
        assert result.service_id == "PXXXXXX"
        assert result.created_service
        assert result.created_escalation_policy
    
    @patch('nthlayer.integrations.pagerduty.httpx.Client')
    def test_create_service_with_team(self, mock_client_class):
        """Test creating service with team mapping."""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        # Service doesn't exist
        get_service_response = Mock()
        get_service_response.json.return_value = {"services": []}
        
        # Get current user
        get_user_response = Mock()
        get_user_response.json.return_value = {
            "user": {"id": "UXXXXXX", "name": "Test User"}
        }
        
        # Team exists
        get_team_response = Mock()
        get_team_response.json.return_value = {
            "teams": [{"id": "TXXXXXX", "name": "payments"}]
        }
        
        # Create escalation policy
        create_ep_response = Mock()
        create_ep_response.json.return_value = {
            "escalation_policy": {"id": "EPXXXXX"}
        }
        
        # Create service
        create_service_response = Mock()
        create_service_response.json.return_value = {
            "service": {
                "id": "PXXXXXX",
                "name": "payment-api",
                "html_url": "https://test.pagerduty.com/services/PXXXXXX",
            }
        }
        
        # Add service to team
        add_to_team_response = Mock()
        
        # Configure mock
        mock_client.get.side_effect = [
            get_service_response,
            get_user_response,
            get_team_response,
        ]
        mock_client.post.side_effect = [create_ep_response, create_service_response]
        mock_client.put.return_value = add_to_team_response
        
        # Test
        client = PagerDutyClient("test_key")
        result = client.setup_service(
            "payment-api",
            team_name="payments",
        )
        
        assert result.success
        assert result.team_id == "TXXXXXX"
        assert not result.created_team
    
    @patch('nthlayer.integrations.pagerduty.httpx.Client')
    def test_use_existing_escalation_policy(self, mock_client_class):
        """Test using existing escalation policy."""
        # Setup mock
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        
        # Service doesn't exist
        get_service_response = Mock()
        get_service_response.json.return_value = {"services": []}
        
        # Escalation policy exists
        get_ep_response = Mock()
        get_ep_response.json.return_value = {
            "escalation_policies": [
                {"id": "EPXXXXX", "name": "payments-critical"}
            ]
        }
        
        # Create service
        create_service_response = Mock()
        create_service_response.json.return_value = {
            "service": {
                "id": "PXXXXXX",
                "name": "payment-api",
                "html_url": "https://test.pagerduty.com/services/PXXXXXX",
            }
        }
        
        # Configure mock
        mock_client.get.side_effect = [get_service_response, get_ep_response]
        mock_client.post.return_value = create_service_response
        
        # Test
        client = PagerDutyClient("test_key")
        result = client.setup_service(
            "payment-api",
            escalation_policy_name="payments-critical",
        )
        
        assert result.success
        assert result.escalation_policy_id == "EPXXXXX"
        assert not result.created_escalation_policy
