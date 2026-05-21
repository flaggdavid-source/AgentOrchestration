import pytest
from src.common.config import Config


class TestConfig:
    def test_load_config(self, tmp_path):
        config_file = tmp_path / "config.json"
        config_file.write_text('{"app": {"name": "test", "port": 8080}}')
        config = Config(str(config_file))
        assert config.get("app.name") == "test"
        assert config.get("app.port") == 8080

    def test_load_yaml_config(self, tmp_path):
        """Test loading a YAML config file (.yaml extension)."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text('app:\n  name: test\n  port: 8080')
        config = Config(str(config_file))
        assert config.get("app.name") == "test"
        assert config.get("app.port") == 8080

    def test_load_yml_config(self, tmp_path):
        """Test loading a YAML config file (.yml extension)."""
        config_file = tmp_path / "config.yml"
        config_file.write_text('app:\n  name: test-app\n  port: 9000')
        config = Config(str(config_file))
        assert config.get("app.name") == "test-app"
        assert config.get("app.port") == 9000

    def test_load_unsupported_format(self, tmp_path):
        """Test that unsupported config file formats raise ValueError."""
        config_file = tmp_path / "config.txt"
        config_file.write_text('app.name=test')
        with pytest.raises(ValueError) as exc_info:
            Config(str(config_file))
        assert "Unsupported config file format" in str(exc_info.value)
        assert ".txt" in str(exc_info.value)

    def test_default_value(self):
        config = Config()
        assert config.get("nonexistent.key", "default") == "default"

    def test_set_value(self):
        config = Config()
        config.set("database.host", "localhost")
        assert config.get("database.host") == "localhost"

    def test_nested_set(self):
        config = Config()
        config.set("a.b.c.d", "value")
        assert config.get("a.b.c.d") == "value"

    def test_to_dict(self):
        config = Config()
        config.set("key1", "value1")
        config.set("key2", "value2")
        data = config.to_dict()
        assert data["key1"] == "value1"
        assert data["key2"] == "value2"
