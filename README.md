# postmarketOS on Oculus Quest 1 (monterey)

Downstream port for the original Quest, based on the stock 4.4 kernel. Boots
from slot B, keeps Android intact on slot A, and never touches abl/xbl.

What works right now: cold boot into an installed postmarketOS system, SSH over
USB NCM (172.16.42.1), labwc desktop visible through the panel, and a nested
KWin VR session rendering through Monado/OpenXR (software rendering for now).
Touch controllers enumerate through libinput via a bridge to the stock SyncBoss
userspace. Not working yet: GPU acceleration, tracking, passthrough, Wi-Fi,
audio, measured 72/90 Hz presentation.

Packages in this repo:

| Package | Purpose |
| --- | --- |
| `device-oculus-monterey` | device package: services, udev rules, sudo policy |
| `linux-oculus-monterey` | kernel built from the public Oculus source (gcc4) |
| `firmware-oculus-monterey` | WLAN/BT/GPU/ADSP firmware extracted from the v50 OTA |
| `oculus-monterey-initramfs-support` | initramfs recovery hook and subpartition mapper |
| `postmarketos-ui-oculus-labwc` | labwc session + nested KWin VR launchers + pattern lock |
| `kwin-oculus-monterey` | KWin with KDE MR !8671 VR mode, pinned fork |
| `monado-oculus-monterey` | Monado with a Monterey SyncBoss IMU driver |

## Boot details worth knowing

Monterey's bootloader appends `skip_initramfs root=/dev/dm-0 init=/init`, so the
kernel carries a small patch (`honor-pmos-initramfs.patch`) plus the
`pmos_force_initramfs` argument to use the pmOS ramdisk instead. The unlocked
bootloader also wants Oculus's legacy 4096-byte BootSignature page after the
boot payload; pmbootstrap doesn't produce one, so image finalizing uses a
known-good boot image as a structural template
(`scripts/prepare-monterey-boot`, no crypto, unlocked devices only). This is a
local bring-up aid and is not a supported postmarketOS kernel build path.

pmOS lives inside `system_b`: the system image contains a small GPT with
`pmOS_boot` and `pmOS_root`. The stock kernel reports UFS at 4096-byte logical
sectors while that GPT uses 512-byte LBAs, and its loop driver gets partition
I/O wrong when you override the sector size. The initramfs hook therefore reads
the GPT through a throwaway read-only loop view, detaches it, and creates
4096-aligned dm-linear mappings instead. This kernel has no devtmpfs either, so
an mdev daemon creates device nodes for both initramfs and normal boot.

Boot and system images must come from the same `pmbootstrap install`; the UUIDs
have to match.

## Firmware

`firmware-oculus-monterey` ships the needed blobs as real files under
`/lib/firmware/` — WCN3990 WLAN and BT firmware, Adreno 540 (a530/a540) files,
ADSP, and the CM710X codec blob. They were extracted from the owner's
`q1_22310100490800000` OTA; the tarball is attached to a GitHub release here and
is not in git. Nothing mounts Android partitions just to expose firmware
anymore.

Wi-Fi is still not functional: QCACLD loads and `/dev/wlan` appears, but this
kernel speaks Qualcomm's old `AF_MSM_IPC` router rather than QRTR. `rmtfs`
runs through the `libqipcrtr4msmipc` preload in a no-write mode. Do not enable
modem subsystem voting — a manual vote wedged PIL's failure path once and took
a watchdog reset to recover from.

## Build

```sh
pmbootstrap build linux-oculus-monterey
pmbootstrap build device-oculus-monterey
pmbootstrap install
```

The 4.4 tree needs pmaports' gcc4 toolchain (selected automatically); Alpine's
modern GCC produces a kernel that goes straight back to fastboot.

Hardware testing has also used locally prepared images containing the OTA
kernel. That workflow is outside postmarketOS support and is only useful for
bring-up comparison. The port targets the source-built
`linux-oculus-monterey` package; end-to-end panel validation of that kernel is
still pending.

## Flashing and recovery

Slot B only (`boot_b`, `system_b`). Keep backups of both B partitions before
the first flash. Never write abl or xbl, on either slot.

```sh
MONTEREY_SERIAL=YOUR_SERIAL scripts/flash-verified-slot-b \
  export/boot.img export/oculus-monterey.img \
  --confirm-overwrite-monterey-slot-b
scripts/return-to-slot-a        # if a trial lands in fastboot
```

The installer verifies product/serial/unlock state, flashes only the two named
B partitions, hashes back what it wrote, and switches slots only after both
hashes match.

Once booted, USB NCM gives you SSH at `user@172.16.42.1`. To get back to
fastboot from an OpenRC pmOS shell, run `sudo reboot-mode bootloader`; from the
host, run `scripts/oculus-usb-control reboot-bootloader`.

If a boot fails before switch-root, a watchdog returns the headset to the
bootloader after five minutes by default (`oculus.recovery_timeout=SECONDS` to
change, 0 disables). Debug images hold an nc root shell on port 23 instead.

## Desktop and VR

`postmarketos-ui-oculus-labwc` starts labwc through Xorg fbdev — enough for a
visible desktop, nowhere near VR frame rates. `oculus-vr start` launches the
patched KWin nested on a separate Wayland socket with Monado underneath; the
current display path is Lavapipe software rendering until someone writes an
Adreno/KGSL compatibility layer or ports the kernel to DRM. See
[docs/vr-desktop.md](docs/vr-desktop.md) for the design and
[docs/bringup.md](docs/bringup.md) for per-subsystem gates.

Controllers don't use Bluetooth pairing — the SyncBoss MCU owns the radio.
The bridge runs the stock v50 input tool from a temporary executable bind of
the inactive slot's system tree (read-only everywhere else) and feeds uinput;
controller firmware updates are unreachable by design. Quest 2 controller
pairing is a later, experimental follow-up.

## Tests

Host-side regression tests (script behavior, package consistency):

```sh
python3 -m pytest tests/ -v
```
