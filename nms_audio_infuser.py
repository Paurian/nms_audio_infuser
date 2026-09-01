#!/usr/bin/env python3
"""Infuse replacement WEM files into No Man's Sky's audio HGPAK archive."""

from __future__ import annotations

import argparse
import getpass
import os
import shlex
import shutil
import subprocess
import sys
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path, PurePosixPath


DEFAULT_HACKS_DIR = Path.home() / "Projects" / "No Man's Sky Hacks"
ARCHIVE_RELATIVE_PATH = (
    "Library/Application Support/Steam/steamapps/common/No Man's Sky/"
    "No Man's Sky.app/Contents/Resources/GAMEDATA/MACOSBANKS/NMSARC.Audio.pak"
)


class InfuserError(Exception):
    """Raised when the infuser cannot complete the requested workflow."""


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d%H%M")


def original_archive_path() -> Path:
    return Path("/Users") / getpass.getuser() / ARCHIVE_RELATIVE_PATH


def resolve_hacks_dir(hacks_dir_text: str | None) -> Path:
    if hacks_dir_text:
        return Path(hacks_dir_text).expanduser().resolve()
    return DEFAULT_HACKS_DIR.resolve()


def resolve_source(source_text: str, tool_dir: Path) -> Path:
    source = Path(source_text).expanduser()
    if source.is_absolute():
        return source.resolve()

    from_tool_dir = (tool_dir / source).resolve()
    if from_tool_dir.exists():
        return from_tool_dir

    return (Path.cwd() / source).resolve()


def prompt_for_source(tool_dir: Path) -> Path:
    while True:
        answer = input("Audio source relative path: ").strip()
        if not answer:
            print("Please provide a directory or .zip file path.")
            continue
        source = resolve_source(answer, tool_dir)
        if source.exists():
            return source
        print(f"Not found: {source}")


def require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise InfuserError(f"{label} not found: {path}")


def require_tools(extract_script: Path, compact_script: Path) -> None:
    require_file(extract_script, "extract_hgpak.py")
    require_file(compact_script, "compact_hgpak.py")


def run_tool(command: list[str]) -> None:
    pretty = " ".join(shlex.quote(part) for part in command)
    print(f"Running: {pretty}")
    subprocess.run(command, check=True)


def safe_zip_member_path(root: Path, member_name: str) -> Path:
    pure = PurePosixPath(member_name)
    if pure.is_absolute() or any(part in ("", ".", "..") for part in pure.parts):
        raise InfuserError(f"Unsafe zip member path: {member_name!r}")
    return root.joinpath(*pure.parts)


def extract_zip_source(zip_path: Path, hacks_dir: Path, stamp: str) -> Path:
    source_dir = hacks_dir / f"Audio_Source_{stamp}"
    source_dir.mkdir(parents=True, exist_ok=False)

    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            target = safe_zip_member_path(source_dir, member.filename)
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination)

    return source_dir


def prepare_source(source: Path, hacks_dir: Path, stamp: str) -> Path:
    if source.is_dir():
        return source
    if source.is_file() and source.suffix.lower() == ".zip":
        print(f"Extracting source zip into Audio_Source_{stamp}")
        return extract_zip_source(source, hacks_dir, stamp)
    raise InfuserError(f"Audio source must be a directory or .zip file: {source}")


def wem_files(root: Path) -> list[Path]:
    return sorted((path for path in root.rglob("*") if path.is_file() and path.suffix.lower() == ".wem"), key=str)


def index_bank_wems(bank_dir: Path) -> dict[str, list[Path]]:
    index: dict[str, list[Path]] = defaultdict(list)
    for path in wem_files(bank_dir):
        index[path.name.lower()].append(path)
    return dict(index)


def overwrite_matching_wems(source_dir: Path, bank_dir: Path) -> tuple[int, list[Path]]:
    bank_index = index_bank_wems(bank_dir)
    replacements = wem_files(source_dir)
    unmatched: list[Path] = []
    replaced = 0

    for source in replacements:
        matches = bank_index.get(source.name.lower(), [])
        if not matches:
            unmatched.append(source)
            continue

        for destination in matches:
            shutil.copy2(source, destination)
            replaced += 1
            print(f"overwrote: {destination.relative_to(bank_dir)}")

    return replaced, unmatched


def should_continue(unmatched: list[Path], source_dir: Path) -> bool:
    if not unmatched:
        return True

    print()
    print("The following source .wem files did not match any Audio_Bank file:")
    for path in unmatched:
        print(f"  {path.relative_to(source_dir)}")
    print()

    while True:
        answer = input("Continue and rebuild the HGPAK anyway? [Y/N]: ").strip().upper()
        if answer == "Y":
            return True
        if answer == "N":
            return False
        print("Please type Y or N.")


def print_manual_copy_command(original: Path, rebuilt: Path) -> None:
    print()
    print(f"Original NMSARC.Audio.pak location: {original}")
    print("Manual install command:")
    print(f"cp {shlex.quote(str(rebuilt))} {shlex.quote(str(original))}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Replace matching WEM files and rebuild NMSARC.Audio.pak.")
    parser.add_argument("audio_source", nargs="?", help="Replacement audio source directory or .zip file")
    parser.add_argument(
        "--hacks-dir",
        help="Root folder for backups, temporary audio banks, and tool scripts. Defaults to '~/Projects/No Man's Sky Hacks'.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    stamp = timestamp()
    hacks_dir = resolve_hacks_dir(args.hacks_dir)
    tool_dir = hacks_dir / "Audio Infuser"
    extract_script = tool_dir / "extract_hgpak.py"
    compact_script = tool_dir / "compact_hgpak.py"
    original = original_archive_path()
    backup = hacks_dir / f"NMSARC.Audio.{stamp}.pak"
    bank_dir = hacks_dir / f"Audio_Bank_{stamp}"
    rebuilt = hacks_dir / f"NMSARC.Audio.infused.{stamp}.pak"

    try:
        require_tools(extract_script, compact_script)
        require_file(original, "Steam NMSARC.Audio.pak")
        hacks_dir.mkdir(parents=True, exist_ok=True)

        source = resolve_source(args.audio_source, tool_dir) if args.audio_source else prompt_for_source(tool_dir)
        source_dir = prepare_source(source, hacks_dir, stamp)

        print(f"Copying original archive to: {backup}")
        shutil.copy2(original, backup)

        print(f"Extracting copied archive to: {bank_dir}")
        run_tool([sys.executable, str(extract_script), "--overwrite", "--quiet", "-o", str(bank_dir), str(backup)])

        replaced, unmatched = overwrite_matching_wems(source_dir, bank_dir)
        print(f"Matched replacement writes: {replaced}")

        if not should_continue(unmatched, source_dir):
            print()
            print("Stopped before rebuilding. To rebuild manually later, run:")
            print(f"python3 {shlex.quote(str(compact_script))} {shlex.quote(str(bank_dir))} -o {shlex.quote(str(rebuilt))} --overwrite")
            print_manual_copy_command(original, rebuilt)
            return 0

        print(f"Rebuilding HGPAK archive: {rebuilt}")
        run_tool([sys.executable, str(compact_script), str(bank_dir), "-o", str(rebuilt), "--overwrite"])
        print_manual_copy_command(original, rebuilt)
        return 0
    except subprocess.CalledProcessError as exc:
        print(f"error: command failed with exit code {exc.returncode}", file=sys.stderr)
        print_manual_copy_command(original, rebuilt)
        return exc.returncode or 1
    except (InfuserError, OSError, zipfile.BadZipFile) as exc:
        print(f"error: {exc}", file=sys.stderr)
        print_manual_copy_command(original, rebuilt)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
