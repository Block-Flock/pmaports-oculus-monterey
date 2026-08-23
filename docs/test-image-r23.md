# Desktop test image r23

r23 supersedes r22 for the first desktop hardware trial. It adds a narrow
udev policy so the unprivileged graphical session can use KGSL and Monado can
open only the two SyncBoss nodes required for the v50 HMD IMU transport.
`syncboss_control0` and `syncboss_powerstate0` remain root-only.

This remains a hardware-validation image. Controller reconnection, display
presentation, refresh switching, HMD orientation, and nested VR have not yet
been validated on-device.

## Local reference pair

The matched images generated from device package `1-r23` are:

```text
62fe69381d69b8ad7275d28efbec3cb7620f7de7e21788e0d4e82b4fadb0d6a8  pmos-monterey-desktop-r23-boot-stock223-90hz.img
3eb4c86af8cb71f688dfa4e32fc53d371777467c38b3559fadd968919fb22ece  pmos-monterey-desktop-r23-system.img
```

The boot wrapper uses the exact owner-supplied v50 OTA kernel, patches the
single `skip_initramfs` token, retains all 14 DTBs, and sets the Lightman panel
range to 60-90 Hz with 90 Hz selected. Proprietary images are not committed.

The boot command line names `pmOS_boot` UUID
`f93cc644-761b-4e3e-b887-6944de3bf161` and `pmOS_root` UUID
`38d8001c-b12a-405b-b7b1-a17806540fb6`; direct filesystem probing of the
system image confirmed the same labels and UUIDs. The system image is
2,253,389,824 bytes, below the installer's guarded 2.5 GiB ceiling.

## Installation and rollback boundary

Use only `scripts/flash-verified-slot-b` from rooted Android slot A. It writes
only `boot_b` and `system_b`, reboots to A, hashes back exactly the written
ranges, and activates B only after both hashes match. Never flash ABL or XBL.

The first boot keeps pattern locking disabled so a controller failure cannot
lock out recovery. USB recovery and the controller bridge remain independent
OpenRC services. Follow the observation and log-capture checklist in
`test-image-r22.md`; its procedure applies unchanged to r23.
