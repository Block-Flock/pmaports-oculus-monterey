from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
RULES = REPO / "device-oculus-monterey" / "90-oculus-monterey-access.rules"


def test_monterey_runtime_access_is_narrow():
    text = RULES.read_text()
    assert 'KERNEL=="kgsl-3d0", GROUP="video", MODE="0660"' in text
    assert 'KERNEL=="syncboss_stream0", GROUP="video", MODE="0660"' in text
    assert 'KERNEL=="syncboss0", GROUP="video", MODE="0660"' in text
    assert "syncboss_control0" not in text
    assert "syncboss_powerstate0" not in text
    assert 'MODE="0666"' not in text


def test_access_policy_is_packaged():
    apkbuild = (REPO / "device-oculus-monterey" / "APKBUILD").read_text()
    assert "90-oculus-monterey-access.rules" in apkbuild
    assert '"$pkgdir/usr/lib/udev/rules.d/90-oculus-monterey-access.rules"' in apkbuild
