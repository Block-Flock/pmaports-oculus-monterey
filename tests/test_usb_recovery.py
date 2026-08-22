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
DEBUG_LOGIN = (
    ROOT / "device-oculus-monterey" / "oculus-initramfs-debug-login"
)
SUBPARTITION_MAPPER = (
    ROOT / "device-oculus-monterey" / "oculus-map-pmos-subpartitions"
)
FLASH_SLOT_B = ROOT / "scripts" / "flash-verified-slot-b"
MDEV_SERVICE = ROOT / "device-oculus-monterey" / "oculus-mdev.initd"
RECOVERY_SUDOERS = ROOT / "device-oculus-monterey" / "oculus-recovery.sudoers"
STOCK_FIRMWARE = ROOT / "device-oculus-monterey" / "oculus-stock-firmware"
STOCK_FIRMWARE_SERVICE = (
    ROOT / "device-oculus-monterey" / "oculus-stock-firmware.initd"
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

    def test_forced_debug_uses_persistent_busybox_nc(self) -> None:
        hook = INITRAMFS_HOOK.read_text()
        self.assertIn(
            "nc -lk -s 172.16.42.1 -p 23 -e /sbin/oculus-debug-login",
            hook,
        )
        self.assertNotIn("telnetd ", hook)

    def test_debug_login_discards_listener_arguments(self) -> None:
        login = DEBUG_LOGIN.read_text()
        self.assertIn("exec /bin/sh -l", login)
        self.assertNotIn('"$@"', login)

    def test_initramfs_maps_512_byte_gpt_with_dm_linear(self) -> None:
        mapper = SUBPARTITION_MAPPER.read_text()
        self.assertIn('"$mdev_command" -s', mapper)
        self.assertIn("OCULUS_SYSTEM_DEVICE", mapper)
        self.assertIn('PARTNAME=system_b', mapper)
        self.assertIn('--sector-size 512 "$system_device"', mapper)
        self.assertIn('losetup -d "$layout_loop"', mapper)
        self.assertIn('dmsetup create "$name" --table', mapper)
        self.assertIn("start % 8", mapper)
        self.assertIn("length % 8", mapper)
        self.assertIn('LABEL=\"pmOS_boot\"', mapper)
        self.assertIn('LABEL=\"pmOS_root\"', mapper)

    def test_storage_mapping_precedes_debug_listener(self) -> None:
        hook = INITRAMFS_HOOK.read_text()
        self.assertLess(
            hook.index('oculus-map-pmos-subpartitions'),
            hook.index('nc -lk -s 172.16.42.1'),
        )

    def test_slot_b_installer_measures_export_symlink_targets(self) -> None:
        installer = FLASH_SLOT_B.read_text()
        self.assertIn('boot_size=$(stat -Lc %s "$boot")', installer)
        self.assertIn('system_size=$(stat -Lc %s "$system")', installer)

    def test_normal_system_uses_foreground_mdev_daemon(self) -> None:
        service = MDEV_SERVICE.read_text()
        self.assertIn('command_args="-df"', service)
        self.assertIn('/sbin/mdev -s', service)
        self.assertIn('before udev udev-trigger', service)

    def test_wheel_refresh_control_is_argument_bounded(self) -> None:
        policy = RECOVERY_SUDOERS.read_text()
        self.assertIn('/usr/sbin/oculus-refresh-rate 72', policy)
        self.assertIn('/usr/sbin/oculus-refresh-rate 90', policy)
        self.assertNotIn('/usr/sbin/oculus-refresh-rate *', policy)

    def test_stock_firmware_mounts_only_slot_a_read_only(self) -> None:
        helper = STOCK_FIRMWARE.read_text()
        self.assertIn("find_partition modem_a", helper)
        self.assertIn("find_partition system_a", helper)
        self.assertNotIn("find_partition modem_b", helper)
        self.assertNotIn("find_partition system_b", helper)
        self.assertIn("ro,nosuid,nodev,noexec", helper)
        self.assertIn("ro,noload,nosuid,nodev,noexec", helper)
        self.assertNotIn("mount -o rw", helper)

    def test_stock_firmware_precedes_network_services(self) -> None:
        service = STOCK_FIRMWARE_SERVICE.read_text()
        self.assertIn("after oculus-mdev", service)
        self.assertIn("before networkmanager wpa_supplicant", service)


if __name__ == "__main__":
    unittest.main()
