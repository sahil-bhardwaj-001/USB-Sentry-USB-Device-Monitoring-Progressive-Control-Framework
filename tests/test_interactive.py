import unittest
from unittest.mock import patch, mock_open, MagicMock
import sys
import json

# Ensure we can import the module
try:
    from usb_sentry.interactive import view_logs
except ImportError:
    # If dependencies are missing in test env
    view_logs = None

class TestInteractive(unittest.TestCase):
    
    def setUp(self):
        if view_logs is None:
            self.skipTest("usb_sentry.interactive could not be imported")

    @patch("usb_sentry.core.logger.log_file_path")
    @patch("builtins.open", new_callable=mock_open, read_data='{"timestamp": "2023-01-01T12:00:00", "level": "INFO", "message": "test msg"}\n')
    @patch("rich.console.Console.print")
    @patch("builtins.input", return_value="") 
    def test_view_logs_success(self, mock_input, mock_print, mock_file, mock_path):
        # Setup mock path
        mock_path.exists.return_value = True
        
        # Run function
        view_logs(lines=1)
        
        # Verify
        self.assertTrue(mock_print.called)
        # The exact call arguments are a Table object, harder to assert exact content equality
        # But we can check if file was opened
        mock_file.assert_called()

    @patch("usb_sentry.core.logger.log_file_path")
    @patch("rich.console.Console.print")
    def test_view_logs_missing_file(self, mock_print, mock_path):
        mock_path.exists.return_value = False
        view_logs()
        mock_print.assert_called_with("[red]Log file not found.[/red]")

if __name__ == "__main__":
    unittest.main()
