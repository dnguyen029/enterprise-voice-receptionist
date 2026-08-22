from unittest.mock import MagicMock, patch

from app.tools import log_lead
from app.tools_lib.zendesk import ZendeskClient


@patch("app.tools_lib.zendesk.requests.get")
@patch("app.tools_lib.zendesk.requests.post")
def test_zendesk_client_create_ticket_with_assignee(mock_post, mock_get):
    # Mock user search endpoint resolution
    mock_get_response = MagicMock()
    mock_get_response.json.return_value = {
        "users": [{"id": 1234567, "email": "support@omniretail.com"}]
    }
    mock_get.return_value = mock_get_response

    # Mock ticket creation endpoint response
    mock_post_response = MagicMock()
    mock_post_response.json.return_value = {"ticket": {"id": 9999}}
    mock_post.return_value = mock_post_response

    # Setup ZendeskClient
    with patch.dict(
        "os.environ",
        {
            "ZENDESK_SUBDOMAIN": "omniretail",
            "ZENDESK_EMAIL": "support@omniretail.com",
            "ZENDESK_TOKEN": "mocktoken",
        },
    ):
        client = ZendeskClient()
        success = client.create_ticket(
            name="Alice Smith",
            email="alice@example.com",
            phone_number="+1234567890",
            summary="Needs order lookup details.",
            status="open",
            urgency="high",
            purchase_order="PO-123",
        )

        assert success is True
        # Verify resolution request was made
        mock_get.assert_called_once()
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        payload = kwargs["json"]
        assert payload["ticket"]["assignee_id"] == 1234567
        assert "after_hours" in payload["ticket"]["tags"]
        assert "ai_receptionist" in payload["ticket"]["tags"]
        assert payload["ticket"]["requester"]["name"] == "Alice Smith"
        assert payload["ticket"]["requester"]["email"] == "alice@example.com"
        assert payload["ticket"]["status"] == "open"
        assert payload["ticket"]["priority"] == "high"


@patch("app.tools.SheetsClient")
@patch("app.tools_lib.zendesk.requests.get")
@patch("app.tools_lib.zendesk.requests.post")
def test_log_lead_triggers_ticket_creation(mock_post, mock_get, mock_sheets):
    # Mock sheets logging
    mock_sheets.return_value.upsert_log.return_value = True

    # Mock assignee search & ticket creation
    mock_get_response = MagicMock()
    mock_get_response.json.return_value = {
        "users": [{"id": 1234567, "email": "support@omniretail.com"}]
    }
    mock_get.return_value = mock_get_response

    mock_post_response = MagicMock()
    mock_post_response.json.return_value = {"ticket": {"id": 9999}}
    mock_post.return_value = mock_post_response

    with patch.dict(
        "os.environ",
        {
            "ZENDESK_SUBDOMAIN": "omniretail",
            "ZENDESK_EMAIL": "support@omniretail.com",
            "ZENDESK_TOKEN": "mocktoken",
        },
    ):
        res = log_lead(
            name="Alice Smith",
            phone_number="+1234567890",
            email="alice@example.com",
            intent="Lead Capture",
            urgency="high",
            sentiment="neutral",
            summary="Conversation summary goes here",
        )
        assert res["success"] is True
        assert res["sync_status"] == "synced_all"
        # Confirm ticket creation was triggered because ticket_id was empty but summary was provided
        mock_post.assert_called_once()
