import os
import pathlib
import subprocess
import tempfile


ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "device-oculus-monterey" / "oculus-stock-runtime"


def test_refuses_source_without_read_only_noexec_mount():
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        source = root / "stock"
        (source / "system").mkdir(parents=True)
        mounts = root / "mounts"
        mounts.write_text(f"/dev/fake {source} ext4 ro,nodev,nosuid 0 0\n")
        result = subprocess.run(
            [str(SCRIPT), "start"],
            env=os.environ
            | {
                "OCULUS_SYSTEM_MOUNT": str(source),
                "OCULUS_STOCK_RUNTIME_ROOT": str(root / "runtime"),
                "OCULUS_MOUNTS_FILE": str(mounts),
            },
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode != 0
        assert "read-only and noexec" in result.stdout


def test_runtime_is_a_separate_read_only_exec_bind():
    text = SCRIPT.read_text()
    assert '"$mount_command" --bind "$system_mount/system" "$runtime_mount"' in text
    assert "remount,bind,ro,nosuid,nodev,exec" in text
    assert 'remount,exec "$system_mount"' not in text
