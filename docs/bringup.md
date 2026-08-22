# Monterey bring-up gates

This document turns the Quest 1 firmware analysis into independently testable
postmarketOS milestones. A later gate must not be reported working from an
earlier gate's result. In particular, USB enumeration does not prove rootfs
mounting, a 90 Hz panel mode does not prove 90 FPS presentation, and camera
device nodes do not prove passthrough.

The reference firmware is the user-supplied `q1_22310100490800000` full OTA
(Monterey Android 10, 2021-04 security patch). Firmware files and proprietary
binaries are analysis inputs and are not redistributed by this repository.

## 1. Boot and recovery

Expected chain:

1. The unlocked Oculus bootloader reads an Android boot-image v0 container.
2. The stock-derived kernel ignores the bootloader's `skip_initramfs` token and
   starts the external pmOS initramfs.
3. USB CDC-NCM exposes `172.16.42.1` for recovery and diagnostics, while a
   bounded watchdog is armed.
4. An explicit `mdev` scan creates nodes for the UFS Android partition table,
   including `system_b`; the stock kernel does not provide devtmpfs.
5. The Monterey hook validates the 512-byte GPT extents stored inside the
   4096-byte-sector `system_b` device and maps them with `dm-linear`.
6. The UUIDs embedded in the boot command line select `pmOS_boot` and
   `pmOS_root`, the watchdog is cancelled, then OpenRC starts the installed
   system and keeps NCM plus SSH available.

Required evidence before continuing:

```sh
cat /proc/cmdline
cat /proc/partitions
find /dev/disk/by-partlabel -maxdepth 1 -type l -ls
blkid
dmsetup ls --tree
dmsetup table oculus-pmos-boot
dmsetup table oculus-pmos-root
mount
cat /etc/os-release
```

The expected root filesystem must be mounted from
`/dev/mapper/oculus-pmos-root`, whose linear extent is inside `system_b`, not
Android's verified-root `dm-0`. The 512-byte loop-sector override is used only
for reading GPT metadata on this downstream kernel. Live testing showed
out-of-range filesystem I/O through its partition nodes, while the equivalent
read-only linear mapping mounted the ext4 filesystem successfully. Keep the
exact `boot_b` and `system_b`
backup hashes outside the repository. Never write `abl`, `xbl`, or another
boot-chain partition.

On-device validation reached this gate with the matching boot/system pair: the
metadata-only loop exposed both GPT extents, both linear mappings matched the
command-line UUIDs, `pmOS_root` mounted read-write as `/`, OpenRC completed, and
authenticated SSH accepted commands over USB NCM. The first normal-system boot
also proved that udev cannot repopulate `/dev` without devtmpfs; the device
package now starts a foreground mdev daemon and performs an early full scan.
A subsequent read-back-verified cold boot confirmed that service stays up and
populates framebuffer, KGSL, SyncBoss, input, media, and V4L2 nodes before the
default runlevel.

At any pmOS shell, root can return directly to the bootloader with
`oculus-reboot-bootloader`. From the authenticated host control path, use
`scripts/oculus-usb-control reboot-bootloader`. The helper issues Linux
`RESTART2("bootloader")`, which Monterey's Qualcomm restart driver maps to the
bootloader restart reason. A debug-shell image automatically does this after
five minutes unless boot continues successfully. Connect to that bounded,
USB-only root shell with `nc 172.16.42.1 23`; it is not enabled in a normal
image.

## 2. Display, GPU, and refresh rate

The downstream stack uses Qualcomm MDSS framebuffer plus KGSL rather than a
validated DRM/KMS path. Establish these independently:

```sh
ls -l /dev/graphics /dev/kgsl-3d0 /sys/class/graphics/fb0
cat /sys/class/graphics/fb0/modes 2>/dev/null || true
oculus-refresh-rate status
oculus-refresh-rate 72
oculus-refresh-rate 90
```

Proof requires a stable visible framebuffer, successful 72/90 writes, and
measured presentation at both rates. The DTB changes only the Lightman panel's
default and maximum rate; they do not change application or compositor pacing.

## 3. SyncBoss, IMU, and controllers

Stock Android exposes `/dev/syncboss0`, `/dev/syncboss_control0`,
`/dev/syncboss_stream0`, and `/dev/syncboss_powerstate0`, plus SPI controls
under `/sys/devices/virtual/misc/syncboss0`. Its sensor HAL publishes camera,
controller, IMU, magnetometer, and power-state HIDL interfaces; trackingservice
then consumes that stack with real-time scheduling and a dedicated cpuset.

First prove the kernel ABI without changing firmware or issuing a SyncBoss
firmware update:

```sh
ls -l /dev/syncboss* /sys/devices/virtual/misc/syncboss0
find /sys/devices/virtual/misc/syncboss0 -maxdepth 5 -type f -print
dmesg | grep -iE 'syncboss|spi|imu|sensor'
```

Do not write the `swd/update_firmware`, `reset`, or `power` attributes during
initial discovery. A native OpenXR backend needs a documented reader for the
stream ABI, timestamp synchronization, calibration loading, controller input,
and pose fusion. Upstream Monado currently has Rift and Rift S drivers but no
Monterey/Quest standalone driver; an interaction-profile name is not a device
driver.

## 4. Tracking cameras and passthrough

Stock permissions identify `/dev/video*`, `/dev/media*`, `/dev/v4l-subdev*`,
`/dev/msm_camera/*`, `/dev/gemini0`, and JPEG devices. Android layers
`cameramuxmodeservice`, a proprietary camera provider, and tracking services on
top of them.

Read-only discovery comes first:

```sh
ls -l /dev/video* /dev/media* /dev/v4l-subdev* 2>/dev/null
for node in /dev/media*; do media-ctl -d "$node" -p; done
for node in /dev/video*; do v4l2-ctl -d "$node" --all; done
dmesg | grep -iE 'camera|v4l2|media|isp|csid|csiphy'
```

Tracking proof requires timestamped frames plus calibrated head pose. A
passthrough proof additionally requires a correctly transformed stereo image
presented by the compositor at interactive latency. Merely opening a camera
node is not enough.

## 5. Audio, radio, and platform services

Validate ALSA cards and playback/capture before adding a desktop policy layer.
Validate Wi-Fi, Bluetooth, thermal behavior, charging, battery reporting,
suspend, and resume separately. `oculus-stock-firmware` resolves the exact
`modem_a` and `system_a` PARTNAMEs, mounts both filesystems with read-only,
`nodev`, `nosuid`, and `noexec` options, and creates runtime-only links under
`/lib/firmware/postmarketos`. Proprietary modem/DSP firmware remains on the
preserved Android slot and is not committed to this repository.

The stock Wi-Fi sequence is now partially reproduced and has distinct proof
gates:

1. Android mounts `modem_a` at `/vendor/firmware_mnt`; its ueventd firmware
   search path is `/vendor/firmware_mnt/image/`.
2. The built-in `CONFIG_QCA_CLD_WLAN` driver waits for userspace to write to
   `/sys/kernel/boot_wlan/boot_wlan` after firmware storage is available.
3. That write successfully initialized the host driver and created `/dev/wlan`
   during a bounded debug boot.
4. Writing `ON` to `/dev/wlan` still timed out because ICNSS never received its
   firmware-ready QMI event, so no `wlan0` was created.

The downstream 4.4 kernel uses Qualcomm's old `AF_MSM_IPC` IPC Router rather
than modern `AF_QRTR`. The `libqipcrtr4msmipc` preload adapts current libqrtr
clients to that ABI. With the old kernel's `rmtfs` UIO node aliased to the name
current upstream rmtfs expects, `rmtfs -P -r` remained running and registered
QMI service `0x0e`, instance 1. The packaged `oculus-rmtfs` service reproduces
only that proven, no-write stage. It does not use rmtfs's `-s` remote-processor
control or open `/dev/subsys_modem`.

A subsequent bounded modem vote reached MBA, then firmware segment
`modem.b19` fell through the kernel's direct loader. BusyBox mdev ignores the
custom `firmware_class.path` and searches `/lib/firmware`, so the valid segment
was not found by fallback userspace. PIL's failure shutdown wedged and the
hardware watchdog reset the headset. The firmware service now supplies
collision-safe, runtime-only top-level links for that fallback, but a follow-up
vote still reset before new crash evidence could replace the occupied pstore
record. Do not enable a default subsystem vote. The next radio gate is an
offline-auditable capture of every PIL fallback request and successful remote
IPC transport registration, followed by ICNSS `FW READY`, a `wlan0` interface,
scan results, association, and sustained traffic.

Audio is independently blocked before firmware policy: the authentic kernel
currently reports `msm8998-asoc-snd ... ASoC: platform (null) not registered`
and registers no ALSA cards. Resolve the CM710X/QDSP platform registration
before treating firmware visibility as audio proof.

## 6. OpenXR and KWin VR

The KWin VR merge request is an application/compositor integration, not a Quest
driver. As checked on 2026-08-22, merge request !8671 is still an open draft and
requires Qt Quick 3D XR (Qt 6.10.2 minimum), a working OpenXR runtime, patched
Qt, and patched XWayland for complete X11 support.

The implementation order is therefore:

1. Complete gates 1-5 on the headset.
2. Add a Monterey device and tracking backend to Monado or an equivalent native
   OpenXR runtime.
3. Add a compositor target that presents directly to the internal display and
   maps `XR_FB_display_refresh_rate` requests to the validated 72/90 Hz control.
4. Pass Monado compositor and OpenXR conformance-oriented smoke tests.
5. Package the KWin VR branch and its matching Qt/XWayland patches.
6. Test head-gaze, controllers, floating Wayland surfaces, physical/virtual
   screens, passthrough composition, suspend/resume, and recovery across
   repeated cold boots.

Do not package KWin VR into the default image until the OpenXR runtime can
independently render a stereo test scene with working tracking.
