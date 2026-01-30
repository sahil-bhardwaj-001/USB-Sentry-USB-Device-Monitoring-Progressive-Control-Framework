import sys
import os
from usb_sentry.core.policy import PolicyEngine, PolicyAction, USBDevice
from usb_sentry.core.events import DeviceType

def test_policy():
    print("Testing Policy Engine...")
    engine = PolicyEngine("policies.yaml")
    
    # Test Blocked
    bad_device = USBDevice(device_path="/dev/sdb", serial_number="0000", vendor_id="BAD", product_id="DEVICE")
    assert engine.evaluate(bad_device) == PolicyAction.BLOCK
    print("Blocklist check passed.")

    # Test Allowed
    good_device = USBDevice(device_path="/dev/sdc", serial_number="ABCDEF", vendor_id="1234", product_id="5678")
    assert engine.evaluate(good_device) == PolicyAction.ALLOW
    print("Allowlist check passed.")

    # Test Default
    unknown_device = USBDevice(device_path="/dev/sdd", serial_number="UNKNOWN", vendor_id="UNKNOWN", product_id="UNKNOWN")
    assert engine.evaluate(unknown_device) == PolicyAction.BLOCK # Default is block in our yaml
    print("Default action check passed.")

def test_imports():
    print("Testing Imports...")
    from usb_sentry.platforms.linux import LinuxUSBMonitor
    print("Linux Monitor imported successfully.")
    
    try:
        from usb_sentry.platforms.windows import WindowsUSBMonitor
        print("Windows Monitor imported successfully (module level).")
    except ImportError:
        print("Windows Monitor import failed (expected if wmi missing).")

if __name__ == "__main__":
    test_policy()
    test_imports()
    print("All basic tests passed.")
