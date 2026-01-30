# USB Device Control & Monitoring System

A comprehensive system to monitor and control USB devices on your system. This tool allows for blocking unauthorized devices, maintaining an allowlist, and auditing file transfers.

## Features

*   **Device Control**: Automatically block USB devices not on the allowlist.
*   **Interactive Manager**: A dedicated window to block/unblock existing devices (mice, keyboards, etc.) in real-time.
*   **Allowlist Management**: Configure trusted devices via `policies.yaml`.
*   **Cross-Platform**: Full support for **Linux** and **Windows**.
*   **File Auditing**: Monitor and log file activities on USB devices.

---

## Installation & Prerequisites

### 1. Requirements
*   **Python 3.8 or higher**: The tool runs on Python.

#### For Windows Users:
**If you do not have Python installed:**
1.  Go to [python.org/downloads](https://www.python.org/downloads/).
2.  Download the latest version for Windows.
3.  **CRITICAL**: During installation, check the box **"Add Python to PATH"**.
4.  Click "Install Now".

---

## How to Run

The tool uses a smart runner (`run.py`) that handles everything for you.
It follows this process:
1.  Checks your OS (Windows or Linux).
2.  Checks/Installs system dependencies (e.g., `dbus-x11` on Linux).
3.  Creates a virtual environment (`venv`) automatically if missing.
4.  Installs all required Python libraries (`requirements.txt`) into the `venv`.
5.  Launches the tool.

### Linux
Open your terminal in the project directory and run:

```bash
sudo python3 run.py start
```
*Note: `sudo` is required to block/unmount devices and manage system drivers.*

### Windows
1.  Open **Command Prompt** or **PowerShell** as **Administrator**.
    *   *Right-click the Start button -> Terminal (Admin) / PowerShell (Admin).*
2.  Navigate to the project folder.
3.  Run:
    ```cmd
    python run.py start
    ```
*Note: Administrator privileges are required to toggle device drivers via PnP.*

---

## Using the Interactive Device Manager

When the tool starts, it will launch a **second window** automatically. This is the **Interactive Device Manager**.

**Features:**
*   **List Devices**: Shows all connected USB devices.
*   **Block/Unblock**: Select a device index to toggle its status.
    *   **Linux**: Uses `/sys/bus/usb/.../authorized`.
    *   **Windows**: Uses `Disable-PnpDevice` (Drivers).
*   **Navigation**:
    *   Enter `0` or `b` to go back to the main menu from any prompt.
*   **Visuals**: High-contrast table and status indicators.

### Relaunching
If you accidentally close the interactive window, you do **not** need to restart the whole tool.
1.  Go to the **Main Terminal** (where the logs are scrolling).
2.  Type **`r`** and hit **Enter**.
3.  The interactive window will re-open instantly.
4.  Type **`q`** to safely quit the entire application.

---

## Structure
*   `run.py`: The intelligent launcher script.
*   `policies.yaml`: Configuration for Allow/Block rules.
*   `usb_sentry/`: Source code.
    *   `interactive.py`: The interactive CLI module.
    *   `main.py`: Core logic.
