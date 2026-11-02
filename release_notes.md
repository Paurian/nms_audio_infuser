# No Man's Sky Audio Infuser Release Notes

Entries are listed in reverse chronological order, with the most recent release
at the top of the file.

## 1.1.0 — 2026-11-02

### Added

- Reorganized the Python code into the `src/nms_audio_infuser/` package and
  added package initializers.
- Added `pyproject.toml` for building wheels and source distributions. The
  package version is read from `APP_VERSION` in `nms_audio_infuser.py`, and
  installed commands are provided for the infuser, extractor, and packer.
- Added `test/hgpak_tests.py` and the `test/test.pak` sample. The
  tests verify extraction of the expected WEM files and repack the extracted
  files to compare archive sizes.
- Added wheel and source distribution artifacts under `dist/`.

### Changed

- Updated `compact_hgpak.py` to follow the HGPAK layout requirements used by
  current No Man's Sky archives. It deduplicates identical payloads, points
  matching file entries to shared data, and preserves the required table
  padding and final payload alignment.
- Added version and release-date output when scripts run without arguments,
  plus `-?` as a help alias. The infuser's interactive prompt is available with
  `--interactive`.
- Updated `readme.md` with the `src/` layout, wheel installation, source usage,
  and distribution build instructions.
- Updated `requirements.txt` to include the `build` frontend; application
  runtime code still uses only the standard library and requires Python 3.10 or
  newer.
- Updated `.gitignore` to allow `test/test.pak` while ignoring other `.pak`
  files.

### Verified

- Built the version 1.1.0 wheel and source distribution in `dist/`.
- Ran the two tests in `test/hgpak_tests.py`; extraction and the repacked-size
  comparison both passed.
- Extracted and repacked the larger `test.pak` sample; the rebuilt archive
  matched its original filesize exactly, and all 28,635 payload hashes matched.

## 2026-09-01 — Initial check-in

### Added

- Added the main program, `nms_audio_infuser.py`, for rebuilding the Mac
  `NMSARC.Audio.pak` archive with replacement audio files.
- Added `extract_hgpak.py` to extract and inspect HGPAK archives.
- Added `compact_hgpak.py` to pack folders into HGPAK archives.
- Added usage instructions and workflow details in `readme.md`.
