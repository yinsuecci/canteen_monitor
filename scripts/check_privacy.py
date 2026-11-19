"""Fail closed on private artifacts in Git snapshots; never print secret values."""
import argparse
from pathlib import PurePosixPath
import re
import subprocess


def git(*args):
    return subprocess.check_output(["git", *args])


PATTERNS = {
    "private key": re.compile(rb"-----BEGIN (?:[A-Z ]+)?PRIVATE KEY-----"),
    "credential": re.compile(rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[A-Z0-9]{16})"),
    "personal path": re.compile(rb"(?:[A-Z]:[\\/]Users[\\/]|/Users/|/home/)[A-Za-z0-9_\x80-\xff][^\s<>]*", re.I),
}
MAC = re.compile(rb"\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b", re.I)


def inspect(path, content):
    name = PurePosixPath(path).name.lower()
    forbidden = (path.startswith(("data/", "docs/screenshots/"))
                 or name.startswith(".env") and name != ".env.example"
                 or name.endswith((".db", ".sqlite", ".sqlite3", ".pem", ".key", ".p12", ".pfx", ".pcap", ".pcapng"))
                 or "-credentials." in name or name.endswith(".local.toml"))
    findings = ["private artifact"] if forbidden else []
    if b"\x00" in content:
        findings.append("binary artifact requires explicit review")
    findings.extend(label for label, pattern in PATTERNS.items() if pattern.search(content))
    # All examples must use locally administered addresses, not real vendor OUIs.
    if any(not (int(match[0:2], 16) & 2) for match in MAC.findall(content)):
        findings.append("non-synthetic AP identifier")
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", action="store_true", help="Check all reachable commits and author emails")
    args = parser.parse_args()
    snapshots = git("rev-list", "--all").decode().splitlines() if args.history else [None]
    checked, errors = set(), []
    for ref in snapshots:
        if ref:
            entries = git("ls-tree", "-rz", ref).split(b"\0")
            rows = [(entry.split(b"\t", 1)[1], entry.split(b"\t", 1)[0].split()[2]) for entry in entries if entry]
            emails = git("show", "-s", "--format=%ae%n%ce", ref).decode().splitlines()
            if any(email != "noreply@github.com" and not email.endswith("@users.noreply.github.com") for email in emails):
                errors.append(f"{ref[:7]}: personal commit email")
        else:
            entries = git("ls-files", "--stage", "-z").split(b"\0")
            rows = [(entry.split(b"\t", 1)[1], entry.split()[1]) for entry in entries if entry]
        for raw_path, oid in rows:
            path = raw_path.decode("utf-8")
            key = (path, oid)
            if key in checked:
                continue
            checked.add(key)
            for issue in inspect(path, git("cat-file", "blob", oid.decode())):
                errors.append(f"{path}: {issue}")
    for error in errors:
        print(error)
    print(f"Checked {len(checked)} file versions; {len(errors)} findings.")
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
