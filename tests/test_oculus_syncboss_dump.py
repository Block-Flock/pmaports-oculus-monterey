import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "device-oculus-monterey" / "oculus-syncboss-dump.c"


class OculusSyncbossDumpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.binary = pathlib.Path(cls.tempdir.name) / "oculus-syncboss-dump"
        subprocess.run(
            ["cc", "-std=c11", "-D_GNU_SOURCE", "-Wall", "-Wextra", "-Werror", str(SOURCE), "-o", str(cls.binary)],
            check=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls.tempdir.cleanup()

    def test_decodes_driver_header_without_writing(self):
        with tempfile.NamedTemporaryFile() as stream:
            stream.write(bytes([1, 3, 0, 0x17, 0xAA, 0x55]))
            stream.flush()
            result = subprocess.run(
                [str(self.binary), "-d", stream.name, "-n", "1", "-t", "0"],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("header_version=1 header_length=3 from_driver=0", result.stdout)
        self.assertIn("0000: 01 03 00 17 aa 55", result.stdout)

    def test_rejects_zero_packet_count(self):
        result = subprocess.run(
            [str(self.binary), "-n", "0"], text=True, capture_output=True, check=False
        )
        self.assertEqual(result.returncode, 2)

    def test_missing_device_fails_closed(self):
        result = subprocess.run(
            [str(self.binary), "-d", "/definitely/not/a/device"],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("read-only", result.stderr)


if __name__ == "__main__":
    unittest.main()
