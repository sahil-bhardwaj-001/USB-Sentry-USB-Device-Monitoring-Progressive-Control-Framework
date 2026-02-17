#!/usr/bin/env python3
import sys
import os
import signal
import subprocess
import ctypes
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, IntPrompt
import time
import json
from collections import deque

# Conditional imports
if sys.platform == 'linux':
    import pyudev
elif sys.platform == 'win32':
    import wmi
    import pythoncom

console = Console()
blocked_paths = set() # Linux: paths, Windows: InstanceIDs

def list_devices():
    """List currently connected usb devices with indexes."""
    table = Table(title="Connected USB Devices (Interactive Mode)")
    table.add_column("Index", style="bold cyan", justify="right")
    table.add_column("Device", style="bold white", overflow="fold")
    table.add_column("VID:PID", style="blue")
    table.add_column("State", style="bold")
    table.add_column("Path/ID", style="white", overflow="fold")

    devices = []
    
    if sys.platform == 'linux':
        try:
            context = pyudev.Context()
            i = 1
            for device in context.list_devices(subsystem='usb'):
                if device.device_type != 'usb_device':
                    continue
                
                vid = device.get('ID_VENDOR_ID') or "????"
                pid = device.get('ID_MODEL_ID') or "????"
                model = device.get('ID_MODEL') or device.get('ID_USB_MODEL') or "Unknown"
                vendor = device.get('ID_VENDOR') or "Unknown"
                
                # Check authorization state
                auth_path = os.path.join(device.sys_path, 'authorized')
                is_authorized = True
                try:
                    with open(auth_path, 'r') as f:
                        is_authorized = f.read().strip() == '1'
                except:
                    pass
                
                state = "[green]Active[/green]" if is_authorized else "[red]BLOCKED[/red]"
                
                table.add_row(
                    str(i),
                    f"{vendor} {model}",
                    f"{vid}:{pid}",
                    state,
                    device.sys_path
                )
                devices.append({'path': device.sys_path, 'authorized': is_authorized, 'auth_file': auth_path, 'platform': 'linux'})
                i += 1
                
        except ImportError:
            console.print("[red]Error: pyudev not installed.[/red]")

    elif sys.platform == 'win32':
        try:
            pythoncom.CoInitialize()
            c = wmi.WMI()
            i = 1
            # Scan for PnPEntities that are USB devices
            for item in c.Win32_PnPEntity(ConfigManagerErrorCode=0):
                if item.DeviceID and "USB" in item.DeviceID:
                     # Filter for actual devices? (Has VID/PID)
                     if "VID" not in item.DeviceID:
                         continue

                     name = item.Name or item.Description or "Unknown"
                     
                     # Parse VID/PID
                     vid = "????"
                     pid = "????"
                     try:
                         if "VID_" in item.DeviceID and "PID_" in item.DeviceID:
                             vid = item.DeviceID.split("VID_")[1].split("&")[0]
                             pid = item.DeviceID.split("PID_")[1].split("&")[0]
                     except:
                         pass

                     # Status: ConfigManagerErrorCode 0=OK, 22=Disabled
                     # But we are filtering for error code 0 above? 
                     # Wait, we need to see BLOCKED devices too.
                     # So remove ConfigManagerErrorCode=0 filter from query?
                     pass
            
            # Re-query properly to find ALL including disabled
            for item in c.Win32_PnPEntity():
                if not item.DeviceID or "USB" not in item.DeviceID or "VID" not in item.DeviceID:
                    continue
                    
                vid = "????"
                pid = "????"
                try:
                    if "VID_" in item.DeviceID and "PID_" in item.DeviceID:
                            vid = item.DeviceID.split("VID_")[1].split("&")[0]
                            pid = item.DeviceID.split("PID_")[1].split("&")[0]
                except:
                    pass
                
                # CM_PROB_DISABLED = 22
                is_disabled = (item.ConfigManagerErrorCode == 22)
                state = "[red]BLOCKED[/red]" if is_disabled else "[green]Active[/green]"
                
                table.add_row(
                    str(i),
                    item.Name or "Unknown",
                    f"{vid}:{pid}",
                    state,
                    item.DeviceID
                )
                devices.append({
                    'id': item.DeviceID, 
                    'authorized': not is_disabled, 
                    'platform': 'win32'
                })
                i += 1

        except Exception as e:
            console.print(f"[red]Error scanning windows devices: {e}[/red]")
            
    console.print(table)
    return devices

def toggle_block(device_info, block=True):
    """Block or Unblock a device."""
    
    if sys.platform == 'linux':
        path = device_info['auth_file']
        try:
            val = '0' if block else '1'
            with open(path, 'w') as f:
                f.write(val)
                
            action = "BLOCKED" if block else "UNBLOCKED"
            color = "red" if block else "green"
            console.print(f"[{color}]Device successfully {action}.[/{color}]")
            
            if block:
                blocked_paths.add(path)
            elif path in blocked_paths:
                blocked_paths.remove(path)
                
        except PermissionError:
            console.print("[bold red]Permission Denied! Please run with sudo.[/bold red]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

    elif sys.platform == 'win32':
        dev_id = device_info['id']
        try:
            cmd = "Disable-PnpDevice" if block else "Enable-PnpDevice"
            # PowerShell command requires admin
            ps_script = f"{cmd} -InstanceId '{dev_id}' -Confirm:$false"
            
            console.print(f"[yellow]Running PowerShell: {cmd}...[/yellow]")
            result = subprocess.run(
                ["powershell", "-Command", ps_script], 
                capture_output=True, text=True
            )
            
            if result.returncode == 0:
                action = "BLOCKED" if block else "UNBLOCKED"
                color = "red" if block else "green"
                console.print(f"[{color}]Device successfully {action}.[/{color}]")
                
                if block:
                    blocked_paths.add(dev_id)
                elif dev_id in blocked_paths:
                    blocked_paths.remove(dev_id)
            else:
                console.print(f"[red]PowerShell Error:[/red] {result.stderr}")

        except Exception as e:
            console.print(f"[red]Error executing PowerShell: {e}[/red]")

def restore_all():
    """Restore all blocked devices on exit."""
    if not blocked_paths:
        return
        
    console.print("\n[yellow]Restoring blocked devices before exit...[/yellow]")
    
    if sys.platform == 'linux':
        for path in list(blocked_paths):
            try:
                with open(path, 'w') as f:
                    f.write('1')
                console.print(f"[green]Restored {path}[/green]")
            except:
                pass
                
    elif sys.platform == 'win32':
        for dev_id in list(blocked_paths):
            try:
                ps_script = f"Enable-PnpDevice -InstanceId '{dev_id}' -Confirm:$false"
                subprocess.run(["powershell", "-Command", ps_script], stdout=subprocess.DEVNULL)
                console.print(f"[green]Restored {dev_id}[/green]")
            except:
                pass

def view_logs(lines=20):
    """View recent logs."""
    from .core.logger import log_file_path
    
    if not log_file_path.exists():
        console.print("[red]Log file not found.[/red]")
        return

    try:
        # Read last N lines
        with open(log_file_path, 'r') as f:
            # simple tail implementation
            q = deque(f, maxlen=lines)
            
        table = Table(title=f"Recent Logs (Last {lines})")
        table.add_column("Time", style="cyan")
        table.add_column("Level", style="bold")
        table.add_column("Message", style="white")
        
        for line in q:
            try:
                entry = json.loads(line)
                
                # Colorize level
                lvl = entry.get('level', 'INFO')
                lvl_style = "green"
                if lvl == "WARNING": lvl_style = "yellow"
                elif lvl == "ERROR": lvl_style = "red"
                elif lvl == "CRITICAL": lvl_style = "bold red"
                
                table.add_row(
                    entry.get('timestamp', '')[11:19], # HH:MM:SS
                    f"[{lvl_style}]{lvl}[/{lvl_style}]",
                    entry.get('message', '')
                )
            except json.JSONDecodeError:
                continue
                
        console.print(table)
        input("\nPress Enter to return...")
        
    except Exception as e:
        console.print(f"[red]Error reading logs: {e}[/red]")

def main():
    console.clear()
    banner = r"""
[bold cyan] _   _ ____  ____            ____             _              
| | | / ___|| __ )          / ___|  ___ _ __ | |_ _ __ _   _ 
| | | \___ \|  _ \   _____  \___ \ / _ \ '_ \| __| '__| | | |
| |_| |___) | |_) | |_____|  ___) |  __/ | | | |_| |  | |_| |
 \___/|____/|____/          |____/ \___|_| |_|\__|_|   \__, |
                                                       |___/ [/bold cyan]
"""
    console.print(banner)
    console.print("[italic]Use this terminal to block/unblock existing devices.[/italic]")
    
    # PID File Handling
    from .core.logger import log_file_path
    pid_file = log_file_path.parent / "interactive.pid"
    
    try:
        with open(pid_file, 'w') as f:
            f.write(str(os.getpid()))
    except Exception as e:
        console.print(f"[yellow]Warning: Could not write PID file: {e}[/yellow]")

    # Handle cleanup
    def cleanup(sig, frame):
        try:
            if pid_file.exists():
                pid_file.unlink()
        except:
            pass
        restore_all()
        sys.exit(0)
    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)


    while True:
        console.print("\n[bold]Menu:[/bold]")
        console.print("1. List Devices")
        console.print("2. Block a Device")
        console.print("3. Unblock a Device")
        console.print("3. Unblock a Device")
        console.print("4. Exit (Restores all devices)")
        console.print("5. View Logs")
        
        choice = Prompt.ask("Select an option", choices=["1", "2", "3", "4", "5"], show_default=False)
        
        if choice == "1":
            list_devices()
        
        elif choice == "2":
            devices = list_devices()
            if not devices:
                continue
            
            console.print("[italic]Enter '0' or 'b' to go back to menu[/italic]")
            val = Prompt.ask("Enter Index to BLOCK", show_default=False)
            if val in ('0', 'b', 'B'):
                continue
                
            try:
                idx = int(val)
                if 1 <= idx <= len(devices):
                    toggle_block(devices[idx-1], block=True)
                else:
                    console.print("[red]Invalid index.[/red]")
            except ValueError:
                console.print("[red]Invalid input.[/red]")
                pass
                
        elif choice == "3":
            devices = list_devices()
            if not devices:
                continue
            
            console.print("[italic]Enter '0' or 'b' to go back to menu[/italic]")
            val = Prompt.ask("Enter Index to UNBLOCK", show_default=False)
            if val in ('0', 'b', 'B'):
                continue

            try:
                idx = int(val)
                if 1 <= idx <= len(devices):
                    toggle_block(devices[idx-1], block=False)
                else:
                    console.print("[red]Invalid index.[/red]")
            except ValueError:
                console.print("[red]Invalid input.[/red]")
                pass
                
        elif choice == "4":
            try:
                if pid_file.exists():
                    pid_file.unlink()
            except:
                pass
            restore_all()
            break
            
        elif choice == "5":
            view_logs(30)
            
if __name__ == "__main__":
    if sys.platform == 'linux':
        if os.geteuid() != 0:
            console.print("[bold red]This tool requires root privileges (sudo).[/bold red]")
            sys.exit(1)
            
    elif sys.platform == 'win32':
        # Check admin on Windows
        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin()
        except:
            is_admin = False
            
        if not is_admin:
            console.print("[bold red]This tool requires Administrator privileges.[/bold red]")
            console.print("[red]Please right-click the terminal and select 'Run as Administrator'.[/red]")
            input("Press Enter to exit...")
            sys.exit(1)
            
    main()
