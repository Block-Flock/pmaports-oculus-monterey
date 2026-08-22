# Monterey VR desktop plan

## Goal

Boot a small Wayland desktop on Oculus Quest 1, then present that desktop in
stereo through OpenXR. The first useful session is deliberately smaller than a
full Plasma install:

1. KWin with KDE's VR plugin.
2. A small shell with a launcher, status panel, settings, and recovery action.
3. Monado as the OpenXR runtime.
4. A Monterey Monado driver for the panel, headset pose, Touch controllers,
   and eventually passthrough.

The KWin source fork is
[`Block-Flock/kwin-oculus-monterey`](https://github.com/Block-Flock/kwin-oculus-monterey),
branch `oculus-vr-desktop`. It currently pins KDE merge request 8671 at commit
`ccdd46eadbd705c6ea2efb9c5de03e2fe5ec148a`.

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

The initial visible-desktop milestone may use Xorg's framebuffer driver and
software rendering as a diagnostic path. That proves panel presentation and
input but is not expected to sustain stereo 72 or 90 Hz. Reliable VR requires
the KGSL/Adreno/HWC compatibility path or a future DRM/MSM kernel port.

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
- [ ] Show a framebuffer diagnostic and a basic desktop on the panel.
- [ ] Build and start the patched KWin VR plugin on aarch64.
- [ ] Start Monado with a Monterey HMD stub and render a stereo test scene.
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
