import ctypes
import locale
import subprocess
import sys
from dataclasses import dataclass


@dataclass
class ScanResult:
    stdout: bytes = b""
    stderr: bytes = b""
    returncode: int | None = None
    error: str | None = None


def decode_output(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    encodings = ["utf-8-sig"]
    if sys.platform == "win32":
        encodings.append(f"cp{ctypes.windll.kernel32.GetOEMCP()}")
    encodings.extend([locale.getpreferredencoding(False), "gb18030"])
    for encoding in encodings:
        try:
            return data.decode(encoding)
        except (UnicodeError, LookupError):
            continue
    raise ValueError("Cannot decode netsh output; raw bytes are retained")


def scan(timeout: int = 30) -> ScanResult:
    if sys.platform != "win32":
        return ScanResult(error="Live netsh scanning requires Windows")
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "networks", "mode=bssid"],
            capture_output=True, timeout=timeout, check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return ScanResult(result.stdout, result.stderr, result.returncode,
                          None if result.returncode == 0 else f"netsh exit code {result.returncode}")
    except subprocess.TimeoutExpired as exc:
        return ScanResult(exc.stdout or b"", exc.stderr or b"", error=f"netsh timeout after {timeout}s")
    except OSError as exc:
        return ScanResult(error=str(exc))
