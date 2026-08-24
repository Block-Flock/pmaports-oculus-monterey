import os
import pathlib
import subprocess
import tempfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "device-oculus-monterey" / "oculus-stock-runtime"


def make_environment(root: pathlib.Path, mounts_options: str) -> tuple[dict, pathlib.Path]:
    """Stage a stock system tree pre-mounted at the expected mount point."""
    source = root / "stock"
    (source / "system").mkdir(parents=True)

    sys_block = root / "sys-block"
    device_dir = sys_block / "fake-device"
    device_dir.mkdir(parents=True)
    (device_dir / "uevent").write_text(
        "MAJOR=254\nMINOR=1\nDEVNAME=fake\nPARTNAME=system_a\n"
    )

    mounts = root / "mounts"
    mounts.write_text(f"/dev/fake {source} ext4 {mounts_options} 0 0\n")

    cmdline = root / "cmdline"
    cmdline.write_text("androidboot.slot_suffix=_b\n")

    environment = os.environ | {
        "OCULUS_SYSTEM_MOUNT": str(source),
        "OCULUS_STOCK_RUNTIME_ROOT": str(root / "runtime"),
        "OCULUS_MOUNTS_FILE": str(mounts),
        "OCULUS_CMDLINE_FILE": str(root / "cmdline"),
        "OCULUS_SYS_CLASS_BLOCK": str(sys_block),
        "OCULUS_SYSTEM_DEVICE": "/dev/fake",
    }
    return environment, source


def test_refuses_source_without_read_only_noexec_mount():
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        environment, _ = make_environment(root, "ro,nodev,nosuid")
        result = subprocess.run(
            [str(SCRIPT), "start"],
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode != 0
        assert "ro, nosuid, nodev, noexec" in result.stdout


def test_runtime_is_a_separate_read_only_exec_bind():
    text = SCRIPT.read_text()
    assert '"$mount_command" --bind "$system_mount/system" "$runtime_mount"' in text
    assert "remount,bind,ro,nosuid,nodev,exec" in text
    assert 'remount,exec "$system_mount"' not in text


def test_slot_suffix_is_detected_not_assumed():
    text = SCRIPT.read_text()
    assert "androidboot.slot_suffix" in text
    # No hardcoded system_a/system_b partition lookups anywhere.
    assert "PARTNAME=system_" not in text.replace("system$suffix", "")
    assert "find_system_partition \"$suffix\"" in text


def test_opposite_slot_is_chosen_for_android_tree():
    text = SCRIPT.read_text()
    assert "_a) printf '%s\\n' _b" in text
    assert "_b) printf '%s\\n' _a" in text


def test_mounts_source_partition_read_only_before_bind():
    text = SCRIPT.read_text()
    assert "-o ro,noload,nosuid,nodev,noexec" in text


def test_stop_leaves_submounts_in_place_and_unmounts_clean_tree():
    text = SCRIPT.read_text()
    assert 'index($2, root "/") == 1' in text
    assert "leaving $system_mount mounted; submounts still present" in text
