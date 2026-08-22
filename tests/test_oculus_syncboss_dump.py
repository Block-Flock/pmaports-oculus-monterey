import pathlib
import struct
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

    def test_decodes_hmd_imu_packet_in_si_units(self):
        payload = struct.pack("<QffffffI", 123456789, 1.0, -2.0, 0.5, 180.0, -90.0, 45.0, 7)
        record = bytes([1, 3, 0, 0x50, 9, len(payload)]) + payload
        with tempfile.NamedTemporaryFile() as stream:
            stream.write(record)
            stream.flush()
            result = subprocess.run(
                [str(self.binary), "-d", stream.name, "-n", "1", "-t", "0"],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("type=0x50 sequence=9 payload_length=36", result.stdout)
        self.assertIn("imu timestamp=123456789 metadata=0x00000007", result.stdout)
        self.assertIn("accel_m_s2=9.80665016,-19.6133003,4.90332508", result.stdout)
        self.assertIn("gyro_rad_s=3.14159274,-1.57079637,0.785398185", result.stdout)

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
