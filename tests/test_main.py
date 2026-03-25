# tests/test_main.py
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from click.testing import CliRunner
from scraper.main import cli, load_config, setup_logging


class TestConfig:
    def test_load_config(self, tmp_path):
        config_file = tmp_path / "config.yaml"
        config_file.write_text("scraping:\n  max_pages: 10\nbrowser:\n  headless: true\n")
        config = load_config(str(config_file))
        assert config["scraping"]["max_pages"] == 10
        assert config["browser"]["headless"] is True

    def test_load_config_missing_file(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/config.yaml")


class TestLogging:
    def test_setup_logging_no_error(self, tmp_path):
        setup_logging(str(tmp_path / "logs"))


class TestCLI:
    def test_run_command_exists(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0
        assert "run" in result.output.lower() or "--help" in result.output

    def test_status_command_exists(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["status", "--help"])
        assert result.exit_code == 0
