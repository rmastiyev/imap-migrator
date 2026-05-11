#!/usr/bin/env python3
"""
IMAP Email Migrator
Copies all messages (preserving folders and flags) from one IMAP server to another.
"""

import imaplib
import email
import sys
import time
from getpass import getpass

# ── Configuration ──────────────────────────────────────────────────────────────

SOURCE = {
    "host": "mail.source-server.com",
    "port": 993,
    "ssl":  True,
    "user": "user@source-server.com",
    "pass": "",          # leave blank to prompt
}

DEST = {
    "host": "mail.dest-server.com",
    "port": 993,
    "ssl":  True,
    "user": "user@dest-server.com",
    "pass": "",          # leave blank to prompt
}

SKIP_FOLDERS = []        # e.g. ["Spam", "Trash"] to exclude
DELAY        = 0.05      # seconds between appends (be kind to the server)

# ── Helpers ────────────────────────────────────────────────────────────────────

def connect(cfg: dict, label: str) -> imaplib.IMAP4:
    print(f"\n[{label}] Connecting to {cfg['host']}:{cfg['port']} …")
    if cfg["ssl"]:
        conn = imaplib.IMAP4_SSL(cfg["host"], cfg["port"])
    else:
        conn = imaplib.IMAP4(cfg["host"], cfg["port"])

    pwd = cfg["pass"] or getpass(f"[{label}] Password for {cfg['user']}: ")
    conn.login(cfg["user"], pwd)
    print(f"[{label}] Logged in as {cfg['user']}")
    return conn


def list_folders(conn: imaplib.IMAP4) -> list[str]:
    status, data = conn.list()
    folders = []
    for item in data:
        if isinstance(item, bytes):
            # parse:  (\HasNoChildren) "/" "INBOX"
            parts = item.decode().split('"')
            name  = parts[-1].strip().strip('"') if len(parts) >= 2 else item.decode().split()[-1]
            folders.append(name)
    return folders


def ensure_folder(conn: imaplib.IMAP4, folder: str) -> None:
    """Create folder on destination if it doesn't exist."""
    status, _ = conn.select(f'"{folder}"')
    if status != "OK":
        conn.create(f'"{folder}"')
        conn.subscribe(f'"{folder}"')
        print(f"  Created folder: {folder}")


def migrate_folder(src: imaplib.IMAP4, dst: imaplib.IMAP4, folder: str) -> tuple[int, int]:
    """Copy all messages from one folder. Returns (copied, failed)."""
    # Select source folder
    status, data = src.select(f'"{folder}"', readonly=True)
    if status != "OK":
        print(f"  [SKIP] Cannot select source folder: {folder}")
        return 0, 0

    total = int(data[0])
    if total == 0:
        print(f"  (empty)")
        return 0, 0

    # Fetch all message IDs
    status, ids = src.search(None, "ALL")
    if status != "OK" or not ids[0]:
        return 0, 0

    msg_ids = ids[0].split()
    copied, failed = 0, 0

    ensure_folder(dst, folder)

    for i, mid in enumerate(msg_ids, 1):
        try:
            # Fetch raw message + flags
            status, msg_data = src.fetch(mid, "(RFC822 FLAGS)")
            if status != "OK":
                failed += 1
                continue

            raw      = None
            flags    = b""
            for part in msg_data:
                if isinstance(part, tuple):
                    raw   = part[1]
                elif isinstance(part, bytes) and b"FLAGS" in part:
                    flags = part

            if raw is None:
                failed += 1
                continue

            # Parse flags (keep \Seen, \Answered, \Flagged, \Deleted, \Draft)
            imap_flags = b""
            for flag in [b"\\Seen", b"\\Answered", b"\\Flagged", b"\\Draft"]:
                if flag in flags:
                    imap_flags += flag + b" "

            # Append to destination
            dst.append(f'"{folder}"', imap_flags.strip().decode() or None, imaplib.Time2Internaldate(time.time()), raw)

            copied += 1
            if i % 50 == 0 or i == len(msg_ids):
                print(f"  {i}/{total} messages copied …", end="\r")

            time.sleep(DELAY)

        except Exception as e:
            print(f"\n  [WARN] Message {mid.decode()} failed: {e}")
            failed += 1

    print(f"  Done: {copied} copied, {failed} failed.      ")
    return copied, failed

# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    src = connect(SOURCE, "SOURCE")
    dst = connect(DEST,   "DEST")

    folders = list_folders(src)
    print(f"\nFound {len(folders)} folder(s) on source server.")

    total_copied = total_failed = 0

    for folder in folders:
        if folder in SKIP_FOLDERS:
            print(f"\n[SKIP] {folder}")
            continue

        print(f"\n── {folder} ──")
        c, f = migrate_folder(src, dst, folder)
        total_copied += c
        total_failed += f

    src.logout()
    dst.logout()

    print(f"\n{'─'*40}")
    print(f"Migration complete.")
    print(f"  Total copied : {total_copied}")
    print(f"  Total failed : {total_failed}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborted by user.")
        sys.exit(1)
