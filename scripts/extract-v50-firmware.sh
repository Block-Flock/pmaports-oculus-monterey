#!/bin/sh
# Extract Linux-relevant firmware from a rooted Quest 1 over ADB.

set -eu

output=${1:-firmware-v50-local}
mkdir -p "$output"

adb_wait='adb wait-for-device'
$adb_wait

pull() {
        source=$1
        target="$output/$2"
        mkdir -p "$target"
        adb pull "$source" "$target" >/dev/null
}

pull /vendor/firmware vendor-firmware
pull /vendor/firmware_mnt/image firmware-image
pull /vendor/firmware/wlan/qca_cld vendor-firmware/wlan/qca_cld
pull /vendor/etc vendor-etc

find "$output" -type f -exec sha256sum {} + | sort > "$output/MANIFEST.sha256"
printf 'Extracted V50 firmware to %s\n' "$output"
printf 'Do not commit this directory: the firmware is proprietary.\n'
