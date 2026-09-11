# KS Sprite Exporter

This script dumps the sprites and associated data from the Multimedia Fusion 2 project file (.mfa) for Knytt Stories or Knytt Stories Plus.

It relies heavily on the MFA parser from the MMF decompiler Anaconda.

## Setup

1. First, install [Python 2.7](https://www.python.org/downloads/release/python-2718/). The following steps assume `python2` is aliased to the Python 2.7 interpreter (3.x will not work).
2. Install dependencies: `python2 -m pip install cython==3.0.12 pillow==6.2.2 natsort==6.2.1`
3. Compile the Cython modules: `python2 setup.py build`
4. Copy the build artifacts (e.g. `build/lib.win-amd64-2.7`) into the root directory. You can do this manually or use the helper: `python2 tools/copy_build.py`

## Usage
```
python2 main.py path/to/KnyttStories.mfa [frame]
```
Frame defaults to Gameplay.
