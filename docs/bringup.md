# Monterey bring-up gates

Each subsystem below is verified separately. A later gate never inherits an
earlier gate's result: USB enumeration doesn't prove rootfs mounting, a 90 Hz
panel mode doesn't prove 90 FPS presentation, camera nodes don't prove
passthrough.

Reference firmware: `q1_22310100490800000` full OTA (Monterey Android 10,
2021-04 patch). It's an analysis input; no proprietary files are committed.

## 1. Boot and recovery

Expected chain:

1. The unlocked Oculus bootloader reads an Android boot-image v0 container.
2. The stock kernel ignores `skip_initramfs` (patched) and starts the pmOS
   initramfs.
3. USB CDC-NCM comes up at 172.16.42.1 with SSH; a bounded watchdog is armed.
4. An explicit mdev scan creates nodes for the UFS partition table (no
   devtmpfs on this kernel), including `system_b`.
5. The hook validates the 512-byte GPT extents inside the 4096-byte-sector
   `system_b` device and maps them with dm-linear.
6. Command-line UUIDs select `pmOS_boot`/`pmOS_root`, the watchdog is
   cancelled, OpenRC takes over.

Evidence collected before moving on:

```sh
cat /proc/cmdline
cat /proc/partitions
find /dev/disk/by-partlabel -maxdepth 1 -type l -ls
blkid
dmsetup ls --tree
mount
cat /etc/os-release
```

The root fs must be `/dev/mapper/oculus-pmos-root`, a linear extent inside
`system_b` — not Android's dm-verity `dm-0`. The loop-device sector override
is used only to decode GPT metadata; filesystem I/O through its partition
nodes corrupts on this kernel, while the equivalent read-only linear mapping
mounted ext4 fine. Keep boot_b/system_b backup hashes outside the repo.

This gate passed on hardware: both mappings matched their UUIDs, pmOS_root
mounted read-write, OpenRC completed, SSH worked over USB NCM. mdev runs as a
foreground daemon in normal boot and populates framebuffer/KGSL/SyncBoss/
input/media/V4L2 nodes before the default runlevel.

Recovery paths: `sudo /usr/sbin/oculus-reboot-bootloader` from any pmOS shell
(sync + `reboot-mode bootloader`, which the Qualcomm restart driver maps to the
bootloader reason). From the host: `scripts/oculus-usb-control
reboot-bootloader`. Debug images hold a root nc shell at port 23 for five
minutes unless boot continues. The timeout is tunable via
`oculus.recovery_timeout=SECONDS` (30-1800, 0 disables).

## 2. Display, GPU, refresh rate

Downstream stack: Qualcomm MDSS framebuffer plus KGSL, no DRM/KMS
(CONFIG_DRM off). Establish independently:

```sh
ls -l /dev/graphics /dev/kgsl-3d0 /sys/class/graphics/fb0
cat /sys/class/graphics/fb0/modes 2>/dev/null || true
oculus-refresh-rate status
oculus-refresh-rate 72
oculus-refresh-rate 90
```

A stable visible framebuffer, successful 72/90 writes, and measured
presentation at both rates are three separate proofs. DTB changes only set the
Lightman panel's default/max rate; compositor pacing lives elsewhere.

## 3. SyncBoss, IMU, controllers

Stock nodes: `/dev/syncboss0`, `_control0`, `_stream0`, `_powerstate0`, plus
sysfs SPI controls. First prove the kernel ABI without writing anything:

```sh
ls -l /dev/syncboss* /sys/devices/virtual/misc/syncboss0
find /sys/devices/virtual/misc/syncboss0 -maxdepth 5 -type f -print
dmesg | grep -iE 'syncboss|spi|imu|sensor'
```

Never write `swd/update_firmware`, `reset`, or `power` during discovery. A
native driver needs documented stream ABI reading, timestamp sync, calibration
loading, controller input, and pose fusion. Upstream Monado has Rift/Rift S
drivers but nothing for Monterey standalone; `monado-oculus-monterey` adds an
orientation-only backend for the v50 IMU packet (type 0x50).

## 4. Tracking cameras / passthrough

Read-only discovery first:

```sh
ls -l /dev/video* /dev/media* /dev/v4l-subdev* 2>/dev/null
for node in /dev/media*; do media-ctl -d "$node" -p; done
for node in /dev/video*; do v4l2-ctl -d "$node" --all; done
dmesg | grep -iE 'camera|v4l2|media|isp|csid|csiphy'
```

Tracking proof = timestamped frames + calibrated head pose. Passthrough proof
= correctly transformed stereo images presented by the compositor at
interactive latency. Opening a camera node proves nothing.

## 5. Audio, radio, platform services

Audio is blocked below firmware policy: the kernel logs
`msm8998-asoc-snd ... ASoC: platform (null) not registered` and registers no
ALSA cards. CM710X/QDSP platform registration has to be resolved first.

Firmware is now packaged (`firmware-oculus-monterey`) rather than exposed from
Android partitions at runtime. That keeps kernel firmware requests working even
if slot A changes state, and removes a whole class of mount-order problems.
Proprietary blobs live in the release tarball only, not git.

Wi-Fi status: QCACLD initializes after the `/sys/kernel/boot_wlan/boot_wlan`
write and `/dev/wlan` appears, but writing ON times out — ICNSS never gets its
firmware-ready QMI event because this kernel uses Qualcomm's old AF_MSM_IPC
IPC router instead of QRTR. `libqipcrtr4msmipc` bridges current libqrtr clients
to it; `oculus-rmtfs` registers QMI service 0x0e through that bridge using
rmtfs `-P -r` only (never `-s`, never opens subsystem devices).

Do not enable modem subsystem voting. A manual vote reached MBA but modem.b19
fell through PIL's direct loader into the userspace fallback, BusyBox mdev
couldn't find it at the time, and the vendor failure shutdown wedged until the
hardware watchdog barked. Top-level fallback links in /lib/firmware exist now,
but the path stays disabled until a full PIL audit passes offline.

## 6. OpenXR and KWin VR

KWin MR !8671 (still open draft as of 2026-08-22) needs Qt Quick 3D XR
(Qt >= 6.10.2), a working OpenXR runtime, patched Qt, and patched XWayland.
Order of work:

1. Gates 1-5 on hardware.
2. Monterey driver work in Monado (started: orientation-only IMU backend).
3. Compositor presenting directly to the panel, with
   `XR_FB_display_refresh_rate` mapped onto the validated 72/90 control.
4. Monado compositor smoke tests.
5. KWin VR packaging (done: pinned fork builds for aarch64).
6. Head-gaze, controllers, floating surfaces, passthrough composition,
   suspend/resume across cold boots.

KWin VR stays out of default images until OpenXR renders a stereo test scene
with real tracking. Current state: nested KWin reaches vrActive=true over
Lavapipe (software), desktop shows as a floating panel, visual alignment and
pose behavior await wearer review.

## Safety rules

- Never flash or modify abl/xbl or anything else in the boot chain.
- Slot A stays intact; mounts are read-only except the temporary exec bind the
  controller bridge creates under /run.
- No SyncBoss controller firmware-update/reset/unlock operations, ever.
- Don't claim anything works until it's observed on the headset after a cold
  boot (and sleep/wake where relevant).
