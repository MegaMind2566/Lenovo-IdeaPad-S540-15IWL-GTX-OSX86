#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Render the original SVG artwork and encode a standard PNG-based ICNS."""
from __future__ import annotations

import io
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

from PIL import Image


def png_bytes(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=False, compress_level=9)
    return output.getvalue()


def main() -> None:
    app = Path(__file__).resolve().parents[1]
    design, resources = app / "design", app / "Resources"
    resources.mkdir(exist_ok=True)
    inkscape = shutil.which("inkscape")
    if not inkscape:
        raise SystemExit("Inkscape is required to render the SVG sources.")

    with tempfile.TemporaryDirectory(prefix="s540-icons-") as temporary:
        def render(source: str, size: tuple[int, int]) -> Image.Image:
            output = Path(temporary) / f"{Path(source).stem}-{size[0]}x{size[1]}.png"
            subprocess.run([inkscape, str(design / source), "--export-type=png",
                            "--export-filename=" + str(output),
                            "--export-width=" + str(size[0]),
                            "--export-height=" + str(size[1])],
                           check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            with Image.open(output) as image:
                return image.convert("RGBA")

        # Render every icon at its native resolution. This preserves strokes
        # and avoids resizing a raster master for low-resolution representations.
        sizes = (16, 32, 64, 128, 256, 512, 1024)
        representations = {size: png_bytes(render("AppIcon.svg", (size, size))) for size in sizes}
        (design / "AppIcon-preview.png").write_bytes(representations[1024])
        types = ((b"icp4", 16), (b"icp5", 32), (b"icp6", 64), (b"ic07", 128),
                 (b"ic08", 256), (b"ic09", 512), (b"ic10", 1024),
                 (b"ic11", 32), (b"ic12", 64), (b"ic13", 256), (b"ic14", 512))
        chunks = b"".join(kind + struct.pack(">I", len(representations[size]) + 8) + representations[size]
                          for kind, size in types)
        (resources / "AppIcon.icns").write_bytes(b"icns" + struct.pack(">I", len(chunks) + 8) + chunks)
        for scale, suffix in ((1, ""), (2, "@2x")):
            data = png_bytes(render("MenuBarIconTemplate.svg", (20 * scale, 18 * scale)))
            (resources / f"MenuBarIconTemplate{suffix}.png").write_bytes(data)

    print("Generated AppIcon.icns, source preview, and menu-bar templates (1x/2x).")


if __name__ == "__main__":
    main()
