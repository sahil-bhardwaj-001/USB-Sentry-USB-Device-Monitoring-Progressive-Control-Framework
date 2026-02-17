import unittest
import sys
import importlib

class TestAppImport(unittest.TestCase):
    def test_import_main(self):
        """
        Smoke test: Verify that the main application module can be imported 
        without raising ImportError or ModuleNotFoundError.
        This catches issues like missing dependencies or typos in imports.
        """
        try:
            import usb_sentry.main
            importlib.reload(usb_sentry.main)
        except ImportError as e:
            self.fail(f"Failed to import usb_sentry.main: {e}")
        except Exception as e:
            # We catch other exceptions too, as import side-effects shouldn't crash
            self.fail(f"Detailed error during import: {e}")

if __name__ == "__main__":
    unittest.main()
