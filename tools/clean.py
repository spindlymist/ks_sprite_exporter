# Deletes all build artifacts

import os
import shutil

def clean(path):
    clean_recursive(path)

    build_dir = os.path.join(path, "build")
    if os.path.isdir(build_dir):
        shutil.rmtree(build_dir)

def clean_recursive(dir_path):
    for name in os.listdir(dir_path):
        full_path = os.path.join(dir_path, name)

        if os.path.isdir(full_path):
            if name == "__pycache__":
                shutil.rmtree(full_path)
            else:
                clean_recursive(full_path)
            continue

        (prefix, ext) = os.path.splitext(full_path)
        ext = ext.lower()
        print(full_path, ext)

        if ext == ".pyc" \
            or ext == ".pyd" \
            or (ext == ".cpp" and os.path.isfile(prefix + ".pyx")):
            os.unlink(full_path)

if __name__ == "__main__":
    clean("mmfparser")
