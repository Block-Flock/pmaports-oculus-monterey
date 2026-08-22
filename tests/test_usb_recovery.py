#!/usr/bin/env python3
"""Host-side execution tests for the persistent USB recovery service."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICE = ROOT / "device-oculus-monterey" / "oculus-usb-recovery"
INITRAMFS_HOOK = (
    ROOT / "device-oculus-monterey" / "oculus-initramfs-recovery-hook"
)


class UsbRecoveryTest(unittest.TestCase):
    def test_configures_ncm_and_starts_single_address_dhcp(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            configfs = base / "configfs"
            net_class = base / "net"
            function = configfs / "functions" / "ncm.usb0"
            function.mkdir(parents=True)
            (function / "ifname").write_text("usb-test0\n")
            (net_class / "usb-test0").mkdir(parents=True)

            calls = base / "calls"
            mock = base / "mock"
            mock.write_text(
                "#!/bin/sh\n"
                "printf '%s\\n' \"$*\" >>\"$OCULUS_TEST_CALLS\"\n"
            )
            mock.chmod(0o755)

            environment = os.environ.copy()
            environment.update(
                {
                    "OCULUS_CONFIGFS": str(configfs),
                    "OCULUS_NET_CLASS": str(net_class),
                    "OCULUS_IP_COMMAND": str(mock),
                    "OCULUS_DHCPD": str(mock),
                    "OCULUS_TEST_CALLS": str(calls),
                }
            )
            result = subprocess.run(
                ["/bin/sh", str(SERVICE)],
                env=environment,
                text=True,
                capture_output=True,
                timeout=5,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                calls.read_text().splitlines(),
                [
                    "link set usb-test0 up",
                    "address replace 172.16.42.1/24 dev usb-test0",
                    "-i usb-test0 -s 172.16.42.1 -c 172.16.42.2",
                ],
            )

    def test_initramfs_watchdog_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            cmdline = base / "cmdline"
            pidfile = base / "watchdog.pid"
            kmsg = base / "kmsg"
            cmdline.write_text("pmos_force_initramfs\n")
            pidfile.write_text(f"{os.getpid()}\n")
            environment = os.environ.copy()
            environment.update(
                {
                    "OCULUS_CMDLINE_PATH": str(cmdline),
                    "OCULUS_WATCHDOG_PIDFILE": str(pidfile),
                    "OCULUS_KMSG_PATH": str(kmsg),
                }
            )

            result = subprocess.run(
                ["/bin/sh", str(INITRAMFS_HOOK)],
                env=environment,
                text=True,
                capture_output=True,
                timeout=5,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(pidfile.read_text(), f"{os.getpid()}\n")
            self.assertIn("already armed", kmsg.read_text())

    def test_forced_telnet_is_supervised_in_foreground(self) -> None:
        hook = INITRAMFS_HOOK.read_text()
        self.assertIn('telnetd -F -b "172.16.42.1:23" -l /bin/sh', hook)
        self.assertIn("Monterey telnetd exited; restarting", hook)


if __name__ == "__main__":
    unittest.main()
