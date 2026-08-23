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
`e160863ad52c0e1c29c8bb7df3e47facdb02288d` adds the bounds-checked SyncBoss
HMD IMU parser, an orientation-only Monado device, and a guarded target builder.
The driver sends only the exact v50 zero-payload HMD IMU enable and disable
commands. It refuses device creation unless a valid type `0x50` packet arrives
within two seconds, and its host lifecycle test verifies the exact command
bytes. `postmarketos-ui-oculus-labwc` now selects this pinned fork instead of
Alpine's stock Monado.

This is deliberately an early hardware backend. Device timestamp units,
sensor axes, lens geometry, distortion, and display presentation still need
on-headset calibration. Until then the driver uses host monotonic arrival time
for 3DoF fusion, reports no positional tracking, uses a provisional 63.5 mm
IPD and 90 degree per-eye field of view, and applies no distortion mesh. These
values are bring-up scaffolding, not a claim of visually correct VR.

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

## Pattern login

The labwc session includes an optional 3x3 pattern lock built on gtklock's
`ext-session-lock-v1` support. Point at a dot, hold the primary controller
trigger, draw across at least four unique dots, and release to submit. Mouse
and touch input exercise the same path during bring-up. The normal masked PAM
password field remains available as a keyboard fallback.

Enable it from an authenticated recovery shell:

```sh
sudo oculus-pattern-setup enable
```

The prompt accepts the dot numbers `1` through `9`, read left-to-right and
top-to-bottom, twice without echoing them. Straight lines automatically include
a skipped middle dot, matching the on-screen gesture. The tool changes the Unix password of the
`user` account to that sequence and creates the enable marker only after
`chpasswd` succeeds. This means the pattern also becomes that account's Unix
password and has less entropy than a normal password; use SSH keys and do not
expose password SSH authentication to an untrusted network. Disable automatic
locking with `sudo oculus-pattern-setup disable`; disabling does not revert the
password.

The lock screen also exposes a two-press, five-second-confirmation bootloader
reboot button. Its command is restricted by the same passwordless sudo policy
as the desktop recovery menu. Pattern login remains off by default so a bad UI
build cannot lock the owner out before USB recovery has been tested.

KWin VR is not started automatically. Until the Monterey Monado driver works,
starting it can only exercise the nested compositor and failure diagnostics.

## Build the desktop packages

From a pmbootstrap checkout configured for `oculus-monterey`, build the custom
compositor first and the UI package second:

```sh
pmbootstrap build kwin-oculus-monterey
pmbootstrap build monado-oculus-monterey
pmbootstrap build postmarketos-ui-oculus-labwc
```

The UI package depends on labwc, `monado-oculus-monterey`, and
`kwin-oculus-monterey`, so
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
with Pixman rendering. On-device testing reached this path and showed an upright
desktop through the headset optics. Xorg 21.1 rejects Monterey's otherwise valid
virtual framebuffer because its sysfs node has no `device/subsystem` link, so
the OpenRC launcher supplies a temporary platform-device probe identity and
removes it immediately after Xorg has opened the framebuffer. The Xorg fbdev
rotation is 180 degrees because the panel scanout is inverted through the
headset optics.

This proves flat panel presentation, not VR. It is not expected to sustain
stereo 72 or 90 Hz. The same labwc session can later run on the KGSL/Adreno/HWC
compatibility host without changing its menu or KWin VR launcher. A future
DRM/MSM kernel port would remove both compatibility layers.

The first on-device Monado run found the Monterey builder, created an Oculus
Quest 1 HMD with two views, and assigned it to the head role. The image had the
Vulkan loader but no Linux Vulkan ICD, so the first compositor attempt failed
at `vkCreateInstance`. Installing Mesa's Lavapipe ICD provided a correctness
path: Monado created a 2880x1600 XCB target and KWin's standalone OpenXR test
created a session and submitted frames to the live headset. This is software
rendering and misses the 72/90 Hz frame budget; it is diagnostic proof, not the
final accelerated path.

The KWin VR scene then exposed Qt 6.11 compatibility issues in older grouped
QML bindings. Those bindings are fixed in the pinned fork. KWin's internal QPA
also lacked the Vulkan-instance hook required by Qt Quick 3D XR, and its
QPainter fallback selected Qt's non-RHI software scene graph globally. The
fork now provides a surface-free Vulkan instance plus an opt-in Vulkan Qt Quick
path for VR. Live testing reached `vrActive=true` with no XR scene failure;
visual stereo alignment and head-motion behavior still require wearer review.

The packaged launcher starts Monado with `XRT_NO_STDIN=1`, automatically
activates the KWin VR property over the session bus, and waits for KWin to exit
during stop/restart. It also adopts an already-running `monado-service` if its
own pidfile is missing, avoiding a duplicate service failure on the native
Monado IPC socket. This path was exercised live both from a clean Monado start
using the packaged Lavapipe ICD and through an immediate KWin stop/start cycle.

`/dev/kgsl-3d0` is present, but `/dev/dri` is absent because the stock 4.4
kernel has `CONFIG_DRM` disabled. The v50 `vulkan.msm8998.so` driver is an
Android/Bionic module and cannot be loaded directly by Alpine/Musl. Mesa
Turnip does not support the Quest 1's Adreno 540, so accelerated presentation
still requires either an Android-driver compatibility host or a newer DRM/MSM
kernel path.

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

Package revision r28 includes the strict command gateway and the runtime mount
it needs. The authoritative slot-A mount stays `ro,nosuid,nodev,noexec`.
`oculus-stock-runtime` bind-mounts only its `system/` directory at
`/run/oculus-stock-runtime/system`, then makes that temporary view
`ro,nosuid,nodev,exec`. This permits the owner's v50 linker and
`syncboss_input_tool` to run without remounting or writing Android. The gateway
accepts only status, list, scan, watch, pair, stream, battery, sleep, and
bounded-haptic operations.

The runtime service discovers both the extracted v50
`system/apex/com.android.runtime.release` layout and Android's logical
`apex/com.android.runtime` layout. The latter exists only after Android mounts
its APEX packages; it is not present in the raw v50 system partition.

Pairing currently selects a discovered hardware device ID; left/right mapping
comes from the controller type reported by SyncBoss. A future shell UI can
label those types after the Quest 1 and Quest 2 values are verified. It must
not guess a hand from connection order.

Package revision r21 added the first desktop-input bridge for already-paired
controllers. `oculus-controller-input` keeps one stock tool instance active,
extracts at most two controller IDs from the stock enumerator's strict indexed
format, and starts read-only stream observers. `oculus-controller-uinput`
accepts only the documented v50 `button`, `trig`, and `thumbstick` text records:
the thumbstick moves a relative pointer, fore-trigger or A/X presses the primary
button, grip or B/Y presses the secondary button, thumbstick-click presses the
middle button, and the system button sends Escape. Unknown, malformed, and
non-finite values produce no Linux input event.

This bridge is a bring-up path for labwc and pattern login, not controller pose
tracking. It does not expose pairing, haptics, calibration writes, or firmware
updates through the background service. Revision r28 fixes the stock runtime
path and enables its non-blocking OpenRC service. A live test enumerated one
paired left and one paired right Quest 1 controller while Monado continued to
own the HMD IMU stream. It also makes every stream worker explicitly own and
reap its stock-tool and uinput children, with a bounded TERM/KILL shutdown that
prevents duplicate readers and false OpenRC failures after a service restart.
Reconnect, input events, sleep/wake, and OpenXR pose still
require wearer validation. USB recovery is independent and remains
available if the stock controller runtime or mapping fails. Inspect it with:

```sh
sudo rc-service oculus-controller start
sudo oculus-controller list
libinput debug-events
sudo rc-service oculus-controller stop
```

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
- [x] Show the framebuffer/labwc diagnostic on the panel with correct optical
      orientation.
- [x] Start the patched KWin VR plugin on the headset against Monado; the live
  service reached `vrActive=true` through the Lavapipe correctness path.
- [x] Capture and parse the live SyncBoss HMD IMU stream in Monado.
- [x] Implement and host-test a guarded, orientation-only Monterey Monado
      backend.
- [ ] Confirm the Monterey backend's orientation axes visually on the headset.
- [ ] Render a stereo test scene on the headset (never substitute simulated
      pose for this gate).
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
