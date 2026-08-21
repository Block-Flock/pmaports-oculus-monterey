# postmarketOS: Oculus Quest 1 (Monterey)

This is an early downstream-kernel port for the original Oculus Quest. It is
not an Android replacement image and it does not alter the boot chain.

## Display rate

The production firmware examined on this Monterey headset exposes a 90 Hz
Lightman panel mode (`debug.oculus.refreshRate=90`, SurfaceFlinger allowed
configuration `90 Hz`). The kernel source used by this port instead defaulted
to 72 Hz and capped dynamic FPS at 72. `90hz-default.patch` makes 90 Hz the
kernel default while retaining the downstream driver's dynamic-FPS support.

After booting postmarketOS, use the root-only selector:

```sh
oculus-refresh-rate status
oculus-refresh-rate 72
oculus-refresh-rate 90
```

It writes only `/sys/class/graphics/fb0/dynamic_fps` and verifies the value
read back. It never patches or flashes a boot image.

## Build

Use a current `pmbootstrap` checkout with this repository as the aports tree.
Build the kernel and device package, then create normal postmarketOS boot and
rootfs artifacts for `oculus-monterey`. Do not use a raw Android OTA boot image
as a postmarketOS boot image.

Before a device trial, confirm the generated boot image contains the patched
DTB and that the rootfs contains `/usr/sbin/oculus-refresh-rate`.

## Device trial and recovery boundary

The connected unit is A/B and currently boots slot `_a`. Keep it that way
until the postmarketOS images have passed build-time checks. The initial test
may target **only** `boot_b` and `system_b`; preserve a known-good copy of
both partitions first. Do not flash, erase, or modify `abl_a`, `abl_b`,
`xbl_a`, `xbl_b`, or any other boot-chain partition.

In fastboot, inspect variables before writing and explicitly name the B-slot
partitions. After a failed B-slot trial, return to the saved B images or select
slot A through the already-unlocked bootloader's documented mechanism. Do not
change active-slot state until the B boot has been observed and tested.

## Validation checklist

- Boot reaches a local shell and the panel is stable at the default 90 Hz.
- `oculus-refresh-rate 72` and then `oculus-refresh-rate 90` each report the
  requested value after the write.
- Check controller tracking, head tracking, audio, Wi-Fi, suspend/resume, and
  thermal behavior separately.
- Treat an OVR Metrics value from Android as a runtime pacing observation, not
  proof of a Linux panel cap. On the examined Android firmware, both Oculus
  and SurfaceFlinger properties already report 90 Hz.

## KWin VR MR

KWin MR !8671 is a draft VR desktop plugin requiring a working OpenXR runtime,
Qt Quick 3D XR, and additional Qt/Xwayland patches. It is not a panel driver
or a 72/90 Hz fix. Consider it only after the kernel display, tracking, and an
OpenXR runtime are independently working.
