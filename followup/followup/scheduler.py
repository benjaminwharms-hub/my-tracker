"""Schedule the daily run on the client's own computer.

    Windows: a Task Scheduler task named "FollowupEmails". It is set to
             "run as soon as possible after a missed start", so if the
             computer was off at 9:00 it runs when it's next switched on.
    Mac:     a launchd agent (~/Library/LaunchAgents/com.followup.daily.plist).
             If the Mac was asleep at the scheduled time, it runs on wake.

Both run:  <python> run.py --all --log-file logs/daily.log
Each run's output is added to logs/daily.log, which is handy when something goes wrong.

The build_* functions only create text, so they can be tested on any computer.
install()/uninstall() actually change the computer.
"""

import os
import platform
import plistlib
import subprocess
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
TASK_NAME = "FollowupEmails"
MAC_LABEL = "com.followup.daily"
LOG_FILE = APP_DIR / "logs" / "daily.log"


def run_command_args(python_exe: Path, app_dir: Path = APP_DIR) -> list:
    """The command the scheduler runs each day."""
    return [str(python_exe), str(app_dir / "run.py"), "--all", "--log-file", str(app_dir / "logs" / "daily.log")]


# ---------------------------------------------------------------- Windows

def _ps_quote(text: str) -> str:
    """Quote a value for PowerShell: wrap in '...' and double any ' inside."""
    return "'" + str(text).replace("'", "''") + "'"


def build_windows_script(python_exe: Path, hour: int, minute: int, app_dir: Path = APP_DIR) -> str:
    """PowerShell that (re)creates the daily task for the current user."""
    exe, *args = run_command_args(python_exe, app_dir)
    arg_string = " ".join(f'"{a}"' for a in args)  # Windows command-line quoting
    return "\n".join([
        f"$action = New-ScheduledTaskAction -Execute {_ps_quote(exe)} -Argument {_ps_quote(arg_string)} "
        f"-WorkingDirectory {_ps_quote(app_dir)}",
        f"$trigger = New-ScheduledTaskTrigger -Daily -At {hour:02d}:{minute:02d}",
        "$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries "
        "-DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1)",
        f"Register-ScheduledTask -TaskName {_ps_quote(TASK_NAME)} -Action $action -Trigger $trigger "
        f"-Settings $settings -Description 'Daily customer follow-up emails' -Force | Out-Null",
    ])


def windows_python(app_dir: Path = APP_DIR) -> Path:
    """pythonw.exe runs without popping up a black console window every morning."""
    return app_dir / ".venv" / "Scripts" / "pythonw.exe"


# ---------------------------------------------------------------- Mac

def mac_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{MAC_LABEL}.plist"


def build_mac_plist(python_exe: Path, hour: int, minute: int, app_dir: Path = APP_DIR) -> bytes:
    log = str(app_dir / "logs" / "launchd.log")
    return plistlib.dumps({
        "Label": MAC_LABEL,
        "ProgramArguments": run_command_args(python_exe, app_dir),
        "WorkingDirectory": str(app_dir),
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "StandardOutPath": log,
        "StandardErrorPath": log,
    })


def mac_folder_warning(app_dir: Path = APP_DIR) -> str:
    """macOS blocks background jobs from reading Desktop, Documents and Downloads.

    Returns a warning if the app is in one of those folders, otherwise "".
    """
    home = Path.home()
    for name in ("Desktop", "Documents", "Downloads", "Library/Mobile Documents"):
        try:
            app_dir.resolve().relative_to(home / name)
            return (f"This folder is inside ~/{name}. macOS won't let the daily job read files there. "
                    f"Move the folder to {home / 'FollowupEmails'} and run the installer again.")
        except ValueError:
            continue
    return ""


# ---------------------------------------------------------------- install / remove

def install(hour: int = 9, minute: int = 0) -> str:
    """Create (or replace) the daily schedule on this computer. Returns a short description."""
    (APP_DIR / "logs").mkdir(exist_ok=True)
    system = platform.system()

    if system == "Windows":
        script = build_windows_script(windows_python(), hour, minute)
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script], check=True)
        return f"Windows Task Scheduler task '{TASK_NAME}', every day at {hour:02d}:{minute:02d}"

    if system == "Darwin":
        warning = mac_folder_warning()
        if warning:
            raise RuntimeError(warning)
        plist = mac_plist_path()
        plist.parent.mkdir(parents=True, exist_ok=True)
        plist.write_bytes(build_mac_plist(APP_DIR / ".venv" / "bin" / "python", hour, minute))
        domain = f"gui/{os.getuid()}"
        subprocess.run(["launchctl", "bootout", domain, str(plist)], capture_output=True)  # remove old one, if any
        subprocess.run(["launchctl", "bootstrap", domain, str(plist)], check=True)
        return f"Mac launchd job '{MAC_LABEL}', every day at {hour:02d}:{minute:02d}"

    # Linux and others: print a cron line for the operator to add by hand.
    cmd = " ".join(f'"{a}"' for a in run_command_args(Path(sys.executable)))
    raise RuntimeError(f"Automatic scheduling supports Windows and Mac. On this system, add this line "
                       f"with 'crontab -e':\n{minute} {hour} * * * {cmd}")


def uninstall() -> str:
    system = platform.system()
    if system == "Windows":
        subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"Unregister-ScheduledTask -TaskName {_ps_quote(TASK_NAME)} -Confirm:$false"], check=False)
        return "Removed the Windows scheduled task."
    if system == "Darwin":
        plist = mac_plist_path()
        subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(plist)], capture_output=True)
        plist.unlink(missing_ok=True)
        return "Removed the Mac launchd job."
    return "Nothing to remove on this system (remove the cron line by hand)."


def run_now() -> None:
    """Ask the scheduler to run the job once right now (to prove it works)."""
    system = platform.system()
    if system == "Windows":
        subprocess.run(["schtasks", "/Run", "/TN", TASK_NAME], check=True, capture_output=True)
    elif system == "Darwin":
        subprocess.run(["launchctl", "kickstart", f"gui/{os.getuid()}/{MAC_LABEL}"], check=True)
