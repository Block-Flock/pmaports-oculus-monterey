# Desktop test image r22

This is the first bounded slot-B image containing the labwc desktop, nested
KWin VR shell, Monterey Monado runtime, Touch-to-uinput bridge, and optional
pattern lock. It is a hardware-validation image, not a release claiming that
display presentation, controller mapping, tracking, or VR is complete.

## Reproduce

Build from pmaports commit
`35d43c5df525f074ec0c187397cc34cc5df0550f` with UI
`oculus-labwc` and SSH public-key installation enabled. Run `pmbootstrap
install --no-sparse`, export the matched artifacts, then wrap the exported boot
image with the owner's exact v50 boot image:

```sh
scripts/prepare-monterey-stock-kernel-boot \
  export/boot.img /path/to/v50/boot.img \
  export/boot-monterey-desktop-r22-stock-90hz.img \
  --refresh-rate 90
```

The locally generated reference pair has these hashes:

```text
1dcccb13951e0d80ff7a210263b6ec47736a8d9ee4a8cea8fa61f52c799c9c02  boot-monterey-desktop-r22-stock-90hz.img
ffddc2407c76a746de6ad9ddc33dac95f3eaf52bbb2ec54e829d60c9679320e2  oculus-monterey.img
```

The boot wrapper contains user-supplied proprietary kernel bytes and must not
be uploaded to this repository. The boot and system images must remain a
matched pair: their embedded `pmOS_boot` and `pmOS_root` UUIDs were verified as
`77cad747-865f-4418-b633-f06eb45c0987` and
`5d7a338a-9b82-4694-a775-eacbea39c3be` respectively.

## Pre-flash audit recorded for this pair

- Boot image parses as Android boot-image v0 with the v50 load addresses and
  Android 10 / 2021-04 fields.
- The stock kernel contains the `xkip_initramfs` patch and all 14 Lightman DTBs
  select a 60-90 Hz range with 90 Hz default.
- The 2.149 GB system image fits the guarded 2.5 GB `system_b` ceiling.
- Device r22, labwc UI r3, KWin fork, Monado fork, gtklock pattern module,
  tinydm, and the PAM SSH server are installed.
- Controller and USB recovery services are in the default OpenRC runlevel.
- The host SSH public key is present; pattern locking is not enabled.
- The initramfs contains the five-minute recovery watchdog, USB debug/recovery
  plumbing, dm-linear partition mapper, and bootloader reboot helper.
- Repository tests pass 34/34.

## Install boundary

Boot known-good Android slot A with root ADB, verify the exact files against
the hashes above, and invoke only the guarded installer:

```sh
MONTEREY_SERIAL=YOUR_SERIAL scripts/flash-verified-slot-b \
  export/boot-monterey-desktop-r22-stock-90hz.img \
  export/oculus-monterey.img \
  --confirm-overwrite-monterey-slot-b
```

The installer names only `boot_b` and `system_b`, returns to Android A to hash
the written ranges, and activates B only after both hashes match. Never flash
ABL, XBL, or another boot-chain partition.

## First-boot observations

Do not interpret one successful stage as proof of the next. Record each item:

1. Whether the bootloader warning clears and OpenRC/USB NCM appears within five
   minutes.
2. Whether the panel is black, shows a console, shows Xorg, or reaches labwc.
3. Whether either paired controller reconnects and moves/clicks the pointer.
4. Whether `oculus-refresh-rate status`, `72`, and `90` succeed. This does not
   prove compositor FPS.
5. Whether Monado detects the HMD without an IMU timeout and whether head
   rotation axes/direction are correct.
6. Whether `oculus-vr start` creates the nested Wayland socket and whether its
   OpenXR diagnostics fail before or after compositor creation.
7. Whether USB SSH remains available throughout and
   `sudo oculus-reboot-bootloader` returns safely to fastboot.

After SSH connects, capture these privately before rebooting:

```sh
rc-status -a
sudo rc-service oculus-controller status
sudo tail -n 200 /var/log/oculus-controller.log
sudo oculus-controller list
oculus-refresh-rate status
dmesg | tail -n 300
```

Controller output can contain hardware identifiers. Redact them before posting
logs publicly. If the controller bridge fails, USB recovery remains independent
and the service can be stopped with `sudo rc-service oculus-controller stop`.
Enable the pattern lock only after pointer input works:

```sh
sudo oculus-pattern-setup enable
oculus-pattern-lock
```
