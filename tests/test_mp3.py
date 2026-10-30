import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import convert_mp3, ffmpeg_path


class MP3Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.folder = Path(self.temp.name)
        self.source = self.folder / 'sample.m4a'
        subprocess.run([ffmpeg_path(), '-v', 'error', '-f', 'lavfi', '-i',
                        'sine=frequency=440:duration=0.2', '-c:a', 'aac', str(self.source)],
                       check=True, capture_output=True)

    def tearDown(self):
        self.temp.cleanup()

    def test_twenty_parts_leave_only_twenty_mp3s(self):
        for number in range(1, 21):
            source = self.folder / f'part{number}.m4a'
            shutil.copyfile(self.source, source)
            target = Path(convert_mp3(source))
            self.assertTrue(target.is_file())
            self.assertFalse(source.exists())
            subprocess.run([ffmpeg_path(), '-v', 'error', '-xerror', '-i', str(target),
                            '-f', 'null', '-'], check=True, capture_output=True)
        self.assertEqual(len(list(self.folder.glob('part*'))), 20)

    def test_failed_conversion_preserves_source(self):
        original = self.source.read_bytes()
        with patch('app.subprocess.run', return_value=subprocess.CompletedProcess([], 1, stderr=b'test failure')):
            with self.assertRaises(RuntimeError):
                convert_mp3(self.source)
        self.assertEqual(self.source.read_bytes(), original)
        self.assertFalse(self.source.with_suffix('.mp3').exists())

    def test_valid_existing_mp3_is_kept(self):
        original = self.source.read_bytes()
        target = Path(convert_mp3(self.source))
        expected = target.read_bytes()
        self.source.write_bytes(original)
        convert_mp3(self.source)
        self.assertFalse(self.source.exists())
        self.assertEqual(target.read_bytes(), expected)
        self.assertEqual(convert_mp3(target), str(target))

    def test_invalid_existing_mp3_preserves_both(self):
        target = self.source.with_suffix('.mp3')
        target.write_bytes(b'invalid mp3')
        with self.assertRaises(RuntimeError):
            convert_mp3(self.source)
        self.assertTrue(self.source.exists())
        self.assertEqual(target.read_bytes(), b'invalid mp3')


if __name__ == '__main__':
    unittest.main()
