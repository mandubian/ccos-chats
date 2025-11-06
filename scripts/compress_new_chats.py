#!/usr/bin/env python3
"""
compress_new_chats.py

Scan a chats directory for new `*.json` files that do not have a compressed
artifact (`*.json.zst` or `*.json.gz`) and compress them. Writes a matching
`{name}.meta.json` with metadata (original/compressed size, sha256 and compression).

Usage examples:
  # Dry-run against the repo root
  ./scripts/compress_new_chats.py --dir . --dry-run

  # Compress using zstd (preferred if available), 4 workers
  ./scripts/compress_new_chats.py --dir . --use-zstd --workers 4

The script is intentionally conservative: it will skip files that already have
compressed outputs or meta files unless --force is supplied.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def run(cmd, check=True, capture=False):
    if capture:
        return subprocess.run(cmd, shell=True, check=check, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return subprocess.run(cmd, shell=True, check=check)


def detect_zstd_binary() -> bool:
    try:
        subprocess.run(["zstd", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except FileNotFoundError:
        return False


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def compress_with_zstd_binary(src: Path, dst: Path) -> None:
    cmd = ["zstd", "-19", "-T0", str(src), "-o", str(dst)]
    subprocess.run(cmd, check=True)


def compress_with_gzip(src: Path, dst: Path) -> None:
    import gzip

    with src.open("rb") as f_in, gzip.open(dst, "wb", compresslevel=9) as f_out:
        shutil.copyfileobj(f_in, f_out)


def write_meta(out_dir: Path, basename: str, original_size: int, compressed_size: int, sha256: str, compression: str) -> None:
    meta = {
        "file": basename,
        "original_size": original_size,
        "compressed_size": compressed_size,
        "sha256": sha256,
        "compression": compression,
        "created_at": time.time(),
    }
    meta_path = out_dir / f"{basename}.meta.json"
    with meta_path.open("w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)


def process_file(f: Path, out_dir: Path, use_zstd: bool, dry_run: bool, force: bool) -> tuple[str, int, int]:
    basename = f.name
    if use_zstd:
        out_name = f"{basename}.zst"
        compression = "zstd"
    else:
        out_name = f"{basename}.gz"
        compression = "gzip"
    out_path = out_dir / out_name
    meta_path = out_dir / f"{basename}.meta.json"

    # Skip if compressed already exists unless force
    if out_path.exists() and not force:
        return (f"SKIP (already compressed): {basename}", 0, 0)
    if meta_path.exists() and not force:
        return (f"SKIP (meta exists): {basename}", 0, 0)

    original_size = f.stat().st_size

    if dry_run:
        return (f"[DRY] Would compress {f} -> {out_path} using {compression}", original_size, 0)

    # Perform compression
    if use_zstd:
        compress_with_zstd_binary(f, out_path)
    else:
        compress_with_gzip(f, out_path)

    compressed_size = out_path.stat().st_size
    sha = sha256_file(out_path)
    write_meta(out_dir, basename, original_size, compressed_size, sha, compression)
    return (f"COMPRESSED: {basename}", original_size, compressed_size)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Compress new chat JSON files in a chats folder and write meta files.")
    parser.add_argument("--dir", type=Path, default=Path("."), help="Directory containing chat JSONs (default: .)")
    parser.add_argument("--use-zstd", action="store_true", help="Force use zstd binary; if not present the script will error unless --use-gzip is set")
    parser.add_argument("--use-gzip", action="store_true", help="Force use gzip compression instead of zstd")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without writing files")
    parser.add_argument("--force", action="store_true", help="Overwrite existing compressed/meta files")
    parser.add_argument("--workers", type=int, default=4, help="Parallel workers for compression")

    args = parser.parse_args(argv)

    repo_dir = args.dir.resolve()
    if not repo_dir.exists():
        print(f"Directory not found: {repo_dir}")
        raise SystemExit(1)

    # Only consider top-level JSON files that are original chats (exclude
    # .meta.json files which also end with .json). We also ignore any
    # already-compressed artifacts (they end with .zst/.gz) because the
    # script targets raw `.json` chat files.
    all_json = sorted(repo_dir.glob("*.json"))
    json_files = [p for p in all_json if not p.name.endswith(".meta.json")]
    if not json_files:
        print("No raw JSON chat files found in the target directory.")
        return

    # Decide compression method
    zstd_available = detect_zstd_binary()
    if args.use_gzip:
        use_zstd = False
    elif args.use_zstd:
        if not zstd_available:
            raise SystemExit("Requested zstd but 'zstd' binary was not found on PATH")
        use_zstd = True
    else:
        use_zstd = zstd_available

    print(f"Target dir: {repo_dir}")
    print("Using zstd for compression" if use_zstd else "Using gzip for compression")
    print(f"Dry-run: {args.dry_run}; workers: {args.workers}; force: {args.force}")

    results = []
    total_original = 0
    total_compressed = 0

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {ex.submit(process_file, f, repo_dir, use_zstd, args.dry_run, args.force): f for f in json_files}
        for fut in as_completed(futures):
            try:
                msg, orig, comp = fut.result()
                print(msg)
                total_original += orig
                total_compressed += comp
            except Exception as e:
                print(f"Error processing a file: {e}")

    print("\nSummary:")
    print(f"  JSON files discovered: {len(json_files)}")
    print(f"  Total original bytes (sum): {total_original}")
    print(f"  Total compressed bytes (sum): {total_compressed}")
    if total_original:
        saved = total_original - total_compressed
        pct = (saved / total_original * 100) if total_compressed else 0
        print(f"  Saved: {saved} bytes ({pct:.1f}%)")


if __name__ == "__main__":
    main()
