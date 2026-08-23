# Desktop test image r24

r24 packages the fixes discovered during the first successful r23 display
trial. It is a build-tested follow-up, not yet a flashed or cold-boot-validated
image.

## Changes from r23

- Starts the labwc/Xorg framebuffer path directly from OpenRC instead of using
  `tinydm`; Monterey's stock kernel does not expose a usable virtual terminal.
- Temporarily supplies the sysfs `device/subsystem` identity required by the
  Xorg fbdev probe, then removes the bind mount after Xorg opens `/dev/fb0`.
- Rotates the fbdev output by 180 degrees so it appears upright through the
  headset optics.
- Applies narrow `root:video` access to KGSL, ION, and SyncBoss character
  devices from an early `mdev`-compatible service. The udev rule remains for
  systems that actually run udev.
- Removes the obsolete `tinydm` runtime dependency and its default-runlevel
  service while preserving the USB recovery path.

The exact launcher was exercised live on r23 and produced the correctly
oriented labwc desktop. Both `device-oculus-monterey` 1-r24 and
`postmarketos-ui-oculus-labwc` 1-r4 build successfully with pmbootstrap. A
matched boot/system pair still needs to be generated and tested before hashes
are published here.

## VR boundary found during the same trial

Monado successfully selected the Monterey builder, opened the live HMD sensor
stream, created a two-view Quest 1 HMD, and assigned it to the head role. Mesa
Lavapipe then supplied a software Vulkan correctness path: Monado created its
2880x1600 XCB target and KWin's standalone OpenXR test submitted live frames.
The software compositor misses the headset frame budget and is not an
accelerated 72/90 Hz solution.

The full KWin scene uncovered Qt 6.11 grouped-binding incompatibilities, a
missing Vulkan-instance hook in KWin's internal QPA, and a global software
scene-graph selection that prevented Qt Quick XR from creating its RHI. All
three are patched in the pinned fork. The live service now reaches
`vrActive=true` without an XR scene failure; visual stereo alignment and
head-motion behavior still require wearer review. The flat, upright labwc
desktop remains the recovery fallback throughout.

The v50 kernel still has `CONFIG_DRM` disabled, so it exposes KGSL but no DRM
render node. The stock Qualcomm Vulkan module is Android/Bionic and not
directly loadable by Alpine/Musl, while Mesa Turnip does not support Adreno
540. Accelerated VR therefore remains a separate compatibility/kernel task.
