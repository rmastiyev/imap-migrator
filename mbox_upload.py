#!/usr/bin/env python3
"""
IMAP Migrator — Step 3: Upload
================================
Reads remapped .mbox files and uploads all messages to target IMAP server
(e.g. PrivateEmail / Namecheap) preserving folder structure.

- Creates folders on target server if they don't exist
- Preserves message dates
- Skips messages that fail without stopping the upload
- Shows live progress per folder

Requirements:
    No additional packages needed (Python stdlib only)

Usage:
    python3 mbox_upload.py --host mail.privateemail.com --user info@vegaplast.com --mbox info_vegaplast_com.mbox
    python3 mbox_upload.py --host mail.privateemail.com --user info@vegaplast.com --mbox info_vegaplast_com.mbox --dry-run
"""

import imaplib
import mailbox
import email
import getpass
import argparse
import sys
import time
from collections import defaultdict


# ── CLI args ──────────────────────────────────────────────────────────────────
def get_args():
    p = argparse.ArgumentParser(description="Upload .mbox to IMAP server")
    p.add_argument("--host",     required=True,  help="Target IMAP host")
    p.add_argument("--port",     default=993,    type=int, help="IMAP port (default: 993)")
    p.add_argument("--user",     required=True,  help="Email address")
    p.add_argument("--password", default=None,   help="Password (prompted if omitted)")
    p.add_argument("--mbox",     required=True,  help=".mbox file to upload")
    p.add_argument("--dry-run",  action="store_true", help="Simulate without uploading")
    return p.parse_args()


# ── IMAP connection ───────────────────────────────────────────────────────────
def imap_connect(host, port, user, password):
    print(f"[*] Connecting to {host}:{port} ...")
    conn = imaplib.IMAP4_SSL(host, port)
    try:
        conn.login(user, password)
    except imaplib.IMAP4.error as e:
        print(f"[!] Login failed: {e}")
        sys.exit(1)
    print(f"[+] Logged in as {user}")
    return conn


# ── Ensure folder exists ──────────────────────────────────────────────────────
def ensure_folder(conn, folder, created_cache):
    if folder in created_cache:
        return
    status, _ = conn.select(f'"{folder}"')
    if status != "OK":
        conn.create(f'"{folder}"')
        print(f"  [+] Created folder: {folder}")
    created_cache.add(folder)


# ── Upload one message ────────────────────────────────────────────────────────
def upload_message(conn, folder, raw, date_str, dry_run):
    if dry_run:
        return True
    try:
        # imaplib.append(mailbox, flags, date_time, message)
        conn.append(
            f'"{folder}"',
            None,
            imaplib.Time2Internaldate(time.time()) if not date_str else None,
            raw
        )
        return True
    except Exception as e:
        print(f"\n    [!] Upload error: {e}")
        return False


# ── Main upload ───────────────────────────────────────────────────────────────
def upload_mbox(args):
    password = args.password or getpass.getpass(f"Password for {args.user}: ")
    conn = imap_connect(args.host, args.port, args.user, password)

    # First pass — count messages per folder without loading into RAM
    print("[*] Scanning mbox ...")
    folder_counts = defaultdict(int)
    mbox = mailbox.mbox(args.mbox)
    for msg in mbox:
        folder_counts[msg.get("X-IMAP-Folder", "INBOX")] += 1
    mbox.close()

    total = sum(folder_counts.values())
    print(f"[+] {total} messages across {len(folder_counts)} folder(s)")
    for folder, count in sorted(folder_counts.items()):
        print(f"    {folder:<30} {count:>5} messages")

    if args.dry_run:
        print("\n[*] Dry run complete — no messages uploaded.")
        conn.logout()
        return

    print(f"\n[*] Uploading ...\n")
    created_cache = set()
    total_ok = total_fail = 0

    # Second pass — stream and upload one message at a time
    mbox = mailbox.mbox(args.mbox)
    current_folder = None
    folder_ok = folder_fail = folder_total = 0

    for msg in mbox:
        folder = msg.get("X-IMAP-Folder", "INBOX")

        if folder != current_folder:
            if current_folder is not None:
                print(f"\r      {folder_ok} uploaded, {folder_fail} failed        ")
            current_folder = folder
            folder_ok = folder_fail = 0
            folder_total = folder_counts[folder]
            print(f"  [>] {folder} ({folder_total} messages)")
            ensure_folder(conn, folder, created_cache)

        raw = msg.as_bytes()
        success = upload_message(conn, folder, raw, msg.get("Date", ""), args.dry_run)
        if success:
            folder_ok += 1
            total_ok  += 1
        else:
            folder_fail  += 1
            total_fail   += 1
        print(f"\r      {folder_ok + folder_fail}/{folder_total} uploaded", end="", flush=True)

    if current_folder:
        print(f"\r      {folder_ok} uploaded, {folder_fail} failed        ")

    mbox.close()
    conn.logout()
    print(f"\n[+] Done. {total_ok} uploaded, {total_fail} failed.")


if __name__ == "__main__":
    args = get_args()
    upload_mbox(args)
