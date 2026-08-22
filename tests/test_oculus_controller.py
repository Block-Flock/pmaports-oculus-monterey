import os
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "device-oculus-monterey" / "oculus-controller"


class OculusControllerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tempdir.name)
        self.stock = root / "stock"
        self.devices = root / "dev"
        self.bin = root / "bin"
        self.log = root / "calls.log"
        self.bin.mkdir()
        self.devices.mkdir()
        for name in ("syncboss0", "syncboss_stream0", "syncboss_control0"):
            (self.devices / name).touch()
        tool = self.stock / "system/vendor/bin/syncboss_input_tool"
        linker = self.stock / "apex/com.android.runtime/bin/linker64"
        tool.parent.mkdir(parents=True)
        linker.parent.mkdir(parents=True)
        tool.touch()
        linker.write_text(
            "#!/bin/sh\nprintf '%s\\n' \"$*\" >>\"$OCULUS_TEST_LOG\"\n",
            encoding="utf-8",
        )
        linker.chmod(0o755)
        rc = self.bin / "rc-service"
        rc.write_text(
            "#!/bin/sh\nprintf 'rc:%s\\n' \"$*\" >>\"$OCULUS_TEST_LOG\"\n"
            "[ \"$2\" != status ]\n",
            encoding="utf-8",
        )
        rc.chmod(0o755)
        self.env = os.environ | {
            "OCULUS_STOCK_ROOT": str(self.stock),
            "OCULUS_DEVICE_ROOT": str(self.devices),
            "OCULUS_RC_COMMAND": str(rc),
            "OCULUS_TEST_LOG": str(self.log),
        }

    def tearDown(self):
        self.tempdir.cleanup()

    def run_script(self, *args):
        return subprocess.run(
            [str(SCRIPT), *args],
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )

    def calls(self):
        return self.log.read_text(encoding="utf-8") if self.log.exists() else ""

    def test_status_checks_runtime_and_devices(self):
        result = self.run_script("status")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("stock-runtime=ready", result.stdout)

    def test_list_is_observe_only(self):
        result = self.run_script("list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--observe --list", self.calls())

    def test_pair_accepts_only_device_id(self):
        good = self.run_script("pair", "0x1234abcd")
        self.assertEqual(good.returncode, 0, good.stderr)
        self.assertIn("--no-prompt --pair 0x1234abcd", self.calls())
        bad = self.run_script("pair", "--fw-update")
        self.assertEqual(bad.returncode, 2)
        self.assertNotIn("--fw-update", self.calls())

    def test_raw_firmware_update_is_not_exposed(self):
        result = self.run_script("--fw-update", "controller.bin")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.calls(), "")

    def test_haptic_range_is_bounded(self):
        result = self.run_script("haptic", "1234", "2.0")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.calls(), "")


if __name__ == "__main__":
    unittest.main()
