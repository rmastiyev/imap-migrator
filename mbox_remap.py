#!/usr/bin/env python3
"""
mbox Folder Remapper
====================
Rewrites X-IMAP-Folder headers in all .mbox files, mapping Yandex
Russian folder names to standard PrivateEmail IMAP folder names.

Steps:
  1. Creates a .bak backup of each mbox before touching it
  2. Rewrites all messages with mapped folder names
  3. Prints a confirmation report: mailbox → folders → message counts

Usage:
    python3 mbox_remap.py           # dry run (no changes)
    python3 mbox_remap.py --apply   # apply changes
    python3 mbox_remap.py --dir /path/to/mboxes --apply
"""

import mailbox
import os
import shutil
import argparse
from collections import defaultdict


# ── Folder mapping ────────────────────────────────────────────────────────────
# Key   = X-IMAP-Folder value as written by the download script (raw Yandex name)
# Value = target folder name on PrivateEmail
FOLDER_MAP = {
    # Russian folders (Yandex Modified UTF-7)
    "&BB4EQgQ,BEAEMAQyBDsENQQ9BD0ESwQ1-":               "Sent",     # Отправленные
    "&BCcENQRABD0EPgQyBDgEOgQ4-":                        "Drafts",   # Черновики
    "&BCcENQRABD0EPgQyBDgEOgQ4-|template":               "Drafts",   # Черновики/template
    "&BCMENAQwBDsENQQ9BD0ESwQ1-":                        "Trash",    # Удаленные
    "&BCMENAQwBDsENQQ9BD0ESwQ1-_0":                      "Trash",    # Удаленные (duplicate)
    "&BCEEPwQwBDw-":                                     "Spam",     # Спам
    "&BB0ENQQ2BDUEOwQwBEIENQQ7BEwEPQQwBE8- &BD8EPgRHBEIEMA-": "Spam",  # Нежелательная почта
    "&BBAEQARFBDgEMg-":                                  "Archive",  # Архив
    "&BBgEQQRFBD4ENARPBEkEOAQ1-":                        "Sent",     # Исходящие → Sent
    # Outlook-style English folders
    "Deleted Items":                                     "Trash",
    "Junk E-mail":                                       "Spam",
    "Sent Items":                                        "Sent",
    # Standard folders — keep as-is
    "INBOX":                                             "INBOX",
    "Sent":                                              "Sent",
    "Drafts":                                            "Drafts",
    "Trash":                                             "Trash",
    "Spam":                                              "Spam",
    "Archive":                                           "Archive",
    # Custom — keep as-is
    "Samarat":                                           "Samarat",
}

FALLBACK = "INBOX"  # anything not in the map goes here


def remap_folder(raw):
    return FOLDER_MAP.get(raw, FALLBACK)


# ── Process one mbox ──────────────────────────────────────────────────────────
def process_mbox(path, apply=False):
    filename = os.path.basename(path)
    account  = filename.replace(".mbox", "")

    src = mailbox.mbox(path)
    messages = list(src)
    src.close()

    before = defaultdict(int)
    after  = defaultdict(int)
    remapped = 0

    new_messages = []
    for msg in messages:
        raw    = msg.get("X-IMAP-Folder", "INBOX")
        target = remap_folder(raw)
        before[raw]    += 1
        after[target]  += 1
        if raw != target:
            remapped += 1
            if apply:
                # Replace the header
                if "X-IMAP-Folder" in msg:
                    del msg["X-IMAP-Folder"]
                msg["X-IMAP-Folder"] = target
        new_messages.append(msg)

    if apply and remapped > 0:
        # Backup first
        bak = path + ".bak"
        if not os.path.exists(bak):
            shutil.copy2(path, bak)
            print(f"  [bak] {filename}.bak created")

        # Rewrite mbox
        out = mailbox.mbox(path)
        out.lock()
        out.clear()
        for msg in new_messages:
            out.add(msg)
        out.flush()
        out.unlock()

    return account, before, after, remapped, len(messages)


# ── Report ────────────────────────────────────────────────────────────────────
def print_report(account, before, after, remapped, total, apply):
    print("=" * 60)
    print(f"  Mailbox  : {account}")
    print(f"  Messages : {total}")
    print(f"  Remapped : {remapped}")
    print()

    print(f"  {'Original folder':<45} → {'Target'}")
    print(f"  {'-'*45}   {'-'*15}")
    for raw, count in sorted(before.items()):
        target = remap_folder(raw)
        changed = "  ✓" if raw != target else ""
        print(f"  {raw:<45} → {target:<15} ({count} msgs){changed}")

    print()
    print(f"  Final folder structure on PrivateEmail:")
    for folder, count in sorted(after.items()):
        print(f"    {folder:<20} {count:>5} messages")
    print()


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Remap mbox folder names for PrivateEmail")
    parser.add_argument("--dir",   default=".", help="Directory with .mbox files")
    parser.add_argument("--apply", action="store_true",
                        help="Apply changes (default is dry run)")
    args = parser.parse_args()

    mbox_files = sorted([
        os.path.join(args.dir, f)
        for f in os.listdir(args.dir)
        if f.endswith(".mbox") and not f.endswith(".lock")
    ])

    if not mbox_files:
        print("No .mbox files found.")
        return

    mode = "APPLYING CHANGES" if args.apply else "DRY RUN (use --apply to make changes)"
    print(f"\n{'='*60}")
    print(f"  mbox Folder Remapper — {mode}")
    print(f"  {len(mbox_files)} mailbox(es) found")
    print(f"{'='*60}\n")

    grand_total = grand_remapped = 0
    for path in mbox_files:
        account, before, after, remapped, total = process_mbox(path, apply=args.apply)
        print_report(account, before, after, remapped, total, args.apply)
        grand_total    += total
        grand_remapped += remapped

    print("=" * 60)
    print(f"  TOTAL: {grand_total} messages, {grand_remapped} folders remapped")
    print("=" * 60)
    if not args.apply:
        print("\n  ⚠  This was a dry run. Run with --apply to make changes.")
    else:
        print("\n  ✓  Done. Original files backed up as .mbox.bak")


if __name__ == "__main__":
    main()
