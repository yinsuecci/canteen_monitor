import subprocess
from unittest.mock import patch
from canteen_monitor.scanner import scan


def test_command_and_no_shell():
    completed = subprocess.CompletedProcess([], 0, b"raw", b"")
    with patch("canteen_monitor.scanner.sys.platform", "win32"), patch("canteen_monitor.scanner.subprocess.run", return_value=completed) as execute:
        result = scan(7)
        assert result.stdout == b"raw" and result.error is None
        args, kwargs = execute.call_args
        assert args[0] == ["netsh", "wlan", "show", "networks", "mode=bssid"]
        assert kwargs["timeout"] == 7
        assert not kwargs.get("shell", False)


def test_timeout_preserves_partial_output():
    with patch("canteen_monitor.scanner.sys.platform", "win32"), patch("canteen_monitor.scanner.subprocess.run", side_effect=subprocess.TimeoutExpired("netsh", 2, b"partial", b"error")):
        result = scan(2)
        assert "timeout" in result.error
        assert result.stdout == b"partial" and result.stderr == b"error"


def test_os_error():
    with patch("canteen_monitor.scanner.sys.platform", "win32"), patch("canteen_monitor.scanner.subprocess.run", side_effect=FileNotFoundError("missing")):
        assert "missing" in scan().error


def test_other_platform():
    with patch("canteen_monitor.scanner.sys.platform", "linux"):
        assert "Windows" in scan().error
