# Copies build artifacts from the build directory to the mmfparser directory

from __future__ import print_function
import os
import shutil

def copy_build(from_dir, to_dir):
    if not os.path.isdir(from_dir):
        print("No build directory. Run python setup.py build first")
        return

    build_dir = None
    for name in os.listdir(from_dir):
        if not name.startswith("lib."):
            continue
        full_path = os.path.join(from_dir, name)
        if os.path.isdir(full_path):
            build_dir = full_path
            break

    if not build_dir:
        print("No build directory. Run python setup.py build first")
        return

    copy_dir(build_dir, to_dir)

def copy_dir(from_root, to_root, rel_path="."):
    from_dir = os.path.join(from_root, rel_path)
    to_dir = os.path.join(to_root, rel_path)

    if not os.path.exists(to_dir):
        os.makedirs(to_dir)

    for name in os.listdir(from_dir):
        full_path = os.path.join(from_dir, name)
        if os.path.isdir(full_path):
            copy_dir(from_root, to_root, os.path.join(rel_path, name))
        elif os.path.islink(full_path):
            link_to = os.readlink(full_path)
            os.symlink(link_to, os.path.join(to_dir, name))
        else:
            shutil.copy(full_path, os.path.join(to_dir, name))

if __name__ == "__main__":
    copy_build("build", ".")
