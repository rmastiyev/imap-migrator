# IMAP Migrator

Download, remap, and migrate mailboxes from any IMAP server (designed for Yandex 360) to a target mail server such as PrivateEmail (Namecheap).

## Workflow

### Step 1 — Download
```bash
pip install tqdm
python3 imap_download.py --host imap.yandex.com --user user@domain.com --force-mbox
```

### Step 2a — Audit
```bash
python3 mbox_audit.py --domain yourdomain.com
```

### Step 2b — Remap folders
```bash
python3 mbox_remap.py          # dry run
python3 mbox_remap.py --apply  # apply
```

### Step 3 — Upload (coming soon)
Upload remapped .mbox files to target IMAP server.

## Notes
- Yandex 360 requires an App Password: Yandex ID → Security → App passwords → Create → Mail
- mbox files can be imported into Outlook: File → Import → MBOX File
