import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "device-oculus-monterey" / "oculus-controller-uinput.c"


class OculusControllerUinputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.binary = pathlib.Path(cls.tempdir.name) / "oculus-controller-uinput"
        subprocess.run(
            [
                "cc",
                "-std=c11",
                "-Wall",
                "-Wextra",
                "-Werror",
                str(SOURCE),
                "-lm",
                "-o",
                str(cls.binary),
            ],
            check=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls.tempdir.cleanup()

    def bridge(self, stream):
        return subprocess.run(
            [str(self.binary), "--dry-run"],
            input=stream,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_thumbstick_moves_relative_pointer_with_deadzone(self):
        result = self.bridge(
            "\tthumbstick : {x:0.500, y:-0.250}\n"
            "\tthumbstick : {x:0.100, y:0.100}\n"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["REL_X 9", "REL_Y 5", "SYN"])

    def test_trigger_and_grip_have_hysteresis(self):
        result = self.bridge(
            "\ttrig       : {fore:0.700, grip:0.000}\n"
            "\ttrig       : {fore:0.500, grip:0.700}\n"
            "\ttrig       : {fore:0.400, grip:0.400}\n"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            [
                "BTN_LEFT 1",
                "SYN",
                "BTN_RIGHT 1",
                "SYN",
                "BTN_LEFT 0",
                "BTN_RIGHT 0",
                "SYN",
            ],
        )

    def test_buttons_combine_with_analog_click_sources(self):
        result = self.bridge(
            "\ttrig       : {fore:0.700, grip:0.000}\n"
            "\tbutton     : {ax:1, by:0, sys:1, ts:1}\n"
            "\ttrig       : {fore:0.000, grip:0.000}\n"
            "\tbutton     : {ax:0, by:0, sys:0, ts:0}\n"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("BTN_LEFT 1\n"), 1)
        self.assertEqual(result.stdout.count("BTN_LEFT 0\n"), 1)
        self.assertIn("KEY_ESC 1\n", result.stdout)
        self.assertIn("BTN_MIDDLE 1\n", result.stdout)

    def test_unknown_and_non_finite_records_fail_closed(self):
        result = self.bridge(
            "firmware update ready\n"
            "\tthumbstick : {x:nan, y:1.000}\n"
            "\ttrig       : {fore:inf, grip:1.000}\n"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
