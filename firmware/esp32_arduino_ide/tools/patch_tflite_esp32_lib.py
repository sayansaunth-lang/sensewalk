"""Patch the Arduino library "TensorFlowLite_ESP32" 1.0.0 so it compiles with ESP32 core 3.x.

Needed by SENSEWALK_cam_person. The library's bundled flatbuffers has a `span` class whose
copy-assignment writes to `const` members and returns nothing; recent GCC (ESP32 core 3.x)
rejects it with "assignment of read-only member 'count_'". The fix is to drop the two `const`
qualifiers and return *this.

The library also ships LCD-screen and bus drivers (src/screen, src/bus) for Espressif's own dev
boards. They are not needed for inference and do not compile on core 3.x, so they are removed.
Safe to run more than once.

    python firmware/esp32_arduino_ide/tools/patch_tflite_esp32_lib.py [library_dir]

With no argument it looks in the usual Arduino library folders (and ~/Arduino/libraries on CI).
"""
from __future__ import annotations

import sys
import shutil
from pathlib import Path

REL = Path("src/third_party/flatbuffers/stl_emulation.h")


def candidates() -> list[Path]:
    home = Path.home()
    return [
        home / "Arduino" / "libraries" / "TensorFlowLite_ESP32",
        home / "Documents" / "Arduino" / "libraries" / "TensorFlowLite_ESP32",
        home / "OneDrive" / "Documents" / "Arduino" / "libraries" / "TensorFlowLite_ESP32",
    ]


def patch(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    text = text.replace("  pointer const data_;\n", "  pointer data_;\n")
    text = text.replace("  const size_type count_;\n", "  size_type count_;\n")
    old = "    data_ = other.data_;\n    count_ = other.count_;\n  }"
    if old in text:
        text = text.replace(old, "    data_ = other.data_;\n    count_ = other.count_;\n    return *this;\n  }")
    changed = False
    if text != original:
        path.write_text(text, encoding="utf-8")
        changed = True
    lib_src = path.parents[2]  # .../src
    for unused in ("screen", "bus"):
        d = lib_src / unused
        if d.exists():
            shutil.rmtree(d)
            changed = True
    return changed


def main() -> int:
    libs = [Path(sys.argv[1])] if len(sys.argv) > 1 else candidates()
    found = False
    for lib in libs:
        f = lib / REL
        if f.exists():
            found = True
            print(("patched " if patch(f) else "already patched ") + str(f))
    if not found:
        print("TensorFlowLite_ESP32 not found; install it from the Library Manager first")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
