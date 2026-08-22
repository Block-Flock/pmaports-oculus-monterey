# postmarketOS: Oculus Quest 1 (Monterey)

This is an early downstream-kernel port for the original Oculus Quest. It is
not yet a complete Android replacement image and it does not alter the boot
chain.

The current verified milestone is an installed postmarketOS edge system with
its embedded root filesystem mounted read-write, OpenRC running, and
authenticated SSH reachable over stable USB NCM. The initramfs UFS mappings
and matching UUID handoff were proven on-device. The framebuffer reports its
2880x1600 90 Hz mode, but visible compositor output, measured 72/90
presentation, Wi-Fi, Bluetooth, audio, tracking, passthrough, and a VR desktop
remain separate validation milestones until they pass on-device tests. The
normal-system mdev service has been cold-booted successfully and populates the
framebuffer, KGSL, SyncBoss, input, media, and V4L2 nodes.

## Display rate

The `q1_22310100490800000` OTA defaults the Lightman panel to 72 Hz and caps
dynamic FPS at 72 in all 14 appended DTBs. Newer production firmware examined
on the test headset exposes a 90 Hz Lightman mode
(`debug.oculus.refreshRate=90`, SurfaceFlinger allowed configuration `90 Hz`).
`90hz-default-v2.patch` makes 90 Hz the source-built kernel default while
retaining the downstream driver's dynamic-FPS support. The stock-kernel image
builder described below applies the same two 72-to-90 DTB cell changes locally.

After booting postmarketOS, use the root-only selector:

```sh
oculus-refresh-rate status
oculus-refresh-rate 72
oculus-refresh-rate 90
oculus-refresh-rate uncapped
```

It writes only `/sys/class/graphics/fb0/dynamic_fps`. Some downstream builds do
not expose readback, so the helper reports that limitation instead of treating
an empty read as proof of failure. `measured-fps` is a diagnostic value and can
be zero when no active framebuffer client is presenting.

`uncapped` selects the panel driver's supported maximum, currently 90 Hz; it
cannot exceed the physical panel capability. Panel refresh and VR compositor
frame rate are different controls. A 90 Hz panel mode does not make the Oculus
Android VR runtime render at 90 FPS. The
Android runtime currently observed on the test headset reports failures such as
`WaitForNextBaseVsync is stuck` and `WarpSwap: MakeRequest failed`; those must
be solved in an OpenXR/runtime implementation, not by changing the panel DTB.

## Firmware and boot structure

The examined full OTA is an Android update payload containing separate `boot`,
`system`, `modem`, `rpm`, `tz`, `hyp`, `pmic`, `keymaster`, `cmnlib`,
`cmnlib64`, `devcfg`, `ovrtz`, `abl`, and `xbl` partitions. This port needs only
the user-supplied `boot` image as a hardware-compatible kernel template. The
guarded workflow does not extract or write `abl` or `xbl`.

Monterey uses an Android boot-image v0 header with 4096-byte pages, kernel load
address `0x00008000`, ramdisk address `0x01000000`, second-stage address
`0x00f00000`, and tags address `0x00000100`. A 4096-byte legacy DER
BootSignature page follows the aligned payload. The bootloader adds
`skip_initramfs root=/dev/dm-0 init=/init`, so an unmodified stock kernel skips
the pmOS ramdisk even when that ramdisk is present.

Android slot selection normally maps `system_b` directly as the root
filesystem. A pmOS system image instead places a small GPT inside `system_b`:
partition 1 is `pmOS_boot` and partition 2 is `pmOS_root`. This stock kernel
reports UFS with 4096-byte logical sectors and has no devtmpfs filesystem,
while the embedded GPT uses 512-byte LBAs. Its old loop driver misaddresses
filesystem I/O when asked to override that sector size. The device initramfs
hook therefore runs an explicit `mdev` scan, uses a read-only 512-byte loop view
only to decode the GPT metadata, detaches it, then creates validated,
4096-aligned `dm-linear` mappings for the two extents before generic pmOS root
discovery. It checks the physical bounds and the
`pmOS_boot`/`pmOS_root` labels before continuing.
The boot image and system image must come from the same `pmbootstrap install`;
mixing artifacts from different installs leaves UUIDs that cannot match.

The stock tracking and passthrough stack is not a single kernel toggle. It uses
the built-in SyncBoss and camera drivers together with Android-specific sensor
HALs, `trackingservice`, `cameramuxmodeservice`, `vrapiserver`, Binder/HIDL,
SurfaceFlinger, calibration data, and device-specific permissions. Bring-up on
Alpine must first prove the kernel devices (`syncboss`, V4L2/media, framebuffer,
and KGSL), then provide native userspace interfaces or an explicitly isolated
compatibility layer. The proprietary Android services are not copied into the
rootfs by this repository.

## Build

Use a current `pmbootstrap` checkout with this repository's package directories
in the pmaports `device/downstream` category. Build the kernel and device
package, then create the normal postmarketOS artifacts:

```sh
pmbootstrap build linux-oculus-monterey
pmbootstrap build device-oculus-monterey
pmbootstrap install
pmbootstrap export ./export
```

This downstream 4.4 tree must be compiled with pmaports' `gcc4` toolchain. The
known-working OTA kernel was built with Android GCC 4.9; an Alpine GCC 15 build
returned directly to fastboot, while the GCC 4.9 package build reaches the
expected container layout. The package selects GCC4 automatically.

Monterey's bootloader adds Android's `skip_initramfs` argument. The
`honor-pmos-initramfs.patch` kernel change and `pmos_force_initramfs` device
argument are both required; without them the external postmarketOS initramfs is
discarded and the kernel tries Android's dm-verity root instead.

The unlocked bootloader also expects a parseable 4096-byte legacy Oculus
BootSignature container. pmbootstrap does not emit it, and its mkbootimg
version records a zero second-stage address when there is no second payload.
There are two image paths.

For the fully open source kernel, finalize the exported image using a
personally backed-up, known-working Monterey boot image as the structural
template:

```sh
scripts/prepare-monterey-boot \
  export/boot.img /path/to/known-good-monterey-boot.img \
  export/boot-monterey.img
```

The finalizer does not contain a key, create a valid cryptographic signature,
or access the headset. It is only suitable for an already-unlocked Monterey.
Do not use a raw Android OTA boot image as the postmarketOS boot image.

For hardware bring-up, the public kernel source has an important limitation:
it omits `drivers/staging/oculus/internal`, and its uncompressed kernel is about
2.1 MB smaller than the authentic OTA kernel. Generate a local image around a
user-supplied OTA `boot.img` so those built-in hardware drivers remain present:

```sh
scripts/prepare-monterey-stock-kernel-boot \
  export/boot.img /path/to/extracted-ota-boot.img \
  export/boot-monterey-stock-kernel-90hz.img
```

This builder does not include or download proprietary files. It makes exactly
these payload changes: `skip_initramfs` to the same-length unrecognized token
`xkip_initramfs` in the uncompressed kernel, and the Lightman default/max cells
from 72 to 90 in each appended DTB. It takes the pmOS ramdisk and UUID command
line from `export/boot.img`, retains the OTA header, and recreates the legacy
signature container. `--refresh-rate 72` produces a 72 Hz default instead.
The signature remains cryptographically stale and therefore requires an
already-unlocked headset.

An unlocked headset may display Oculus's untrusted/corrupt-software warning
before starting this image. That warning occurs before Linux and can delay USB
NCM enumeration. This repository does not suppress it by modifying `vbmeta`,
ABL, XBL, or another verified-boot component; only an Oculus-trusted signing
key could make a locally rebuilt payload trusted by the stock bootloader.

Once pmOS reaches its normal initramfs hook stage, it arms a five-minute
recovery watchdog. For a bounded bring-up session, add `--debug-shell`; this
puts `oculus.force-debug` at the front of Monterey's primary command-line field
and holds the image at a root TCP shell on `172.16.42.1:23`. Connect from the
host with `nc 172.16.42.1 23`. Run `/usr/sbin/oculus-reboot-bootloader` to
return immediately. Otherwise, the
watchdog automatically returns the headset to its bootloader rather than
leaving it stuck in initramfs. Set `oculus.recovery_timeout=SECONDS` on the
kernel command line to choose 30-1800 seconds; zero explicitly disables it.

Run the proprietary-free transformer regression tests with:

```sh
python3 -m unittest discover -s tests -v
```

The supplied OTA identifies itself as Monterey Android 10 build
`22310100490800000`, security patch 2021-04, timestamp 2022-01-12. Extract only
the `boot` and `system` payload partitions for this workflow. Never flash or
modify payload entries named `abl` or `xbl`.

Before a device trial, confirm the generated boot image contains the patched
DTB, the rootfs contains `/usr/sbin/oculus-refresh-rate`, and the kernel config
has `CONFIG_DEVTMPFS_MOUNT`, `CONFIG_FRAMEBUFFER_CONSOLE`, and USB gadget
support.

## Device trial and recovery boundary

The Quest is A/B. Keep a known-working Android installation and exact partition
backups on slot A. The Linux trial may target **only** `boot_b` and `system_b`;
preserve known-good copies of both B partitions first. Do not flash, erase, or
modify `abl_a`, `abl_b`, `xbl_a`, `xbl_b`, or any other boot-chain partition.

Start in fully booted Android slot A with root ADB, then use the guarded
installer. It checks the product, serial, unlock state, image sizes and
alignment, flashes explicitly named B partitions, returns to A, hashes the
exact written ranges, and activates B only after both hashes match:

```sh
MONTEREY_SERIAL=YOUR_SERIAL scripts/flash-verified-slot-b \
  export/boot-monterey.img export/oculus-monterey.img \
  --confirm-overwrite-monterey-slot-b
```

If a B trial returns to fastboot, recover without writing a partition:

```sh
scripts/return-to-slot-a
```

The repository's USB and flash helpers contain no ABL or XBL write target.

After the installed system starts, the device package runs BusyBox mdev for the
stock kernel (which has no devtmpfs), keeps the NCM link at `172.16.42.1`,
serves the host `172.16.42.2`, and starts SSH. An authenticated wheel user may
invoke only the dedicated bootloader helper and exact refresh-rate selector
arguments without a second password prompt. From the host:

```sh
scripts/oculus-usb-control status
scripts/oculus-usb-control reboot-bootloader
```

The host helper selects ADB when Android is running and authenticated SSH when
postmarketOS is running. It never contains a flash or erase operation.

## Validation checklist

- Confirm the device does not return directly to fastboot and that USB
  networking exposes the postmarketOS initramfs or installed system.
- Confirm the embedded boot/root UUIDs match the filesystems in the system
  image.
- Boot reaches a local shell and the panel is stable at the default 90 Hz.
- `oculus-refresh-rate 72` and then `oculus-refresh-rate 90` each report the
  requested value after the write.
- Check controller tracking, head tracking, audio, Wi-Fi, suspend/resume, and
  thermal behavior separately.
- Treat an OVR Metrics value from Android as a runtime pacing observation, not
  proof of a Linux panel cap. On the examined Android firmware, both Oculus
  and SurfaceFlinger properties already report 90 Hz.

## VR desktop status

KWin MR !8671 is not a device driver or panel fix. It requires a DRM/KMS
graphics path, a working OpenXR runtime, Qt Quick 3D XR, and working head and
controller tracking. This port currently uses the Quest downstream framebuffer
driver, so the correct order is: boot and display, USB/network recovery,
firmware-backed sensors and input, DRM/KMS or a dedicated compositor path,
OpenXR runtime, then KWin VR. Copying the Android Oculus runtime into
postmarketOS is not a reliable substitute because it depends on Android Binder,
SurfaceFlinger, vendor services, and proprietary runtime interfaces.

The public kernel checkout references a missing
`drivers/staging/oculus/internal/Kconfig`; this port removes that unavailable
menu entry and empty Makefile descent so the public source builds without
pretending the internal drivers are present. The generated stock-kernel path
is therefore the current candidate for tracking, SyncBoss, and passthrough
bring-up, while the GCC4 source build remains independently reproducible.

[KWin MR !8671](https://invent.kde.org/plasma/kwin/-/merge_requests/8671)
remains a later integration candidate after DRM/OpenXR/tracking are working.
The subsystem-by-subsystem proof gates and current runtime integration order are
documented in [docs/bringup.md](docs/bringup.md).
