from __future__ import print_function
import json
import os
import shutil
import sys

from mmfparser.bytereader import ByteReader
from mmfparser.data.mfa import MFA, Animation, AnimationObject, Frame, FrameItem, ItemFolder
from mmfparser.data.mfaloaders.imagebank import ImageItemTypeStub as ImageItem
from PIL import Image

class Context:
    def __init__(self, mfa, frame):
        # type: (MFA, Frame) -> None
        self.mfa = mfa # type: MFA
        self.frame = frame # type: Frame

        self.item_data = {} # type: dict[str, dict]
        self.anim_data = {} # type: dict[str, dict]

        for item in frame.items:
            item.name = mmf_str_to_unicode(item.name)

        self.folder_lookup = {} # type: dict[int, ItemFolder]
        for folder in frame.folders:
            folder.name = mmf_str_to_unicode(folder.name)
            for item_handle in folder.items:
                self.folder_lookup[item_handle] = folder

        self.image_info_lookup = mfa.images.itemDict # type: dict[int, ImageItem]
        self.image_lookup = {} # type: dict[int, Image.Image]
        with open("multiobjects.json", "r") as f:
            self.multiobjects_lookup = json.load(f) # type: dict[str, dict]

def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py path/to/KnyttStories.mfa [frame name]")
        return

    mfa_path = sys.argv[1]
    frame_name = sys.argv[2] if len(sys.argv) > 2 else "Gameplay"

    mfa = load_mfa(mfa_path)
    frame = next((x for x in mfa.frames if x.name == frame_name), None)
    if not frame:
        print("Frame {0} not found".format(frame_name))
        return

    ctx = Context(mfa, frame)

    if os.path.exists("output"):
        shutil.rmtree("output")
    os.mkdir("output")

    IGNORE_FOLDERS = ["Bars, credits", "Movement Engine", "System Engine", "Map Inv"]

    for item in frame.items:
        folder = ctx.folder_lookup[item.handle]
        if folder.name in IGNORE_FOLDERS: continue
        process_frame_item(ctx, item)

    with open("item_data.json", "w") as f:
        json.dump(ctx.item_data, f)
    with open("anim_data.json", "w") as f:
        json.dump(ctx.anim_data, f)

def process_frame_item(ctx, item):
    # type: (Context, FrameItem) -> None
    if not isinstance(item.loader, AnimationObject):
        print("Skipping " + item.name)
        return
    loader = item.loader # type: AnimationObject

    object_id = parse_item_name(item.name)
    if object_id is None:
        print("Skipping " + item.name)
        return

    item_data = {}

    n_values = len(loader.values.items)
    if n_values > 0:
        offsetX = loader.values.items[0]
        if offsetX.name not in ["X Offset", "OffsetX", "OrginX"]:
            print(item.name + " has alterable value A named " + offsetX.name)
        item_data["offsetX"] = offsetX.value
    if n_values > 1:
        offsetY = loader.values.items[1]
        if offsetY.name not in ["Y Offset", "OffsetY", "OrginY"]:
            print(item.name + " has alterable value B named " + offsetY.name)
        item_data["offsetY"] = offsetY.value

    ctx.item_data[item.name] = item_data

    animations = loader.items or []
    for (anim_index, animation) in enumerate(animations):
        process_animation(ctx, anim_index, animation, object_id)

def process_animation(
    ctx, # type: Context
    anim_index, # type: int
    animation, # type: Animation
    object_id # type: tuple[str, str, str]
):
    has_frames = \
        len(animation.directions) > 0 \
        and any(len(dir.frames) > 0 for dir in animation.directions)
    if not has_frames: return

    (bank, obj, object_name) = object_id
    anim_name = get_anim_name(animation, anim_index)

    for direction in animation.directions:
        n_frames = len(direction.frames)
        if n_frames == 0: continue

        # First, iterate over all frames and find the largest offsets from the hotspot
        extents = [] # type: list[tuple[int, int, int, int]]
        for (frame_index, frame_handle) in enumerate(direction.frames):
            image_info = ctx.image_info_lookup[frame_handle]
            frame_extents = calc_frame_extents(image_info)
            extents.append(frame_extents)

        # Expand the frame size to account for the largest offsets
        extents_top_min   = min(top   for (top, right, bot, left) in extents)
        extents_right_max = max(right for (top, right, bot, left) in extents)
        extents_bot_max   = max(bot   for (top, right, bot, left) in extents)
        extents_left_min  = min(left  for (top, right, bot, left) in extents)
        frame_width = extents_right_max + abs(extents_left_min)
        frame_height = extents_bot_max + abs(extents_top_min)

        # Create the spritesheet
        total_width = n_frames * frame_width
        spritesheet = Image.new("RGBA", (total_width, frame_height), (0, 0, 0, 0))

        # Copy each frame into the spritesheet
        for (frame_index, frame_handle) in enumerate(direction.frames):
            image_info = ctx.image_info_lookup[frame_handle]
            image = get_image(ctx, frame_handle)

            (top, right, bot, left) = extents[frame_index]

            width = right - left
            height = bot - top
            if width != image.width or height != image.height:
                align_right = image_info.xHotspot < 0
                align_bot = image_info.yHotspot < 0
                image = image_resize_canvas(image, width, height, align_right, align_bot)
            
            offset_x = left - extents_left_min
            offset_y = top - extents_top_min

            frame_origin_x = frame_index * frame_width
            spritesheet.paste(image, (frame_origin_x + offset_x, offset_y))

        output_name = get_output_name(bank, obj, object_name, anim_name, direction.index, ctx.multiobjects_lookup)
        if output_name is None:
            continue

        if direction.minSpeed != direction.maxSpeed:
            print("Speeds differ for", object_name, anim_name, direction.index)

        anim_data = {
            "speed": direction.minSpeed,
            "repeat": direction.repeat,
            "backTo": direction.backTo,
        }
        ctx.anim_data[output_name] = anim_data

        spritesheet.save("output/" + output_name)

def calc_frame_extents(image_info):
    # type: (ImageItem) -> tuple[int, int, int, int]
    if image_info.xHotspot < 0:
        left = 0
        right = image_info.width + abs(image_info.xHotspot)
    elif image_info.xHotspot >= image_info.width:
        left = -(image_info.width + (image_info.xHotspot - image_info.width))
        right = 1
    else:
        left = -image_info.xHotspot
        right = image_info.width - image_info.xHotspot
    if image_info.yHotspot < 0:
        top = 0
        bot = image_info.height + abs(image_info.yHotspot)
    elif image_info.yHotspot >= image_info.height:
        top = -(image_info.height + (image_info.yHotspot - image_info.height))
        bot = 1
    else:
        top = -image_info.yHotspot
        bot = image_info.height - image_info.yHotspot

    return (top, right, bot, left)

def get_image(ctx, handle):
    # type: (Context, int) -> Image.Image
    image_info = ctx.image_info_lookup[handle]
    if handle not in ctx.image_lookup:
        byte_data = bytearray(image_info.getImageData());
        pixel_data = []
        for i in range(0, len(byte_data), 4):
            pixel = (byte_data[i], byte_data[i + 1], byte_data[i + 2], byte_data[i + 3])
            pixel_data.append(pixel)
        image = Image.new("RGBA", (image_info.width, image_info.height))
        image.putdata(pixel_data)
        ctx.image_lookup[handle] = image
    return ctx.image_lookup[handle]

def load_mfa(path):
    # type: (str) -> MFA
    reader = ByteReader(open(path, 'rb'))
    mfa = MFA()
    mfa.initialize()
    mfa.read(reader)
    return mfa

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
    # type: (Animation, int) -> str
    if index < len(ANIM_NAMES):
        return ANIM_NAMES[index]
    else:
        return animation.name

def parse_item_name(item_name):
    # type: (str) -> tuple[str, str, str]|None
    if " " not in item_name: return None

    (bank_obj, name) = item_name.split(" ", 1)
    if ":" in bank_obj:
        (bank, obj) = bank_obj.split(":")
    elif "." in bank_obj:
        (bank, obj) = bank_obj.split(".")
    else:
        return None

    if "-" in obj:
        obj = obj.split("-")[0]

    return (bank, obj, name)

def get_output_name(
    bank, # type: str
    obj, # type: str
    item_name, # type: str
    anim_name, # type: str
    direction, # type: int
    multiobjects_lookup # type: dict[str, dict]
):
    # type: (...) -> str|None
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

def image_resize_canvas(
    image, # type: Image.Image
    new_width, # type: int
    new_height, # type: int
    align_right, # type: bool
    align_bot # type: bool
):
    # type: (...) -> Image.Image
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
    # type: (str) -> str
    return "_".join(part.lower() for part in s.split(" "))

def mmf_str_to_unicode(s):
    # type: (str) -> str
    return s.decode('cp1252')

if __name__ == "__main__":
    main()
