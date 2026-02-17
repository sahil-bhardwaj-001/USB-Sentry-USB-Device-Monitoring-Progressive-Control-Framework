import unittest
from unittest.mock import patch, mock_open
from usb_sentry.core.config import load_config, DEFAULT_CONFIG

class TestConfig(unittest.TestCase):
    @patch("builtins.open", new_callable=mock_open, read_data="interactive:\n  geometry: 120x40\n")
    @patch("pathlib.Path.exists", return_value=True)
    def test_load_custom_config(self, mock_exists, mock_file):
        config = load_config("dummy_config.yaml")
        self.assertEqual(config['interactive']['geometry'], "120x40")
        # Ensure defaults are preserved for missing keys
        self.assertEqual(config['app']['name'], "USB Sentry")

    @patch("pathlib.Path.exists", return_value=False)
    def test_load_defaults_missing_file(self, mock_exists):
        config = load_config("missing.yaml")
        self.assertEqual(config, DEFAULT_CONFIG)

    @patch("builtins.open", new_callable=mock_open, read_data="invalid_yaml: [")
    @patch("pathlib.Path.exists", return_value=True)
    def test_load_invalid_yaml(self, mock_exists, mock_file):
        # Should fallback to defaults on error?
        # Our implementation prints error and returns defaults
        config = load_config("bad.yaml")
        self.assertEqual(config, DEFAULT_CONFIG)

if __name__ == "__main__":
    unittest.main()
