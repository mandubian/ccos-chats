ccos-chats
===========

This repository is an exported archive of the `chats/` directory from the main
`ccos` repository.

Original repo: https://github.com/mandubian/ccos
This archive (this repo): https://github.com/mandubian/ccos-chats

Contents
--------
- Compressed chat JSONs: `chat_<n>.json.zst` (zstd) or `chat_<n>.json.gz` (gzip)
- Per-chat metadata: `chat_<n>.json.meta.json` (original size, compressed size, sha256, compression)
- Markdown renderings: `chat_<n>.md` for human-readable exports
- `scripts/` contains helper tools (e.g. `compress_new_chats.py`)

Purpose
-------
This repository stores the chat archives outside the main `ccos` repo to reduce
repository size and LFS use. Files are compressed and accompanied by metadata
so the original content can be verified and restored if needed.

Quick verification
------------------
From this repo root you can:

- List high-level contents and disk usage:

```bash
ls -lah
du -sh .
```

- Verify a sample compressed file against its metadata:

```bash
# compute sha256 of compressed file
sha256sum chat_100.json.zst
# inspect metadata (contains sha256 of compressed file)
jq . chat_100.json.meta.json
```

- If you want to re-compress or add new raw `*.json` files, use the helper:

```bash
# dry-run first
./scripts/compress_new_chats.py --dir . --dry-run
# then compress (zstd preferred if available)
./scripts/compress_new_chats.py --dir . --workers 4
```

Notes about git & LFS
---------------------
- This archive was created from the `ccos` repository. The initial import is
  a single commit that contains the compressed artifacts and metadata.
- No remote is required, but you can add one and push this repo if you want the
  archive stored remotely:

```bash
git remote add origin <your-remote-url>
git branch -M main
git push -u origin main
```

- The `ccos` main repo still contains the original chat JSONs. After you
  verify this archive you can remove the original files from the main repo in
  a normal commit:

```bash
# in the main repo
git rm chats/*.json
git commit -m "Move chats archive to ccos-chats"
git push
```

- If your goal is to reclaim server-side storage and LFS quota, you will need
  to rewrite history and force-push the cleaned mirror. This is destructive —
  use `scripts/clean_main_repo_history.sh --mirror-dir /tmp/ccos-mirror --dry-run`
  to preview the changes and only run with `--force-push` after backups.

Security & integrity
--------------------
- Each compressed artifact has a corresponding `.meta.json` with a `sha256` of
  the compressed file. Use that to verify integrity before trusting restores.
- Keep a secure backup of this archive before doing any destructive history
  operations on the original repo.

Contact
-------
If you want, I can:
- Add a `.gitattributes` for LFS tracking in this repo
- Push this repo to a remote for you (provide the URL)
- Run the history-clean mirror dry-run and report back

