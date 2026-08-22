#!/usr/bin/env python3
"""Regression tests for the proprietary-free stock-kernel transformer."""

from __future__ import annotations

import gzip
import importlib.machinery
import importlib.util
import struct
import unittest
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "prepare-monterey-stock-kernel-boot"


def load_builder():
    loader = importlib.machinery.SourceFileLoader("monterey_builder", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None:
        raise RuntimeError("could not create module spec")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


BUILDER = load_builder()


def pad4(data: bytes) -> bytes:
    return data + bytes((-len(data)) % 4)


def synthetic_lightman_dtb() -> tuple[bytes, dict[str, int]]:
    names = list(BUILDER.RATE_PROPERTIES)
    strings = bytearray()
    name_offsets: dict[str, int] = {}
    for name in names:
        name_offsets[name] = len(strings)
        strings.extend(name.encode("ascii") + b"\0")

    structure = bytearray()

    def begin_node(name: str) -> None:
        structure.extend(struct.pack(">I", BUILDER.FDT_BEGIN_NODE))
        structure.extend(pad4(name.encode("ascii") + b"\0"))

    begin_node("")
    begin_node("soc")
    begin_node("qcom,mdss_mdp@c900000")
    begin_node("qcom,mdss_dsi_sdc_lightman_video")

    values = {
        "qcom,mdss-dsi-min-refresh-rate": 60,
        "qcom,mdss-dsi-max-refresh-rate": 72,
        "qcom,mdss-dsi-panel-framerate": 72,
    }
    relative_value_offsets: dict[str, int] = {}
    for name, value in values.items():
        structure.extend(
            struct.pack(">III", BUILDER.FDT_PROP, 4, name_offsets[name])
        )
        relative_value_offsets[name] = len(structure)
        structure.extend(struct.pack(">I", value))

    structure.extend(struct.pack(">I", BUILDER.FDT_END_NODE) * 4)
    structure.extend(struct.pack(">I", BUILDER.FDT_END))

    reserve = bytes(16)
    structure_offset = 40 + len(reserve)
    strings_offset = structure_offset + len(structure)
    total_size = strings_offset + len(strings)
    header = struct.pack(
        ">10I",
        BUILDER.FDT_MAGIC,
        total_size,
        structure_offset,
        strings_offset,
        40,
        17,
        16,
        0,
        len(strings),
        len(structure),
    )
    absolute_offsets = {
        name: structure_offset + offset
        for name, offset in relative_value_offsets.items()
    }
    return header + reserve + structure + strings, absolute_offsets


class StockKernelTransformerTest(unittest.TestCase):
    def test_prioritizes_pmos_selectors_in_primary_cmdline(self) -> None:
        original = (
            b"androidboot.hardware=monterey long_platform_option=value "
            b"pmos_boot_uuid=boot-id pmos_root_uuid=root-id "
            b"pmos_rootfsopts=defaults"
        )

        result = BUILDER.prioritize_pmos_cmdline(original, True)

        self.assertTrue(result.startswith(b"oculus.force-debug pmos_boot_uuid="))
        self.assertLess(result.index(b"pmos_root_uuid="), result.index(b"androidboot."))
        self.assertEqual(sorted(result.split()), sorted(original.split() + [b"oculus.force-debug"]))

    def test_patches_only_token_and_selected_rate_cells(self) -> None:
        dtb, offsets = synthetic_lightman_dtb()
        image = b"prefix skip_initramfs suffix"
        stock_kernel = gzip.compress(image, mtime=0) + dtb + dtb

        result, count, minimum = BUILDER.patch_kernel(stock_kernel, 90)

        stream = zlib.decompressobj(16 + zlib.MAX_WBITS)
        patched_image = stream.decompress(result) + stream.flush()
        tail = stream.unused_data
        self.assertEqual(patched_image, b"prefix xkip_initramfs suffix")
        self.assertEqual(count, 2)
        self.assertEqual(minimum, 60)
        self.assertEqual(len(tail), 2 * len(dtb))

        expected = {
            "qcom,mdss-dsi-min-refresh-rate": 60,
            "qcom,mdss-dsi-max-refresh-rate": 90,
            "qcom,mdss-dsi-panel-framerate": 90,
        }
        for copy_offset in (0, len(dtb)):
            for name, value in expected.items():
                actual = struct.unpack_from(
                    ">I", tail, copy_offset + offsets[name]
                )[0]
                self.assertEqual(actual, value, name)

    def test_rejects_kernel_without_unique_skip_token(self) -> None:
        dtb, _ = synthetic_lightman_dtb()
        for image in (b"no setup token", b"skip_initramfs skip_initramfs"):
            with self.subTest(image=image):
                with self.assertRaises(BUILDER.ImageError):
                    BUILDER.patch_kernel(gzip.compress(image, mtime=0) + dtb, 90)

    def test_rejects_lightman_dtb_with_missing_property(self) -> None:
        dtb, _ = synthetic_lightman_dtb()
        broken = dtb.replace(
            b"qcom,mdss-dsi-panel-framerate\0",
            b"xcom,mdss-dsi-panel-framerate\0",
        )
        with self.assertRaises(BUILDER.ImageError):
            BUILDER.patch_lightman_dtb(broken, 90)

if __name__ == "__main__":
    unittest.main()
