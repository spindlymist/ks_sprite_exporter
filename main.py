from __future__ import print_function
import json
import os
import shutil
import sys

from mmfparser.bytereader import ByteReader
from mmfparser.data.mfa import MFA, AnimationObject
from PIL import Image

ANIM_NAMES = [
    "Stopped",
    "Walking",
    "Running",
    "Appearing",
    "Disappearing",
    "Bouncing",
    "Launching",
    "Jumping",
    "Falling",
    "Climbing",
    "Crouch down",
    "Stand up"
]

def get_anim_name(animation, index):
    if index < len(ANIM_NAMES):
        return ANIM_NAMES[index]
    else:
        return animation.name

def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py path/to/KnyttStories.mfa [frame name]")
        return

    mfa_path = sys.argv[1]
    frame_name = sys.argv[2] if len(sys.argv) > 2 else "Gameplay"
    
    mfa = load_mfa(mfa_path)
    frame_handle = next((x for x in mfa.frames if x.name == frame_name), None)
    if not frame_handle:
        print("Frame {0} not found".format(frame_name))
        return

    if os.path.exists("output"):
        shutil.rmtree("output")
    os.mkdir("output")

    folder_lookup = {}
    for folder in frame_handle.folders:
        folder.name = mmf_str_to_unicode(folder.name)
        for item_handle in folder.items:
            folder_lookup[item_handle] = folder
    
    image_lookup = mfa.images.itemDict
    frame_lookup = {}
    with open("multiobjects.json", "r") as f:
        multiobjects_lookup = json.load(f)

    ignore_folders = ["Bars, credits", "Movement Engine", "System Engine", "Map Inv"]

    all_metadata = {}
    speeds = {}

    for item in frame_handle.items:
        folder = folder_lookup[item.handle]
        if folder.name in ignore_folders: continue
        if not isinstance(item.loader, AnimationObject): continue

        item.name = mmf_str_to_unicode(item.name)
        (bank, obj, item_name) = parse_item_name(item.name)
        if bank is None:
            print("Skipping " + item.name)
            continue
        
        animations = item.loader.items or []
        if len(animations) == 0: continue
        
        for (anim_index, animation) in enumerate(animations):
            has_frames = \
                len(animation.directions) > 0 \
                and any(len(dir.frames) > 0 for dir in animation.directions)
            if not has_frames: continue
            
            anim_name = get_anim_name(animation, anim_index)
            
            for direction in animation.directions:
                n_frames = len(direction.frames)
                if n_frames == 0: continue

                # First, iterate over all frames and find the largest offsets from the hotspot
                extents_left = []
                extents_right = []
                extents_top = []
                extents_bot = []

                for (frame_index, frame_handle) in enumerate(direction.frames):
                    image = image_lookup[frame_handle]
                    
                    if image.xHotspot < 0:
                        left = 0
                        right = image.width + abs(image.xHotspot)
                    elif image.xHotspot >= image.width:
                        left = -(image.width + (image.xHotspot - image.width))
                        right = 1
                    else:
                        left = -image.xHotspot
                        right = image.width - image.xHotspot

                    if image.yHotspot < 0:
                        top = 0
                        bot = image.height + abs(image.yHotspot)
                    elif image.yHotspot >= image.height:
                        top = -(image.height + (image.yHotspot - image.height))
                        bot = 1
                    else:
                        top = -image.yHotspot
                        bot = image.height - image.yHotspot
                    
                    extents_left.append(left)
                    extents_top.append(top)
                    extents_right.append(right)
                    extents_bot.append(bot)

                # Expand the frame size to account for the largest offsets
                extents_left_min = min(extents_left)
                extents_right_max = max(extents_right)
                extents_top_min = min(extents_top)
                extents_bot_max = max(extents_bot)
                frame_width = extents_right_max + abs(extents_left_min)
                frame_height = extents_bot_max + abs(extents_top_min)

                # Create the spritesheet
                total_width = n_frames * frame_width
                spritesheet = Image.new("RGBA", (total_width, frame_height), (0, 0, 0, 0))

                # Copy each frame into the spritesheet
                for (frame_index, frame_handle) in enumerate(direction.frames):
                    image = image_lookup[frame_handle]

                    if frame_handle not in frame_lookup:
                        byte_data = bytearray(image.getImageData());
                        pixel_data = []
                        for i in range(0, len(byte_data), 4):
                            pixel = (byte_data[i], byte_data[i + 1], byte_data[i + 2], byte_data[i + 3])
                            pixel_data.append(pixel)
                        frame = Image.new("RGBA", (image.width, image.height))
                        frame.putdata(pixel_data)
                        frame_lookup[frame_handle] = frame
                    else:
                        frame = frame_lookup[frame_handle]

                    left = extents_left[frame_index]
                    right = extents_right[frame_index]
                    top = extents_top[frame_index]
                    bot = extents_bot[frame_index]

                    width = right - left
                    height = bot - top
                    if width != frame.width or height != frame.height:
                        align_right = image.xHotspot < 0
                        align_bot = image.yHotspot < 0
                        frame = image_resize_canvas(frame, width, height, align_right, align_bot)

                    frame_origin_x = frame_index * frame_width
                    offset_x = left - extents_left_min
                    offset_y = top - extents_top_min
                    spritesheet.paste(frame, (frame_origin_x + offset_x, offset_y))

                output_name = get_output_name(bank, obj, item_name, anim_name, direction.index, multiobjects_lookup)
                if output_name is None:
                    continue

                spritesheet.save("output/" + output_name)

                if direction.minSpeed != direction.maxSpeed:
                    print("Speeds differ for", item_name, anim_name, direction.index)

                anim_meta = {
                    "minSpeed": direction.minSpeed,
                    "maxSpeed": direction.maxSpeed,
                    "repeat": direction.repeat,
                    "backTo": direction.backTo,
                }
                all_metadata[output_name] = anim_meta
                speeds[output_name] = direction.minSpeed

    with open("animation_meta.json", "w") as f:
        json.dump(all_metadata, f)
    with open("animation_speeds.json", "w") as f:
        json.dump(speeds, f)

def load_mfa(path):
    reader = ByteReader(open(path, 'rb'))
    mfa = MFA()
    mfa.initialize()
    mfa.read(reader)
    return mfa

def parse_item_name(item_name):
    if " " not in item_name: return (None, None, None)
    
    (bank_obj, name) = item_name.split(" ", 1)
    if ":" in bank_obj:
        (bank, obj) = bank_obj.split(":")
    elif "." in bank_obj:
        (bank,obj) = bank_obj.split(".")
    else:
        return (None, None, None)

    if "-" in obj:
        obj = obj.split("-")[0]

    return (bank, obj, name)

def get_output_name(bank, obj, item_name, anim_name, direction, multiobjects_lookup):
    omit_animation = False
    omit_direction = False
    variant = None
    
    if obj == "x":
        try:
            animations = multiobjects_lookup[item_name]
            if '*' in animations:
                directions = animations['*']
            else:
                directions = animations[anim_name]
                omit_animation = True
            omit_direction = True
            bank_obj = directions[str(direction)]
            bank = bank_obj["bank"]
            obj = bank_obj["object"]
            variant = bank_obj.get("variant", None)
        except:
            print('Lookup failed on name="{0}" anim="{1}" dir={2}'.format(item_name, anim_name, direction))
            return None

    if bank == "Child":
        output_name = "child_"
    else:
        output_name = "b{0}_o{1}_".format(bank, obj)
    output_name += convert_to_snake_case(item_name)
    if variant is not None:
        output_name += "_" + convert_to_snake_case(variant)
    if not omit_animation:
        output_name += "_" + convert_to_snake_case(anim_name)
    if not omit_direction:
        output_name += "_" + str(direction)
    
    return output_name + ".png"

def image_resize_canvas(image, new_width, new_height, align_right, align_bot):
    new_image = Image.new("RGBA", (new_width, new_height), (0, 0, 0, 0))
    if align_right:
        x = new_width - image.width
    else:
        x = 0
    if align_bot:
        y = new_height - image.height
    else:
        y = 0
    new_image.paste(image, (x, y))
    return new_image

def convert_to_snake_case(s):
    return "_".join(part.lower() for part in s.split(" "))

def mmf_str_to_unicode(s):
    return s.decode('cp1252')

if __name__ == "__main__":
    main()
