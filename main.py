from __future__ import print_function
from collections import OrderedDict
import io
import json
import os
import shutil
import sys

from natsort import natsorted
from PIL import Image

from mmfparser.bytereader import ByteReader
from mmfparser.data.mfa import MFA, Active, Animation, AnimationObject, Frame, FrameItem, ItemFolder
from mmfparser.data.mfaloaders.imagebank import ImageItemTypeStub as ImageItem

class Context:
    def __init__(self, mfa, frame):
        # type: (MFA, Frame) -> None
        self.mfa = mfa # type: MFA
        self.frame = frame # type: Frame

        self.object_data = {} # type: dict[str, ObjectData]
        self.anim_data = {} # type: dict[str, AnimData]

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

    for item in frame.items:
        process_frame_item(ctx, item)

    sort_and_jsonify = lambda d: dict_sort_and_map(d, lambda d: d.to_json())
    with io.open("object_data.json", "w", encoding="utf8") as f:
        object_data_sorted = dict_sort_and_map(ctx.object_data, sort_and_jsonify)
        json_out = json.dumps(object_data_sorted, ensure_ascii=False)
        f.write(json_out)

    with io.open("anim_data.json", "w", encoding="utf8") as f:
        anim_data_sorted = sort_and_jsonify(ctx.anim_data)
        json_out = json.dumps(anim_data_sorted, ensure_ascii=False)
        f.write(json_out)

IGNORE_ITEMS = [
    ("7: Effects", "Nature"),
    ("Bars, credits", "Object Bar"),
    ("Movement Engine", "KBD"),
    ("Movement Engine", "Physics"),
    ("System Engine", "Extras"),
    ("System Engine", "Flag Storage"),
    ("System Engine", "Frame Reset Countdown"),
    ("System Engine", "Render Quick Value Storage"),
    ("System Engine", "Screen Values"),
    ("System Engine", "Sound Values (Global)"),
]

def process_frame_item(ctx, item):
    # type: (Context, FrameItem) -> None
    folder = ctx.folder_lookup[item.handle]
    if (folder.name, item.name) in IGNORE_ITEMS:
        print("{0}/{1} is ignored".format(folder.name, item.name))
        return
    
    if not isinstance(item.loader, Active):
        print("{0}/{1} has loader type {2}".format(folder.name, item.name, item.loader.__class__.__name__))
        return
    loader = item.loader # type: AnimationObject

    object_id = parse_item_name(item.name)
    if object_id is None:
        object_id = (folder.name, item.name, item.name)

    object_data = ObjectData()
    n_values = len(loader.values.items)

    offset_x = 0
    offset_y = 0
    if n_values > 0:
        alterable_value = loader.values.items[0]
        if alterable_value.name not in ["X Offset", "OffsetX", "OrginX"]:
            print(item.name + " has alterable value A named " + alterable_value.name)
        offset_x = alterable_value.value
    if n_values > 1:
        alterable_value = loader.values.items[1]
        if alterable_value.name not in ["Y Offset", "OffsetY", "OrginY"]:
            print(item.name + " has alterable value B named " + alterable_value.name)
        offset_y = alterable_value.value
    object_data.offset = (offset_x, offset_y)

    if n_values > 2:
        alterable_value = loader.values.items[2]
        if alterable_value.name == "DoesHurt":
            object_data.does_hurt = alterable_value.value

    object_data.ink_effect = item.inkEffect
    object_data.ink_effect_param = item.inkEffectParameter

    matching_objects = get_matching_objects(object_id, ctx.multiobjects_lookup)
    for (bank, obj) in matching_objects:
        if bank not in ctx.object_data:
            ctx.object_data[bank] = {}
        ctx.object_data[bank][obj] = object_data

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
        extents_top_min   = min(top   for (top, right, bot, left) in extents)
        extents_right_max = max(right for (top, right, bot, left) in extents)
        extents_bot_max   = max(bot   for (top, right, bot, left) in extents)
        extents_left_min  = min(left  for (top, right, bot, left) in extents)

        # Calculate the hotspot position and frame size that accommodates all frames
        hotspot_x = abs(extents_left_min)
        hotspot_y = abs(extents_top_min)
        frame_width = hotspot_x + extents_right_max
        frame_height = hotspot_y + extents_bot_max

        # Create the spritesheet
        total_width = n_frames * frame_width
        spritesheet = Image.new("RGBA", (total_width, frame_height), (0, 0, 0, 0))

        action_points = []

        # Copy each frame into the spritesheet
        # Also calculate and record the action point for each frame
        for (frame_index, frame_handle) in enumerate(direction.frames):
            image_info = ctx.image_info_lookup[frame_handle]
            image = get_image(ctx, frame_handle)
            
            frame_origin_x = frame_index * frame_width
            top_left_x = hotspot_x - image_info.xHotspot
            top_left_y = hotspot_y - image_info.yHotspot
            
            action_x = top_left_x + image_info.actionX
            action_y = top_left_y + image_info.actionY
            action_points.append((action_x, action_y))

            spritesheet.paste(image, (frame_origin_x + top_left_x, top_left_y))

        output_name = get_output_name(bank, obj, object_name, anim_name, direction.index, ctx.multiobjects_lookup)
        if output_name is None:
            continue

        anim_data = AnimData()
        anim_data.frame_count = n_frames
        anim_data.frame_size = (frame_width, frame_height)
        anim_data.min_speed = direction.minSpeed
        anim_data.max_speed = direction.maxSpeed
        anim_data.repeat = direction.repeat
        anim_data.back_to = direction.backTo
        anim_data.hotspot = (hotspot_x, hotspot_y)
        anim_data.action_points = action_points
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

    return (bank, obj, name)

def get_matching_objects(object_id, multiobjects_lookup):
    # type: (tuple[str, str, str], dict[str, dict]) -> list[tuple[str, str]]
    (bank, obj, item_name) = object_id
    animations = multiobjects_lookup.get(item_name)

    # Special case
    if item_name == "Liquid Lights":
        return []

    if animations is None:
        obj = obj if len(obj) > 0 else item_name
        return [(bank, obj)]

    matching_objects = set()
    for animation in animations.values():
        for direction in animation.values():
            bank = str(direction["bank"])
            obj = str(direction["object"])
            matching_objects.add((bank, obj))

    return list(matching_objects)

ENGINE_FOLDERS = [
    "Bars, credits",
    "Map Inv",
    "Movement Engine",
    "System Engine",
]

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

    try:
        animations = multiobjects_lookup[item_name]
        if '*' in animations:
            directions = animations['*']
        else:
            directions = animations[anim_name]
            omit_animation = True
        if '*' in directions:
            bank_obj = directions['*']
        else:
            bank_obj = directions[str(direction)]
            omit_direction = True
        bank = bank_obj["bank"]
        obj = bank_obj["object"]
        variant = bank_obj.get("variant", None)
        item_name = bank_obj.get("rename", item_name)
    except:
        if obj == "x" or "-" in obj:
            print('Lookup failed on name="{0}" anim="{1}" dir={2}'.format(item_name, anim_name, direction))
            return None

    if bank in ENGINE_FOLDERS:
        output_name = ""
    elif is_intlike(bank):
        output_name = "b{0}_o{1}_".format(bank, obj)
    else:
        output_name = "{0}_".format(convert_to_snake_case(bank))
    output_name += convert_to_snake_case(item_name)
    if variant is not None:
        output_name += "_" + convert_to_snake_case(variant)
    if not omit_animation:
        output_name += "_" + convert_to_snake_case(anim_name)
    if not omit_direction:
        output_name += "_" + str(direction)

    return output_name + ".png"

def is_intlike(x):
    # type: (any) -> bool
    try:
        _ = int(x)
        return True
    except:
        return False

def convert_to_snake_case(s):
    # type: (str) -> str
    return "_".join(part.lower() for part in super_split(s))

def super_split(s):
    # type: (str) -> list[str]
    '''Splits on spaces, numbers, and capital letters.'''

    start = 0
    parts = []
    in_digit_sequence = False

    for (i, char) in enumerate(s):
        is_new_part = False
        is_digit = char.isdigit()

        if in_digit_sequence:
            if not is_digit:
                is_new_part = True
                in_digit_sequence = False
        elif char == " ":
            is_new_part = True
        elif char.isupper():
            is_new_part = True
        elif is_digit:
            is_new_part = True
            in_digit_sequence = True

        if is_new_part:
            new_part = s[start:i]
            if len(new_part) > 0:
                parts.append(new_part)
            if char == " ":
                start = i + 1
            else:
                start = i

    last_part = s[start:]
    if len(last_part) > 0:
        parts.append(last_part)

    return parts

def mmf_str_to_unicode(s):
    # type: (str) -> str
    return s.decode('cp1252')

def dict_sort_and_map(d, map = lambda x: x):
    # type (dict) -> OrderedDict
    return OrderedDict(
        (key, map(d[key])) for key in natsorted(d.keys())
    )

def clamp(x, lower, upper):
    return min(max(x, lower), upper)

def trans_to_alpha(t):
    return clamp((128 - t) * 2, 0, 255)

INK_EFFECT_NAMES = {
    0: "none",
    1: "semi-transparent",
    2: "inverted",
    3: "xor",
    4: "and",
    5: "or",
    9: "add",
    10: "monochrome",
    11: "subtract",
}

class ObjectData:
    def __init__(self):
        self.offset = (0, 0) # type: tuple[int, int]
        self.does_hurt = None # type: int|None
        self.ink_effect = 0 # type: int
        self.ink_effect_param = 0 # type: int

    def to_json(self):
        d = OrderedDict()
        d["offset"] = self.offset
        if self.does_hurt is not None:
            d["doesHurt"] = self.does_hurt

        if self.ink_effect > 0:
            ink_effect = INK_EFFECT_NAMES.get(self.ink_effect)
            if ink_effect is None:
                print("Unknown ink effect:", ink_effect)
            elif ink_effect == "semi-transparent":
                d["alpha"] = trans_to_alpha(self.ink_effect_param)
            else:
                d["blendMode"] = ink_effect

        return d

class AnimData:
    def __init__(self):
        self.frame_count = 0 # type: int
        self.frame_size = (0, 0) # type: tuple[int, int]
        self.repeat = 0 # type: int
        self.back_to = 0 # type: int
        self.hotspot = (0, 0) # type: tuple[int, int]
        self.action_points = [] # type: list[tuple[int, int]]
        self.min_speed = 0 # type: int
        self.max_speed = 0 # type: int

    def to_json(self):
        d = OrderedDict()
        d["frameCount"] = self.frame_count
        d["frameSize"] = self.frame_size
        if self.min_speed == self.max_speed:
            d["speed"] = self.min_speed
        else:
            d["minSpeed"] = self.min_speed
            d["maxSpeed"] = self.max_speed
        d["repeat"] = self.repeat
        d["backTo"] = self.back_to
        d["hotspot"] = self.hotspot

        if len(set(self.action_points)) == 1:
            d["actionPoint"] = self.action_points[0]
        else:
            d["actionPoints"] = self.action_points

        return d

if __name__ == "__main__":
    main()
