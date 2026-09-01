# No Man's Sky Audio Infuser

No Man's Sky Audio Infuser helps you rebuild the Mac version of
`NMSARC.Audio.pak` with replacement `.wem` audio files from a mod source folder
or source zip.

The usual workflow is:

1. Download a No Man's Sky audio mod from Nexus Mods as a zip file or extracted
   folder. My favorite is [MEGAN Exosuit AI Voice](https://www.nexusmods.com/nomanssky/mods/1992).
2. Run `nms_audio_infuser.py` on a Macintosh with No Man's Sky installed through
   Steam.
3. The script copies the game's original `NMSARC.Audio.pak`, extracts it,
   overwrites matching `.wem` files with the modded audio, and rebuilds a new
   HGPAK archive.

The script does not overwrite the game install automatically. At the end, it
prints a `cp` command you can review and run manually.

## Requirements

- macOS
- No Man's Sky installed through Steam
- Python 3.10 or newer
- No third-party Python packages

The default Steam audio archive location is:

```text
~/Library/Application Support/Steam/steamapps/common/No Man's Sky/No Man's Sky.app/Contents/Resources/GAMEDATA/MACOSBANKS/NMSARC.Audio.pak
```

## Quick Start

From this directory:

```bash
python3 nms_audio_infuser.py "NMS-MeganExosuitAudio.zip"
```

With an extracted source folder:

```bash
python3 nms_audio_infuser.py "NMS-Megan-Audio"
```

With an explicit project directory:

```bash
python3 nms_audio_infuser.py \
  --hacks-dir "$HOME/Projects/No Man's Sky Hacks" \
  "NMS-MeganExosuitAudio.zip"
```

## Main Script

```bash
python3 nms_audio_infuser.py [--hacks-dir HACKS_DIR] [audio_source]
```

### Arguments

`audio_source`

- Optional.
- A directory or `.zip` file containing replacement No Man's Sky audio files.
- The script searches recursively for `.wem` files inside this source.
- If omitted, the script prompts for the relative path of the audio source.
- Relative paths are checked from this tool directory first, then from the
  current terminal directory.

`--hacks-dir HACKS_DIR`

- Optional.
- Overrides the root folder used for backups, temporary extracted audio banks,
  temporary extracted zip sources, and helper scripts.
- If omitted, the default is:

```text
~/Projects/No Man's Sky Hacks
```

## What Happens When You Run It

For one run, the script creates a timestamp like `YYYYMMDDHHmm`.

It then:

1. Finds the original Steam archive:

```text
~/Library/Application Support/Steam/steamapps/common/No Man's Sky/No Man's Sky.app/Contents/Resources/GAMEDATA/MACOSBANKS/NMSARC.Audio.pak
```

2. Copies it to:

```text
<hacks-dir>/NMSARC.Audio.YYYYMMDDHHmm.pak
```

3. Extracts that copy to:

```text
<hacks-dir>/Audio_Bank_YYYYMMDDHHmm
```

4. If the source is a zip file, extracts it to:

```text
<hacks-dir>/Audio_Source_YYYYMMDDHHmm
```

5. Recursively scans the source directory for `.wem` files.

6. Finds `.wem` files in the extracted audio bank with the same filename and
   extension.

7. Overwrites each matching extracted bank file with the source file.

8. Prints any source `.wem` files that did not match a file in the extracted
   audio bank.

If unmatched source `.wem` files exist, the script asks:

```text
Continue and rebuild the HGPAK anyway? [Y/N]:
```

If you type `Y`, it rebuilds the archive.

If you type `N`, it stops before rebuilding and prints the manual
`compact_hgpak.py` command you can run later.

If there are no unmatched source `.wem` files, it rebuilds without asking.

The rebuilt archive is written to:

```text
<hacks-dir>/NMSARC.Audio.infused.YYYYMMDDHHmm.pak
```

At exit, the script prints the original game archive path and a manual install
command like:

```bash
cp '<hacks-dir>/NMSARC.Audio.infused.YYYYMMDDHHmm.pak' '~/Library/Application Support/Steam/steamapps/common/No Man'\''s Sky/No Man'\''s Sky.app/Contents/Resources/GAMEDATA/MACOSBANKS/NMSARC.Audio.pak'
```

Review that command before running it.

## Helper Scripts

### extract_hgpak.py

Extracts files from an HGPAK archive.

```bash
python3 extract_hgpak.py [options] archive
```

Arguments:

`archive`

- Required.
- Path to the `.pak` or HGPAK archive to extract.

Options:

`-o, --output OUTPUT`

- Optional.
- Output directory.
- If omitted, extraction goes to `<archive_stem>_extracted` next to the archive.

`--list`

- Optional.
- Lists archive contents without extracting files.

`--overwrite`

- Optional.
- Overwrites existing extracted files.
- If omitted, existing files are skipped.

`--strict`

- Optional.
- Treats parser warnings as errors.

`--quiet`

- Optional.
- Reduces extraction output.

### compact_hgpak.py

Packs a folder into an HGPAK archive.

```bash
python3 compact_hgpak.py [options] input_dir
```

Arguments:

`input_dir`

- Required.
- Folder whose contents should be packed into the archive.

Options:

`-o, --output OUTPUT`

- Optional.
- Output archive path.
- If omitted, the output is `<input_dir>.pak`.

`--include-hidden`

- Optional.
- Includes files and folders whose names start with `.`.
- If omitted, hidden files such as `.DS_Store` are skipped.

`--overwrite`

- Optional.
- Overwrites an existing output archive.
- If omitted and the output archive already exists, packing stops with an
  error.

## Notes

- Matching is based on `.wem` filename plus extension, not full folder path.
- The replacement source may contain extra files; only `.wem` files are used by
  the main infuser script.
- The helper packer stores files in HGPAK format. It does not convert or
  recompress the audio inside `.wem` files.
