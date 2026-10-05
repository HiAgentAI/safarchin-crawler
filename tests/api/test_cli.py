import pytest
from typer.testing import CliRunner
from unittest.mock import AsyncMock, patch, MagicMock
from app.cli import app as cli_app
from app.db.models import APIKey

runner = CliRunner()

def test_cli_apikey_create():
    with patch("app.cli.async_session_maker") as mock_session_maker:
        mock_session = AsyncMock()
        mock_session_maker.return_value.__aenter__.return_value = mock_session

        result = runner.invoke(cli_app, ["apikey", "create", "--name", "TestApp", "--tier", "pro", "--rate-limit", "100"])
        assert result.exit_code == 0
        assert "API Key Generated Successfully" in result.stdout
        assert "TestApp" in result.stdout
        assert mock_session.commit.called

def test_cli_apikey_list():
    with patch("app.cli.async_session_maker") as mock_session_maker:
        mock_session = AsyncMock()
        mock_session_maker.return_value.__aenter__.return_value = mock_session

        fake_key = APIKey(
            id="12345678-abcd",
            key_hash="hash",
            client_name="TestApp",
            tier="pro",
            rate_limit_per_min=100,
            daily_quota=1000,
            is_active=True,
        )
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [fake_key]
        mock_session.execute.return_value = mock_result

        result = runner.invoke(cli_app, ["apikey", "list"])
        assert result.exit_code == 0
        assert "TestApp" in result.stdout
        assert "pro" in result.stdout

def test_cli_cache_flush():
    with patch("app.cli.CacheManager.flush_all", new_callable=AsyncMock) as mock_flush:
        result = runner.invoke(cli_app, ["cache", "flush"])
        assert result.exit_code == 0
        assert "flushed successfully" in result.stdout
        assert mock_flush.called

def test_cli_crawlers_status():
    result = runner.invoke(cli_app, ["crawlers", "status"])
    assert result.exit_code == 0
    assert "Registered Crawlers" in result.stdout
