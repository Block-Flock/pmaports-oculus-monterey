import os
import pathlib
import subprocess
import tempfile
import time
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "device-oculus-monterey" / "oculus-controller"
INPUT_MANAGER = ROOT / "device-oculus-monterey" / "oculus-controller-input"
CONTROLLER_SERVICE = ROOT / "device-oculus-monterey" / "oculus-controller.initd"
LABWC_SERVICE = ROOT / "postmarketos-ui-oculus-labwc" / "oculus-labwc.initd"


class OculusControllerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.tempdir.name)
        self.stock = root / "stock"
        self.devices = root / "dev"
        self.bin = root / "bin"
        self.runtime = root / "run"
        self.log = root / "calls.log"
        self.bin.mkdir()
        self.runtime.mkdir()
        self.devices.mkdir()
        for name in ("syncboss0", "syncboss_stream0", "syncboss_control0"):
            (self.devices / name).touch()
        tool = self.stock / "system/vendor/bin/syncboss_input_tool"
        # This is the layout on the untouched v50 system partition. Android's
        # usual /apex/com.android.runtime path exists only after Android mounts
        # the APEX payload.
        linker = (
            self.stock
            / "system/apex/com.android.runtime.release/bin/linker64"
        )
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
            "OCULUS_CONTROLLER_RUNTIME_DIR": str(self.runtime),
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

    def test_legacy_logical_apex_layout_remains_supported(self):
        release = self.stock / "system/apex/com.android.runtime.release"
        legacy = self.stock / "apex/com.android.runtime"
        legacy.parent.mkdir(parents=True)
        release.rename(legacy)
        result = self.run_script("status")
        self.assertEqual(result.returncode, 0, result.stderr)

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

    def test_input_manager_starts_only_two_enumerated_streams(self):
        controller = self.bin / "controller-manager-mock"
        controller.write_text(
            "#!/bin/sh\n"
            "printf '%s\\n' \"$*\" >>\"$OCULUS_TEST_LOG\"\n"
            "case $1 in\n"
            "daemon) trap 'exit 0' TERM INT; while :; do sleep 1; done;;\n"
            "list) printf ' 0: 0123456789abcdef left connected\\n'\n"
            "      printf ' 1: fedcba9876543210 right connected\\n'\n"
            "      printf ' 2: aaaaaaaaaaaaaaaa left connected\\n';;\n"
            "stream) printf '\\tthumbstick : {x:0.500, y:0.000}\\n';;\n"
            "esac\n",
            encoding="utf-8",
        )
        controller.chmod(0o755)
        bridge = self.bin / "bridge-mock"
        bridge.write_text("#!/bin/sh\ncat >/dev/null\n", encoding="utf-8")
        bridge.chmod(0o755)
        manager = ROOT / "device-oculus-monterey" / "oculus-controller-input"
        result = subprocess.run(
            [str(manager), "--once"],
            env=self.env
            | {
                "OCULUS_CONTROLLER_COMMAND": str(controller),
                "OCULUS_CONTROLLER_BRIDGE": str(bridge),
                "OCULUS_CONTROLLER_START_DELAY": "0",
            },
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        self.assertIn("stream 0x0123456789abcdef", calls)
        self.assertIn("stream 0xfedcba9876543210", calls)
        self.assertNotIn("stream 0xaaaaaaaaaaaaaaaa", calls)

    def test_input_manager_reaps_stream_pipeline_children(self):
        producer_pids = pathlib.Path(self.tempdir.name) / "producer.pids"
        consumer_pids = pathlib.Path(self.tempdir.name) / "consumer.pids"
        controller = self.bin / "controller-lifecycle-mock"
        controller.write_text(
            "#!/bin/sh\n"
            "case $1 in\n"
            "daemon) trap 'exit 0' TERM INT; while :; do sleep 1; done;;\n"
            "list) printf ' 0: 0123456789abcdef left connected\\n';;\n"
            "stream) echo $$ >>\"$OCULUS_PRODUCER_PIDS\"; "
            "        trap 'exit 0' TERM INT; while :; do sleep 1; done;;\n"
            "esac\n",
            encoding="utf-8",
        )
        controller.chmod(0o755)
        bridge = self.bin / "bridge-lifecycle-mock"
        bridge.write_text(
            "#!/bin/sh\n"
            "echo $$ >>\"$OCULUS_CONSUMER_PIDS\"\n"
            "trap 'exit 0' TERM INT\n"
            "cat >/dev/null\n",
            encoding="utf-8",
        )
        bridge.chmod(0o755)
        manager = ROOT / "device-oculus-monterey" / "oculus-controller-input"
        process = subprocess.Popen(
            [str(manager)],
            env=self.env
            | {
                "OCULUS_CONTROLLER_COMMAND": str(controller),
                "OCULUS_CONTROLLER_BRIDGE": str(bridge),
                "OCULUS_CONTROLLER_START_DELAY": "0",
                "OCULUS_PRODUCER_PIDS": str(producer_pids),
                "OCULUS_CONSUMER_PIDS": str(consumer_pids),
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if producer_pids.exists() and consumer_pids.exists():
                break
            time.sleep(0.05)
        process.terminate()
        _, stderr = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 0, stderr)
        pids = [
            int(value)
            for path in (producer_pids, consumer_pids)
            for value in path.read_text().splitlines()
        ]
        self.assertTrue(pids)
        self.assertTrue(all(not pathlib.Path(f"/proc/{pid}").exists() for pid in pids))

    def test_mdev_input_metadata_is_ready_before_labwc(self):
        manager = INPUT_MANAGER.read_text()
        controller_service = CONTROLLER_SERVICE.read_text()
        labwc_service = LABWC_SERVICE.read_text()
        self.assertIn('test --action=add "$event_path"', manager)
        self.assertIn("ID_INPUT_MOUSE=1", controller_service)
        self.assertIn("need dbus localmount elogind oculus-controller", labwc_service)


if __name__ == "__main__":
    unittest.main()
