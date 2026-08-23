import os
import shutil
import sys
from PIL import Image

OUTPUT_FRAMES = False

def split_spritesheet(sheet, frame_width, frame_height):
    frames = []
    n_cols = sheet.width // frame_width
    n_rows = sheet.height // frame_height

    for row in range(n_rows):
        y = row * frame_height
        for col in range(n_cols):
            x = col * frame_width
            frame = sheet.crop((x, y, x + frame_width, y + frame_height))
            frames.append(frame)

    return frames

if len(sys.argv) < 5:
    print("Usage: python compare.py <image1> <image2> <frame width> <frame height>")

sheet1 = Image.open(sys.argv[1])
sheet2 = Image.open(sys.argv[2])
frame_width = int(sys.argv[3])
frame_height = int(sys.argv[4])

frames1 = split_spritesheet(sheet1, frame_width, frame_height)
frames2 = split_spritesheet(sheet2, frame_width, frame_height)

if OUTPUT_FRAMES:
    if os.path.exists("./image1_frames"):
        shutil.rmtree("./image1_frames")
    if os.path.exists("./image2_frames"):
        shutil.rmtree("./image2_frames")
    os.mkdir("./image1_frames")
    os.mkdir("./image2_frames")
    for (i, frame) in enumerate(frames1):
        frame.save("image1_frames/{0}.png".format(i))
    for (i, frame) in enumerate(frames2):
        frame.save("image2_frames/{0}.png".format(i))

n_frames_common = min(len(frames1), len(frames2))
for i in range(n_frames_common):
    frame1 = frames1[i]
    frame2 = frames2[i]
    frames_differ = False
    for y in range(frame_height):
        if frames_differ: break
        for x in range(frame_width):
            pixel1 = frame1.getpixel((x, y))
            pixel2 = frame2.getpixel((x, y))
            if pixel1[3] == 0 and pixel2[3] == 0: continue
            if pixel1 != pixel2:
                frames_differ = True
                break
    if frames_differ:
        print("Frame {0} differs".format(i))

print("Image1 has {0} frames.".format(len(frames1)))
print("Image2 has {0} frames.".format(len(frames2)))

has_extra_frames = len(frames1) != len(frames2)
if len(frames1) > len(frames2):
    more_frames = frames1
    less_frames = frames2
else:
    more_frames = frames2
    less_frames = frames1

extra_frames_have_content = False
for frame in more_frames[len(less_frames):]:
    if extra_frames_have_content: break
    for y in range(frame.height):
        if extra_frames_have_content: break
        for x in range(frame.width):
            if frame.getpixel((x, y))[3] != 0:
                extra_frames_have_content = True
                break

if extra_frames_have_content:
    print("The extra frames are NOT empty.")
elif has_extra_frames:
    print("The extra frames are empty.")
