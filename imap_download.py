#!/usr/bin/env python3
"""
Yandex 360 IMAP → PST Exporter
================================
Connects to Yandex 360 IMAP, downloads all folders/messages,
and writes a .pst file (or .mbox fallback if libpff is unavailable).

IMAP details (Yandex 360):
  Host : imap.yandex.com
  Port : 993 (SSL)
  Auth : OAuth2 token  OR  app password (recommended — regular passwords
         are blocked by Yandex unless "less secure apps" is enabled)

Setup
-----
  pip install libpff-python tqdm          # PST output (needs libpff C lib)
  # Ubuntu/Debian: sudo apt-get install libpff-dev
  # --- OR just ---
  pip install tqdm                        # mbox fallback, no C lib needed

App password (Yandex 360):
  Yandex ID → Security → App passwords → Create → Mail
  Use that password here instead of your main password.
"""

import imaplib
import mailbox
import os
import sys
import getpass
import argparse
from tqdm import tqdm

# ── Yandex 360 IMAP defaults ─────────────────────────────────────────────────
YANDEX_HOST = "imap.yandex.com"
YANDEX_PORT = 993

# ── PST support via libpff ────────────────────────────────────────────────────
try:
    import pypff
    PST_AVAILABLE = True
except ImportError:
    PST_AVAILABLE = False


# ── CLI args ──────────────────────────────────────────────────────────────────
def get_args():
    p = argparse.ArgumentParser(
        description="Export Yandex 360 mailbox to .pst / .mbox"
    )
    p.add_argument("--user",     required=True,
                   help="Yandex 360 email, e.g. user@yourdomain.com")
    p.add_argument("--password", default=None,
                   help="App password (prompted if omitted)")
    p.add_argument("--host",     default=YANDEX_HOST,
                   help=f"IMAP host (default: {YANDEX_HOST})")
    p.add_argument("--port",     default=YANDEX_PORT, type=int,
                   help=f"IMAP port (default: {YANDEX_PORT})")
    p.add_argument("--output",   default=None,
                   help="Output file path (auto-named if omitted)")
    p.add_argument("--folders",  default=None,
                   help="Comma-separated folder list to export (default: all)")
    p.add_argument("--force-mbox", action="store_true",
                   help="Force .mbox output even if libpff is available")
    return p.parse_args()


# ── IMAP connection ───────────────────────────────────────────────────────────
def imap_connect(host, port, user, password):
    print(f"[*] Connecting to {host}:{port} (SSL) ...")
    conn = imaplib.IMAP4_SSL(host, port)
    try:
        conn.login(user, password)
    except imaplib.IMAP4.error as e:
        print(f"\n[!] Login failed: {e}")
        print("    → Make sure you are using an App Password, not your main password.")
        print("      Yandex ID → Security → App passwords → Create → Mail")
        sys.exit(1)
    print(f"[+] Authenticated as {user}")
    return conn


# ── Folder listing ────────────────────────────────────────────────────────────
def list_folders(conn):
    """Return all IMAP folder names as raw byte strings (safe for re-use in SELECT)."""
    _, folder_list = conn.list()
    folders = []
    for item in folder_list:
        # item is bytes like: b'(\\HasNoChildren) "|" &BB0E...-'
        # We want the raw name after the delimiter, preserving encoding
        decoded = item.decode(errors="replace")
        # Strip flags section: everything after the last '"' separator token
        # Format: (flags) "delim" name  OR  (flags) "delim" "name with spaces"
        # Split on delimiter character
        parts = decoded.split('"|"', 1)
        if len(parts) < 2:
            parts = decoded.split('" "', 1)  # space delimiter
        if len(parts) < 2:
            continue
        raw_name = parts[1].strip()
        # Remove surrounding quotes if present
        if raw_name.startswith('"') and raw_name.endswith('"'):
            raw_name = raw_name[1:-1]
        if raw_name:
            folders.append(raw_name)
    return folders


# ── Message fetcher ───────────────────────────────────────────────────────────
def fetch_messages(conn, folder):
    """Select folder, yield (uid_str, raw_bytes) for every message."""
    try:
        # Always quote, and escape any inner quotes in the folder name
        safe = folder.replace('\\', '\\\\').replace('"', '\\"')
        status, data = conn.select(f'"{safe}"', readonly=True)
        if status != "OK":
            print(f"  [!] Cannot select: {folder}")
            return

        total = int(data[0])
        print(f"      {total} messages")
        if total == 0:
            return

        status, uids = conn.search(None, "ALL")
        if status != "OK" or not uids[0]:
            return

        for uid in uids[0].split():
            status, msg_data = conn.fetch(uid, "(RFC822)")
            if status == "OK" and msg_data and msg_data[0]:
                yield uid.decode(), msg_data[0][1]

    except imaplib.IMAP4.error as e:
        print(f"  [!] IMAP error on '{folder}': {e}")


# ── PST writer (libpff) ───────────────────────────────────────────────────────
def write_pst(output_path, conn, folders):
    try:
        pst = pypff.file()
        # Try the new API first, fall back to integer mode constant
        try:
            pst.open(output_path, 1)  # 1 = write mode in current libpff builds
        except Exception:
            pst.open_write(output_path)

        root = pst.get_root_folder()

        for folder_name in folders:
            print(f"  [>] {folder_name}")
            pst_folder = root.add_sub_folder(folder_name)
            msgs = list(fetch_messages(conn, folder_name))
            for uid, raw in tqdm(msgs, desc=f"    {folder_name}", unit="msg", leave=False):
                try:
                    m = pst_folder.add_message()
                    m.set_message_data(raw)
                except Exception as e:
                    print(f"    [!] UID {uid} skipped: {e}")

        pst.close()
        print(f"\n[+] PST written → {output_path}")

    except Exception as e:
        print(f"\n[!] PST write failed: {e}")
        print("    libpff Python bindings on this build don't support writing.")
        print("    Falling back to mbox ...\n")
        output_mbox = output_path.replace(".pst", ".mbox")
        write_mbox(output_mbox, conn, folders)


# ── mbox writer (fallback) ────────────────────────────────────────────────────
def write_mbox(output_path, conn, folders):
    mbox = mailbox.mbox(output_path)
    mbox.lock()
    total = 0

    for folder_name in folders:
        print(f"  [>] {folder_name}")
        # Stream one message at a time — no RAM buildup, file grows immediately
        count = 0
        for uid, raw in fetch_messages(conn, folder_name):
            try:
                m = mailbox.mboxMessage(raw)
                m["X-IMAP-Folder"] = folder_name
                mbox.add(m)
                mbox.flush()
                total += 1
                count += 1
                print(f"\r      {count} messages written", end="", flush=True)
            except Exception as e:
                print(f"\n    [!] UID {uid} skipped: {e}")
        if count:
            print()  # newline after folder completes
        mbox.flush()

    mbox.unlock()
    print(f"\n[+] mbox written → {output_path}  ({total} messages)")
    print("    Import into Outlook: File → Open & Export → Import/Export")
    print("    → Import from another program or file → mbox")


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    args = get_args()
    password = args.password or getpass.getpass(f"App password for {args.user}: ")

    conn = imap_connect(args.host, args.port, args.user, password)

    print("[*] Listing folders ...")
    all_folders = list_folders(conn)

    if args.folders:
        wanted = [f.strip() for f in args.folders.split(",")]
        folders = [f for f in all_folders if f in wanted]
        missing = set(wanted) - set(folders)
        if missing:
            print(f"[!] Folders not found: {', '.join(missing)}")
    else:
        folders = all_folders

    print(f"[+] Exporting {len(folders)} folder(s): {', '.join(folders)}\n")

    safe_user = args.user.replace("@", "_").replace(".", "_")

    if PST_AVAILABLE and not args.force_mbox:
        output = args.output or f"{safe_user}.pst"
        print(f"[*] Mode: PST (libpff)  →  {output}")
        write_pst(output, conn, folders)
    else:
        if not PST_AVAILABLE:
            print("[!] libpff-python not found — using mbox fallback.")
            print("    For native PST on macOS:  brew install libpff && pip install libpff-python")
            print("    For native PST on Linux:  sudo apt-get install libpff-dev && pip install libpff-python\n")
        output = args.output or f"{safe_user}.mbox"
        print(f"[*] Mode: mbox  →  {output}")
        write_mbox(output, conn, folders)

    conn.logout()
    print("[*] Done.")


if __name__ == "__main__":
    main()
