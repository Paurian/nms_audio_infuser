"""Round-trip tests for the checked-in HGPAK sample."""

import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SOURCE_ROOT))

from nms_audio_infuser.compact_hgpak import compact_hgpak
from nms_audio_infuser.extract_hgpak import main as extract_main


SAMPLE_ARCHIVE = Path(__file__).resolve().parent / "test.pak"
EXPECTED_FILES = (
    Path("80959229.WEM"),
    Path("ENGLISH(US)") / "808789373.WEM",
    Path("ENGLISH(US)") / "811360087.WEM",
    Path("ENGLISH(US)") / "825969836.WEM",
    Path("ENGLISH(US)") / "871932351.WEM",
    Path("ENGLISH(US)") / "891464212.WEM",
    Path("ENGLISH(US)") / "899453751.WEM",
    Path("ENGLISH(US)") / "80959229.WEM",
    Path("ENGLISH(US)") / "824368356.WEM",
    Path("ENGLISH(US)") / "863051935.WEM",
    Path("ENGLISH(US)") / "884631197.WEM",
    Path("ENGLISH(US)") / "899320928.WEM",
)


class HGPAKTests(unittest.TestCase):
    def extract_sample(self, output_dir: Path) -> None:
        output = StringIO()
        with redirect_stdout(output):
            result = extract_main(
                ["--quiet", "-o", str(output_dir), str(SAMPLE_ARCHIVE)]
            )
        self.assertEqual(result, 0, output.getvalue())

    def test_extracts_expected_files_from_test_archive(self) -> None:
        self.assertTrue(SAMPLE_ARCHIVE.is_file(), f"Sample archive not found: {SAMPLE_ARCHIVE}")

        with tempfile.TemporaryDirectory(prefix="extract-hgpak-test-") as temporary_dir:
            output_dir = Path(temporary_dir) / "hg_unpacked"
            self.extract_sample(output_dir)
            missing = [
                relative_path.as_posix()
                for relative_path in EXPECTED_FILES
                if not (output_dir / relative_path).is_file()
            ]
            self.assertEqual(missing, [], f"Expected extracted files are missing: {missing}")

    def test_repacked_archive_is_similar_in_size_to_test_archive(self) -> None:
        self.assertTrue(SAMPLE_ARCHIVE.is_file(), f"Sample archive not found: {SAMPLE_ARCHIVE}")

        with tempfile.TemporaryDirectory(prefix="repack-hgpak-test-") as temporary_dir:
            temporary_root = Path(temporary_dir)
            extracted_dir = temporary_root / "hg_unpacked"
            rebuilt_archive = temporary_root / "test.pak"
            self.extract_sample(extracted_dir)

            compact_hgpak(extracted_dir, rebuilt_archive)

            original_size = SAMPLE_ARCHIVE.stat().st_size
            rebuilt_size = rebuilt_archive.stat().st_size
            relative_difference = abs(rebuilt_size - original_size) / original_size
            self.assertLessEqual(
                relative_difference,
                0.01,
                f"Repacked archive size {rebuilt_size} differs from original size "
                f"{original_size} by more than 1%.",
            )


if __name__ == "__main__":
    unittest.main()
