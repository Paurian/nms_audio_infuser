#!/usr/bin/env python3
"""Pack a folder into a Hello Games HGPAK archive.

The generated archive mirrors the HGPAK layout used by No Man's Sky:

    0x00  "HGPAK" magic
    0x08  little-endian version, normally 2
    0x10  little-endian table row count
    0x20  table rows, each 32 bytes:
          uint64 payload_offset
          uint64 payload_size
          16-byte MD5 of lowercase archive path

Rows 0 and 1 describe package metadata. Row 1 points at the CRLF-separated
filename table and also carries the MD5 for the first archive path. Subsequent
rows carry the MD5 for the next archive path and the payload offset/size for
the previous file. This staggered layout matches HGPAK archives observed in
No Man's Sky data.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import struct
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import BinaryIO


MAGIC = b"HGPAK"
VERSION = 2
TABLE_OFFSET = 0x20
ROW_SIZE = 32
ALIGNMENT = 16
COPY_CHUNK_SIZE = 1024 * 1024


class HGPAKError(Exception):
    """Raised when an archive cannot be built safely."""


@dataclass(frozen=True)
class SourceFile:
    disk_path: Path
    archive_name: str
    size: int


@dataclass(frozen=True)
class Payload:
    offset: int
    size: int


def align_up(value: int, alignment: int = ALIGNMENT) -> int:
    return (value + alignment - 1) // alignment * alignment


def archive_digest(archive_name: str) -> bytes:
    return hashlib.md5(archive_name.lower().encode("utf-8")).digest()


def normalize_archive_name(path: Path) -> str:
    name = path.as_posix()
    pure = PurePosixPath(name)
    if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
        raise HGPAKError(f"Unsafe archive path: {name!r}")
    return name


def discover_files(input_dir: Path, *, include_hidden: bool = False) -> list[SourceFile]:
    if not input_dir.is_dir():
        raise HGPAKError(f"Input is not a directory: {input_dir}")

    files: list[SourceFile] = []
    for path in sorted(input_dir.rglob("*"), key=lambda item: item.relative_to(input_dir).as_posix().lower()):
        if not path.is_file() or path.is_symlink():
            continue

        relative = path.relative_to(input_dir)
        if not include_hidden and any(part.startswith(".") for part in relative.parts):
            continue

        archive_name = normalize_archive_name(relative)
        files.append(SourceFile(disk_path=path, archive_name=archive_name, size=path.stat().st_size))

    if not files:
        raise HGPAKError("Input directory contains no files to pack")
    return files


def build_name_table(files: list[SourceFile]) -> bytes:
    return "".join(f"{source.archive_name}\r\n" for source in files).encode("utf-8")


def table_row_count(file_count: int) -> int:
    if file_count == 1:
        return 3
    return file_count + 1


def compute_payload_layout(name_table: bytes, files: list[SourceFile]) -> tuple[int, int, list[Payload]]:
    row_count = table_row_count(len(files))
    table_size = row_count * ROW_SIZE
    name_table_offset = align_up(TABLE_OFFSET + table_size)
    next_offset = align_up(name_table_offset + len(name_table))

    payloads: list[Payload] = []
    for source in files:
        payloads.append(Payload(offset=next_offset, size=source.size))
        next_offset = align_up(next_offset + source.size)

    return name_table_offset, table_size, payloads


def write_padding(handle: BinaryIO, target_offset: int) -> None:
    current = handle.tell()
    if current > target_offset:
        raise HGPAKError(f"Internal layout error: position {current} passed target {target_offset}")
    if current < target_offset:
        handle.write(b"\x00" * (target_offset - current))


def copy_file(source_path: Path, destination: BinaryIO) -> None:
    with source_path.open("rb") as source:
        while True:
            chunk = source.read(COPY_CHUNK_SIZE)
            if not chunk:
                break
            destination.write(chunk)


def write_header(handle: BinaryIO, row_count: int) -> None:
    header = bytearray(TABLE_OFFSET)
    header[0:5] = MAGIC
    struct.pack_into("<I", header, 0x08, VERSION)
    struct.pack_into("<Q", header, 0x10, row_count)
    handle.write(header)


def write_rows(
    handle: BinaryIO,
    *,
    table_size: int,
    name_table_offset: int,
    name_table_size: int,
    files: list[SourceFile],
    payloads: list[Payload],
) -> None:
    rows: list[tuple[int, int, bytes]] = []

    rows.append((0, name_table_offset, archive_digest("__metadata__")))
    rows.append((name_table_offset, name_table_size, archive_digest(files[0].archive_name)))

    if len(files) == 1:
        rows.append((payloads[0].offset, payloads[0].size, b"\x00" * 16))
    else:
        for index, payload in enumerate(payloads[:-1], start=1):
            rows.append((payload.offset, payload.size, archive_digest(files[index].archive_name)))

    for offset, size, digest in rows:
        handle.write(struct.pack("<QQ", offset, size))
        handle.write(digest)


def compact_hgpak(input_dir: Path, output_path: Path, *, include_hidden: bool = False, overwrite: bool = False) -> int:
    files = discover_files(input_dir, include_hidden=include_hidden)
    name_table = build_name_table(files)
    name_table_offset, table_size, payloads = compute_payload_layout(name_table, files)
    row_count = table_row_count(len(files))

    if output_path.exists() and not overwrite:
        raise HGPAKError(f"Output already exists: {output_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = output_path.with_name(f".{output_path.name}.tmp")

    try:
        with temp_path.open("wb") as out:
            write_header(out, row_count)
            write_rows(
                out,
                table_size=table_size,
                name_table_offset=name_table_offset,
                name_table_size=len(name_table),
                files=files,
                payloads=payloads,
            )
            write_padding(out, name_table_offset)
            out.write(name_table)

            for source, payload in zip(files, payloads):
                write_padding(out, payload.offset)
                copy_file(source.disk_path, out)

        os.replace(temp_path, output_path)
    except Exception:
        try:
            temp_path.unlink()
        except FileNotFoundError:
            pass
        raise

    return len(files)


def default_output_path(input_dir: Path) -> Path:
    return input_dir.with_suffix(".pak")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pack a folder into a Hello Games HGPAK archive.")
    parser.add_argument("input_dir", type=Path, help="Folder whose contents should be packed")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output archive path. Defaults to '<input_dir>.pak'.",
    )
    parser.add_argument("--include-hidden", action="store_true", help="Include files and folders whose names start with '.'")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite an existing output archive")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    input_dir = args.input_dir.expanduser().resolve()
    output_path = (args.output or default_output_path(input_dir)).expanduser().resolve()

    try:
        count = compact_hgpak(
            input_dir,
            output_path,
            include_hidden=args.include_hidden,
            overwrite=args.overwrite,
        )
        print(f"Done: packed {count} file(s) into {output_path}")
        return 0
    except HGPAKError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
