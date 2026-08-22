# Monterey VR desktop plan

## Goal

Boot a small labwc desktop on Oculus Quest 1, then present selected desktop
windows in stereo through OpenXR. The session is deliberately smaller than a
full Plasma install:

1. labwc owns the normal desktop, launcher, settings, and recovery actions.
2. The patched KWin runs nested only when VR mode is requested.
3. Applications intended for VR connect to KWin's separate Wayland socket.
4. Monado is the OpenXR runtime used by KWin's VR plugin.
5. A Monterey Monado driver supplies the panel, headset pose, Touch controllers,
   and eventually passthrough.

The KWin source fork is
[`Block-Flock/kwin-oculus-monterey`](https://github.com/Block-Flock/kwin-oculus-monterey),
branch `oculus-vr-desktop`. It currently pins KDE merge request 8671 at commit
`ccdd46eadbd705c6ea2efb9c5de03e2fe5ec148a`, plus two Qt 6.11 include fixes
at fork commit `ad20b0ea6f9ec415cb3756f1d53ce419548fe6bf`.

The native device-driver work is in
[`Block-Flock/monado-oculus-monterey`](https://github.com/Block-Flock/monado-oculus-monterey),
branch `oculus-monterey`. Commit
`1d8bd7f0042320ef0af294f88ab80f1f2814dc4a` adds the first bounds-checked
SyncBoss HMD IMU parser and tests. It is not yet selected by this UI package:
the runtime remains on Alpine's stock Monado until hardware capture confirms
the packet layout and the driver owns sensor enable/disable cleanly.

## Why there are two compositors

KDE's VR mode is a KWin plugin and uses KWin-private window, input, and scene
APIs. It cannot be loaded into labwc. Keeping labwc as the base compositor and
running KWin as a nested Wayland client gives the headset a lightweight normal
desktop without rewriting the VR plugin.

The packaged commands are:

```sh
oculus-labwc-session       # start the base desktop
oculus-vr start            # start nested KWin on oculus-vr-0
oculus-vr-run APPLICATION  # start an application inside KWin VR
oculus-vr stop
```

KWin VR is not started automatically. Until the Monterey Monado driver works,
starting it can only exercise the nested compositor and failure diagnostics.

## Build the desktop packages

From a pmbootstrap checkout configured for `oculus-monterey`, build the custom
compositor first and the UI package second:

```sh
pmbootstrap build kwin-oculus-monterey
pmbootstrap build postmarketos-ui-oculus-labwc
```

The second package depends on labwc, Monado, and `kwin-oculus-monterey`, so
selecting this UI pulls in the complete two-compositor userspace. A successful
KWin APK contains `/usr/bin/kwin_wayland`,
`/usr/lib/qt6/plugins/kwin/plugins/vr.so`, the VR settings module, and
`/usr/lib/libexec/kwinvr-xrtest`. This is a build gate only; on-headset OpenXR,
tracking, display, and sleep/wake validation remain separate milestones.

## Why the GPU needs a compatibility layer

The v50 kernel has `CONFIG_DRM` disabled. It presents the display through
Qualcomm's Android framebuffer and KGSL drivers instead of Linux DRM/KMS. A
normal Alpine KWin or Monado install therefore cannot directly present frames
to this headset.

The owner's v50 system image contains the matching Adreno EGL, GLES and Vulkan
drivers, gralloc modules, Qualcomm hardware composer, and the Oculus composer
implementation. These files are proprietary and are not stored in this
repository. The port will discover them from the read-only `system_a` mount,
verify the supported v50 build, and expose only the files required by an
isolated Android-graphics compatibility process.

Package `postmarketos-ui-oculus-labwc` implements the initial diagnostic path:
Xorg scans out through `/dev/fb0`, and labwc runs on wlroots' nested X11 backend
with Pixman rendering. It proves panel presentation and input but is not
expected to sustain stereo 72 or 90 Hz. The same labwc session can later run on
the KGSL/Adreno/HWC compatibility host without changing its menu or KWin VR
launcher. A future DRM/MSM kernel port would remove both compatibility layers.

## Refresh-rate ownership

`oculus-refresh-rate 72` and `oculus-refresh-rate 90` select the panel mode.
The OpenXR compositor must independently pace its frame loop to the selected
rate and report measured presentation timing. A sysfs write alone is never
treated as proof that applications are rendering at that frame rate.

## Touch controller path

Quest Touch controllers do not use normal BlueZ pairing. The headset's
SyncBoss MCU owns a Pulsar radio and retains the paired-controller state. The
stock v50 userspace exposes controller enumeration, pairing, wake/sleep,
battery, calibration, input streaming, and haptics through the SyncBoss device
nodes.

The planned bridge has two parts:

- A small privileged service that talks to SyncBoss and exports normalized
  controller state to Monado.
- An unprivileged shell client for status, left/right pairing, battery,
  reconnect, and haptic tests.

The device package also installs `oculus-syncboss-dump`, a deliberately
read-only stream probe used to map the MCU packet format before that bridge is
enabled. It opens only `/dev/syncboss_stream0`, never sends an ioctl, and never
opens the power, control, or command nodes. Capture a short sample with:

```sh
doas oculus-syncboss-dump -n 16 -t 3000 >syncboss-idle.txt
```

Repeat while moving the headset, then compare record types and changing fields.
A v50 HMD IMU packet is reported as type `0x50`; the probe decodes its MCU
timestamp, acceleration in m/s2, angular velocity in rad/s, and metadata while
retaining the complete hex record for format validation. This layout was
derived from the exact v50 `libsyncboss.so` packet handler and must still be
confirmed against captures from the headset.
A timeout means no producer has enabled the relevant sensor stream; it is not a
reason to write an unverified command to SyncBoss. Captures can contain device
timing and controller identifiers, so redact them before attaching them to a
public issue.

Package revision r17 includes the first strict command gateway. It runs the
owner's `syncboss_input_tool` with the Android linker directly from the
read-only slot-A mount and accepts only status, list, scan, watch, pair,
stream, battery, sleep, and bounded-haptic operations. The accompanying
OpenRC watcher is packaged but is not enabled by default until passive
enumeration and sleep/wake have passed an on-headset test.

Pairing currently selects a discovered hardware device ID; left/right mapping
comes from the controller type reported by SyncBoss. A future shell UI can
label those types after the Quest 1 and Quest 2 values are verified. It must
not guess a hand from connection order.

Quest 2 controller compatibility is tracked as an experimental follow-up. A
user-supplied module showed that v50 can pair those controllers after two
checks in `libsyncboss` are changed. The port will reproduce those changes only
in a device-local copy made from the owner's exact v50 library. Controller
firmware-update entry points and every CLI update flag must fail closed.
Neither the stock library, the modified library, controller serials, nor
pairing data may be committed or included in an APK.

## Safety rules

- Never flash or modify ABL or XBL.
- Keep Android slot A intact and mount its partitions read-only.
- Keep USB NCM recovery and `oculus-reboot-bootloader` active in every desktop
  image.
- Do not call SyncBoss controller firmware-update, forced-update, unlock,
  reset-to-download-mode, or device-lock operations.
- Do not claim 72/90 Hz, tracking, passthrough, or controller reconnect works
  until it has been observed on the headset after a cold boot and sleep/wake
  cycle.

## Milestones

- [x] Stable slot-B boot and USB recovery.
- [x] Publish the KWin VR fork at the exact KDE merge-request revision.
- [x] Package a labwc base desktop and guarded nested-KWin launcher.
- [x] Build the patched KWin VR plugin and `kwin_wayland` for aarch64.
- [ ] Show the framebuffer/labwc diagnostic on the panel.
- [ ] Start the patched KWin VR plugin on the headset against Monado.
- [ ] Capture and document real SyncBoss IMU records with the read-only probe.
- [ ] Start Monado with a Monterey hardware backend and render a stereo test
      scene (never substitute simulated pose for this gate).
- [ ] Present through the v50 Qualcomm graphics compatibility layer.
- [ ] Enumerate already-paired Quest 1 Touch controllers without firmware
      writes.
- [ ] Pair left and right Quest 1 Touch controllers and reconnect after
      sleep/wake.
- [ ] Add guarded Quest 2 Touch pairing without firmware writes.
- [ ] Feed controller actions, battery, haptics, and pose data into Monado.
- [ ] Add headset 6DoF tracking and controller optical fusion.
- [ ] Add camera passthrough and a shell toggle.
- [ ] Measure stable 72 Hz and 90 Hz presentation on-device.
