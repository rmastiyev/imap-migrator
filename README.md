# IMAP Migrator

A set of Python scripts to migrate email from any IMAP server to another — designed for **Yandex 360 → PrivateEmail (Namecheap)** but works with any IMAP source/destination.

## Workflow

```
[Yandex 360]
     │
     ▼
imap_download.py   →   .mbox files (one per mailbox)
     │
     ▼
mbox_audit.py      →   verify folders, message counts, sizes
     │
     ▼
mbox_remap.py      →   normalize folder names to standard IMAP
     │
     ▼
mbox_upload.py     →   upload to target IMAP server
     │
     ▼
[PrivateEmail]
```

## Scripts

### `imap_download.py` — Download
Connects to source IMAP server and downloads all mail to local `.mbox` files.
Tags each message with `X-IMAP-Folder` to preserve folder structure.

```bash
python3 imap_download.py --host imap.yandex.com --user user@domain.com --force-mbox
```

Options:
- `--host` — IMAP server hostname
- `--port` — IMAP port (default: 993 SSL)
- `--user` — email address
- `--password` — password (prompted if omitted)
- `--output` — output file path (auto-named if omitted)
- `--folders` — comma-separated folder list (default: all)
- `--force-mbox` — force mbox output (recommended; libpff write support is limited on macOS)

> **Yandex 360:** Use an App Password, not your main password.
> Yandex ID → Security → App passwords → Create → Mail

---

### `mbox_audit.py` — Audit
Reads all `.mbox` files and produces a summary report: folders, message counts, date ranges, sizes, and a DNS/mailbox checklist for the target server.

```bash
python3 mbox_audit.py
python3 mbox_audit.py --domain yourdomain.com --verbose
```

Options:
- `--dir` — directory containing `.mbox` files (default: current)
- `--domain` — domain for DNS checklist
- `--verbose` — show sender/recipient domain breakdown

---

### `mbox_remap.py` — Remap Folders
Rewrites `X-IMAP-Folder` headers to map provider-specific folder names to standard IMAP names (`Sent`, `Drafts`, `Trash`, `Spam`, `Archive`).

Handles:
- Yandex 360 Russian folder names (Modified UTF-7 encoded)
- Outlook-style names (`Sent Items`, `Deleted Items`, `Junk E-mail`)

```bash
python3 mbox_remap.py           # dry run — shows what will change
python3 mbox_remap.py --apply   # apply changes (backs up originals as .mbox.bak)
```

Options:
- `--dir` — directory with `.mbox` files (default: current)
- `--apply` — apply changes (default is dry run)

> Edit `FOLDER_MAP` in the script to customise mappings for your provider.

---

### `mbox_upload.py` — Upload
Reads remapped `.mbox` files and uploads all messages to the target IMAP server, creating folders as needed.

```bash
python3 mbox_upload.py --host mail.privateemail.com --user user@domain.com --mbox user_domain_com.mbox
python3 mbox_upload.py --host mail.privateemail.com --user user@domain.com --mbox user_domain_com.mbox --dry-run
```

Options:
- `--host` — target IMAP hostname
- `--port` — IMAP port (default: 993)
- `--user` — email address
- `--password` — password (prompted if omitted)
- `--mbox` — `.mbox` file to upload
- `--dry-run` — scan and report without uploading

---

## Requirements

```bash
pip install tqdm   # only needed for imap_download.py
```

All other scripts use Python stdlib only. Tested on macOS with Python 3.9+.

---

## DNS Records (PrivateEmail / Namecheap)

| Type  | Name                    | Value                                      |
|-------|-------------------------|--------------------------------------------|
| MX    | @                       | mx1.privateemail.com (priority 10)         |
| MX    | @                       | mx2.privateemail.com (priority 20)         |
| TXT   | @                       | v=spf1 include:spf.privateemail.com ~all   |
| TXT   | default._domainkey      | v=DKIM1;k=rsa;p=... (from Namecheap panel) |
| TXT   | _dmarc                  | v=DMARC1; p=none; rua=mailto:admin@domain  |

Verify with:
```bash
dig MX yourdomain.com +short
dig TXT yourdomain.com +short
dig TXT default._domainkey.yourdomain.com +short
```

---

## License

MIT
