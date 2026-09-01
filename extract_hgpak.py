#!/usr/bin/env python3
"""Extract files from Hello Games HGPAK archives.

This parser is based on the HGPAK layout used by No Man's Sky archives:

    0x00  "HGPAK" magic
    0x08  little-endian version
    0x10  little-endian table row count
    0x20  table rows, each 32 bytes:
          uint64 payload_offset
          uint64 payload_size
          16-byte MD5 of lowercase archive path

The first rows describe package metadata. Row 1 points at the CRLF-separated
filename table. Payload offsets for the named files begin at row 2. Some HGPAK
archives omit an explicit payload row for the final file; in that case this
script infers the final file's start from the previous payload end and uses EOF.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Iterable


TABLE_OFFSET = 0x20
ROW_SIZE = 32
ALIGNMENT = 16
COPY_CHUNK_SIZE = 1024 * 1024


class HGPAKError(Exception):
    """Raised when an archive cannot be parsed safely."""


@dataclass(frozen=True)
class TableRow:
    offset: int
    size: int
    digest: bytes


@dataclass(frozen=True)
class FileEntry:
    name: str
    offset: int
    size: int
    inferred: bool = False

    @property
    def end(self) -> int:
        return self.offset + self.size


def align_up(value: int, alignment: int = ALIGNMENT) -> int:
    return (value + alignment - 1) // alignment * alignment


def read_exact(handle: BinaryIO, size: int, label: str) -> bytes:
    data = handle.read(size)
    if len(data) != size:
        raise HGPAKError(f"Unexpected end of file while reading {label}")
    return data


def parse_rows(handle: BinaryIO, row_count: int) -> list[TableRow]:
    handle.seek(TABLE_OFFSET)
    rows: list[TableRow] = []
    for index in range(row_count):
        row = read_exact(handle, ROW_SIZE, f"table row {index}")
        offset, size = struct.unpack_from("<QQ", row, 0)
        rows.append(TableRow(offset=offset, size=size, digest=row[16:32]))
    return rows


def read_names(handle: BinaryIO, name_row: TableRow, archive_size: int) -> list[str]:
    if name_row.offset + name_row.size > archive_size:
        raise HGPAKError("Filename table points beyond the end of the archive")

    handle.seek(name_row.offset)
    blob = read_exact(handle, name_row.size, "filename table")
    text = blob.decode("utf-8")
    names = [line for line in text.splitlines() if line]
    if not names:
        raise HGPAKError("Filename table is empty")
    return names


def parse_hgpak(path: Path, *, strict: bool = False) -> tuple[list[FileEntry], list[str]]:
    archive_size = path.stat().st_size
    warnings: list[str] = []

    with path.open("rb") as handle:
        header = read_exact(handle, TABLE_OFFSET, "HGPAK header")

        if not header.startswith(b"HGPAK"):
            raise HGPAKError("Not an HGPAK archive: missing HGPAK magic")

        version = struct.unpack_from("<I", header, 0x08)[0]
        row_count = struct.unpack_from("<Q", header, 0x10)[0]
        if row_count < 3:
            raise HGPAKError(f"Invalid table row count: {row_count}")

        table_end = TABLE_OFFSET + row_count * ROW_SIZE
        if table_end > archive_size:
            raise HGPAKError("Table extends beyond the end of the archive")

        rows = parse_rows(handle, row_count)
        names = read_names(handle, rows[1], archive_size)

    if version != 2:
        warnings.append(f"HGPAK version is {version}; this script was tested with version 2")

    entries: list[FileEntry] = []
    payload_rows = rows[2:]

    for name_index, name in enumerate(names):
        if name_index < len(payload_rows):
            row = payload_rows[name_index]
            inferred = False
        elif name_index == len(payload_rows) and entries:
            previous = entries[-1]
            offset = align_up(previous.end)
            if offset > archive_size:
                raise HGPAKError("Cannot infer final file offset beyond EOF")
            row = TableRow(offset=offset, size=archive_size - offset, digest=b"")
            inferred = True
            warnings.append(f"Inferred final payload for {name!r} from previous entry and EOF")
        else:
            message = f"No payload table row available for {name!r}"
            if strict:
                raise HGPAKError(message)
            warnings.append(message)
            continue

        if row.offset + row.size > archive_size:
            raise HGPAKError(f"Payload for {name!r} points beyond EOF")

        hash_row_index = name_index + 1
        if hash_row_index < len(rows):
            expected = hashlib.md5(name.lower().encode("utf-8")).digest()
            if rows[hash_row_index].digest != expected:
                message = f"MD5 path hash mismatch for {name!r}"
                if strict:
                    raise HGPAKError(message)
                warnings.append(message)

        entries.append(FileEntry(name=name, offset=row.offset, size=row.size, inferred=inferred))

    return entries, warnings


def safe_output_path(root: Path, archive_name: str) -> Path:
    archive_path = PurePosixPath(archive_name)
    if archive_path.is_absolute() or any(part in ("", ".", "..") for part in archive_path.parts):
        raise HGPAKError(f"Unsafe archive path: {archive_name!r}")
    return root.joinpath(*archive_path.parts)


def copy_range(source: BinaryIO, destination: BinaryIO, size: int) -> None:
    remaining = size
    while remaining:
        chunk = source.read(min(COPY_CHUNK_SIZE, remaining))
        if not chunk:
            raise HGPAKError("Unexpected EOF while extracting payload")
        destination.write(chunk)
        remaining -= len(chunk)


def extract_entries(
    archive: Path,
    output_dir: Path,
    entries: Iterable[FileEntry],
    *,
    overwrite: bool = False,
    quiet: bool = False,
) -> tuple[int, int]:
    extracted = 0
    skipped = 0
    output_dir.mkdir(parents=True, exist_ok=True)

    with archive.open("rb") as source:
        for entry in entries:
            destination = safe_output_path(output_dir, entry.name)
            if destination.exists() and not overwrite:
                skipped += 1
                if not quiet:
                    print(f"skip existing: {entry.name}", file=sys.stderr)
                continue

            destination.parent.mkdir(parents=True, exist_ok=True)
            source.seek(entry.offset)
            with destination.open("wb") as out:
                copy_range(source, out, entry.size)

            extracted += 1
            if not quiet:
                marker = " inferred" if entry.inferred else ""
                print(f"extracted{marker}: {entry.name}")

    return extracted, skipped


def default_output_dir(archive: Path) -> Path:
    return archive.with_name(f"{archive.stem}_extracted")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Extract files from a Hello Games HGPAK archive.")
    parser.add_argument("archive", type=Path, help="Path to an .pak/.HGPAK archive")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output directory. Defaults to '<archive_stem>_extracted' next to the archive.",
    )
    parser.add_argument("--list", action="store_true", help="List files without extracting")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing extracted files")
    parser.add_argument("--strict", action="store_true", help="Treat parser warnings as errors")
    parser.add_argument("--quiet", action="store_true", help="Reduce extraction output")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    archive = args.archive.expanduser().resolve()
    if not archive.is_file():
        parser.error(f"Archive does not exist or is not a file: {archive}")

    try:
        entries, warnings = parse_hgpak(archive, strict=args.strict)
        for warning in warnings:
            print(f"warning: {warning}", file=sys.stderr)

        if args.list:
            for entry in entries:
                marker = " inferred" if entry.inferred else ""
                print(f"{entry.offset:012x} {entry.size:10d}{marker}  {entry.name}")
            return 0

        output_dir = (args.output or default_output_dir(archive)).expanduser().resolve()
        extracted, skipped = extract_entries(
            archive,
            output_dir,
            entries,
            overwrite=args.overwrite,
            quiet=args.quiet,
        )
        print(f"Done: extracted {extracted} file(s), skipped {skipped}, output: {output_dir}")
        return 0
    except (HGPAKError, OSError, UnicodeDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
