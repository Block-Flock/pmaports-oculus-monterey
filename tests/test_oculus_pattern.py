import ctypes
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
SOURCE = ROOT / "gtklock-oculus-pattern" / "oculus-pattern-core.c"
INCLUDE = ROOT / "gtklock-oculus-pattern"


class Pattern(ctypes.Structure):
    _fields_ = [
        ("path", ctypes.c_ubyte * 9),
        ("selected", ctypes.c_bool * 9),
        ("length", ctypes.c_size_t),
    ]


class OculusPatternTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tempdir = tempfile.TemporaryDirectory()
        library = pathlib.Path(cls.tempdir.name) / "liboculus-pattern.so"
        subprocess.run(
            [
                "cc",
                "-std=c11",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-shared",
                "-fPIC",
                f"-I{INCLUDE}",
                str(SOURCE),
                "-o",
                str(library),
            ],
            check=True,
        )
        cls.lib = ctypes.CDLL(str(library))
        cls.lib.oculus_pattern_add.argtypes = [ctypes.POINTER(Pattern), ctypes.c_uint]
        cls.lib.oculus_pattern_add.restype = ctypes.c_bool
        cls.lib.oculus_pattern_valid.argtypes = [ctypes.POINTER(Pattern)]
        cls.lib.oculus_pattern_valid.restype = ctypes.c_bool
        cls.lib.oculus_pattern_password.argtypes = [ctypes.POINTER(Pattern), ctypes.c_char_p]

    @classmethod
    def tearDownClass(cls):
        cls.tempdir.cleanup()

    def test_skipped_middle_dot_is_inserted(self):
        pattern = Pattern()
        self.assertTrue(self.lib.oculus_pattern_add(pattern, 0))
        self.assertTrue(self.lib.oculus_pattern_add(pattern, 2))
        self.assertEqual(list(pattern.path[: pattern.length]), [0, 1, 2])

    def test_duplicate_and_out_of_range_nodes_fail_closed(self):
        pattern = Pattern()
        self.assertTrue(self.lib.oculus_pattern_add(pattern, 4))
        self.assertFalse(self.lib.oculus_pattern_add(pattern, 4))
        self.assertFalse(self.lib.oculus_pattern_add(pattern, 9))
        self.assertEqual(pattern.length, 1)

    def test_four_dot_pattern_becomes_pam_password(self):
        pattern = Pattern()
        for node in (0, 1, 4, 8):
            self.assertTrue(self.lib.oculus_pattern_add(pattern, node))
        self.assertTrue(self.lib.oculus_pattern_valid(pattern))
        password = ctypes.create_string_buffer(10)
        self.lib.oculus_pattern_password(pattern, password)
        self.assertEqual(password.value, b"1259")


if __name__ == "__main__":
    unittest.main()
