S540 Tasti icon artwork
Copyright 2026 S540 project contributors. SPDX-License-Identifier: MIT.

Original vector artwork: a keyboard with a shortcut flash, shared by the
application icon and the monochrome menu-bar template. No trademark artwork.

Regenerate with Python 3, Pillow and Inkscape:
  python3 app/tools/build-icons.py

Runtime outputs live in app/Resources. AppIcon.icns contains standard and
Retina PNG icon representations. MenuBarIconTemplate.png is 20x18 pixels;
MenuBarIconTemplate@2x.png is 40x36 pixels. Load as an NSImage template at
20x18 points so macOS adapts its color to light/dark menu bars.

The app icon has transparent margins around an 896-pixel rounded tile in a
1024-pixel canvas, rather than filling or clipping the outer square.
