"""
What a map pack shared by a player may hold, and the checks that make sure it does.

Players publish their packs from the map editor (/minigolf/editor), everybody can browse, test and play
them. The holes are plain data, drawn and played by every browser that opens the pack, and run 240
physics steps a second against every wall. So whatever comes in is rebuilt from what the game knows
(unknown keys are dropped), and kept within limits that keep it playable on a LAN party laptop and the
database small:

- a pack has 1 to MAX_HOLES holes and takes MAX_BYTES as JSON at most
- every list of things on a hole has a limit (LIST_LIMITS), all walls together have at most MAX_WALL_CORNERS
  corners, as every corner is a wall the balls are checked against on every physics step
- the tees and the cup are on the canvas and on the fairway (inside the outline, not in a block or in water),
  everything else close to the canvas, and every number is finite and in a range that makes sense

Whether a hole can be holed at all isn't checked here, the editor makes its author hole every hole in a test
run before it publishes the pack. Like rounds, that's taken on trust.

No Flask in here: lol9k1/minigolf.py stores packs and serves them, tests/test_minigolf_pack_limits.py checks this.
"""
import json
import math
from typing import Callable

MAX_HOLES = 18
MAX_BYTES = 64 * 1024  # of a pack's holes as JSON
MAX_NAME = 40          # of a pack and of a hole
MAX_HINT = 200
MAX_TEES = 8           # the game has a colour for 8 players
MAX_CORNERS = 32       # of a polygon
MAX_WALL_CORNERS = 200  # of the outline and all the blocks of a hole together
LIST_LIMITS = {'blocks': 40, 'sand': 30, 'water': 30, 'boosts': 30, 'bumpers': 30, 'sliders': 12, 'rotors': 4}
# what the map editor calls the things in those lists, one and more of them, for the messages to its players
ITEM_NAMES = {'blocks': ('block', 'blocks'), 'sand': ('sand area', 'sand areas'), 'water': ('water', 'water areas'),
              'boosts': ('boost', 'boosts'), 'bumpers': ('bumper', 'bumpers'), 'sliders': ('slider', 'sliders'),
              'rotors': ('windmill', 'windmills')}
MAX_SPEED = 10         # of windmills and sliders, in radians per second
MAX_BLADES = 8
MAX_BUMPER = 80        # radius


class PackError(ValueError):
    """Why a pack can't be shared, in words for its author."""


def clean_text(value, what: str, longest: int, required: bool = True) -> str:
    """A name or a hint on one line, whitespace collapsed."""
    if value is None and not required:
        return ''
    if not isinstance(value, str):
        raise PackError(f'{what} must be text')
    text = ' '.join(value.split())
    if required and not text:
        raise PackError(f'{what} is missing')
    if len(text) > longest:
        raise PackError(f'{what} is longer than {longest} characters')
    return text


def validate_holes(holes, width: int, height: int, max_strokes: int) -> list[dict]:
    """The holes of a pack as the game takes them, rebuilt from what came in. Raises PackError."""
    if not isinstance(holes, list) or not 1 <= len(holes) <= MAX_HOLES:
        raise PackError(f'a pack has 1 to {MAX_HOLES} holes')
    clean = [_Hole(width, height, max_strokes, i + 1).clean(h) for i, h in enumerate(holes)]
    # in UTF-8 bytes, as the editor measures it (with ensure_ascii every non-ASCII character would count 6 or 12)
    if len(json.dumps(clean, separators=(',', ':'), ensure_ascii=False).encode()) > MAX_BYTES:
        raise PackError(f'the pack is too big, it may take {MAX_BYTES // 1024} KB at most')
    return clean


def is_number(value) -> bool:
    """A finite int or float, not a bool. Ints are always finite: math.isfinite would overflow on huge ones."""
    return type(value) is int or (type(value) is float and math.isfinite(value))


def inside_polygon(x: float, y: float, poly: list) -> bool:
    """Like insidePolygon in static/js/minigolf_editor.js."""
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        (xi, yi), (xj, yj) = poly[i], poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _in_rect(x: float, y: float, r: list) -> bool:
    return r[0] <= x <= r[0] + r[2] and r[1] <= y <= r[1] + r[3]


class _Hole:
    """Checks one hole and rebuilds it, every error names the hole and what's wrong with it."""

    def __init__(self, width: int, height: int, max_strokes: int, number: int):
        self.w, self.h, self.max_strokes, self.number = width, height, max_strokes, number

    def fail(self, message: str):
        raise PackError(f'hole {self.number}: {message}')

    def number_in(self, value, what: str, low: float, high: float) -> float:
        if not is_number(value) or not low <= value <= high:
            self.fail(f'{what} must be a number from {low:g} to {high:g}')
        return value

    # Things may stick out of the canvas a bit (the editor only warns about it), but not by miles.
    def x(self, value, what: str) -> float:
        return self.number_in(value, what, -self.w, 2 * self.w)

    def y(self, value, what: str) -> float:
        return self.number_in(value, what, -self.h, 2 * self.h)

    def point(self, value, what: str, on_canvas: bool = False) -> list:
        if not isinstance(value, list) or len(value) != 2:
            self.fail(f'{what} must be a point [x, y]')
        if on_canvas:
            return [self.number_in(value[0], f'the x of {what}', 0, self.w),
                    self.number_in(value[1], f'the y of {what}', 0, self.h)]
        return [self.x(value[0], f'the x of {what}'), self.y(value[1], f'the y of {what}')]

    def polygon(self, value, what: str) -> list:
        if not isinstance(value, list) or not 3 <= len(value) <= MAX_CORNERS:
            self.fail(f'{what} must have 3 to {MAX_CORNERS} corners')
        return [self.point(p, f'a corner of {what}') for p in value]

    def items(self, hole: dict, key: str, clean_one: Callable) -> list:
        value = hole.get(key, [])
        limit = LIST_LIMITS[key]
        one, many = ITEM_NAMES[key]
        if not isinstance(value, list):
            self.fail(f'the {many} must be a list')
        if len(value) > limit:
            self.fail(f'it has {len(value)} {many}, {limit} at most')
        return [clean_one(item, f'{one} {i + 1}') for i, item in enumerate(value)]

    def area(self, value, what: str, extra: int = 0) -> list:
        """A rect [x, y, w, h], plus extra numbers that the caller checks."""
        if not isinstance(value, list) or len(value) != 4 + extra:
            self.fail(f'{what} must be [x, y, width, height{", dx, dy" if extra else ""}]')
        return [self.x(value[0], f'the x of {what}'), self.y(value[1], f'the y of {what}'),
                self.number_in(value[2], f'the width of {what}', 0, 2 * self.w),
                self.number_in(value[3], f'the height of {what}', 0, 2 * self.h)]

    def boost(self, value, what: str) -> list:
        r = self.area(value, what, extra=2)
        return r + [self.number_in(value[4], f'the dx of {what}', -1, 1),
                    self.number_in(value[5], f'the dy of {what}', -1, 1)]

    def bumper(self, value, what: str) -> list:
        if not isinstance(value, list) or len(value) != 3:
            self.fail(f'{what} must be [x, y, radius]')
        return [self.x(value[0], f'the x of {what}'), self.y(value[1], f'the y of {what}'),
                self.number_in(value[2], f'the radius of {what}', 1, MAX_BUMPER)]

    def slider(self, value, what: str) -> dict:
        if not isinstance(value, dict):
            self.fail(f'{what} must be an object')
        return {
            'x': self.x(value.get('x'), f'the x of {what}'), 'y': self.y(value.get('y'), f'the y of {what}'),
            'w': self.number_in(value.get('w'), f'the width of {what}', 1, self.w),
            'h': self.number_in(value.get('h'), f'the height of {what}', 1, self.h),
            'ax': self.number_in(value.get('ax'), f'how far {what} slides across', -self.w, self.w),
            'ay': self.number_in(value.get('ay'), f'how far {what} slides down', -self.h, self.h),
            'speed': self.number_in(value.get('speed'), f'the speed of {what}', -MAX_SPEED, MAX_SPEED),
            'phase': self.number_in(value.get('phase'), f'the phase of {what}', -100, 100),
        }

    def rotor(self, value, what: str) -> dict:
        if not isinstance(value, dict):
            self.fail(f'{what} must be an object')
        blades = value.get('blades')
        if type(blades) is not int or not 1 <= blades <= MAX_BLADES:
            self.fail(f'{what} must have 1 to {MAX_BLADES} blades')
        door = value.get('door')
        if not isinstance(door, list) or len(door) != 2:
            self.fail(f'the door of {what} must be [from x, to x]')
        door = [self.x(door[0], f'the door of {what}'), self.x(door[1], f'the door of {what}')]
        if door[0] > door[1]:
            self.fail(f'the door of {what} must go from left to right')
        return {
            'cx': self.x(value.get('cx'), f'the x of {what}'), 'cy': self.y(value.get('cy'), f'the y of {what}'),
            'len': self.number_in(value.get('len'), f'the length of the blades of {what}', 1, self.w),
            'speed': self.number_in(value.get('speed'), f'the speed of {what}', -MAX_SPEED, MAX_SPEED),
            'blades': blades, 'door': door,
        }

    def clean(self, hole) -> dict:
        if not isinstance(hole, dict):
            self.fail('must be an object')
        try:
            name = clean_text(hole.get('name'), 'its name', MAX_NAME)
        except PackError as e:
            self.fail(str(e))
        par = hole.get('par')
        if type(par) is not int or not 1 <= par <= self.max_strokes:
            self.fail(f'par must be a whole number from 1 to {self.max_strokes}')
        out = {'name': name, 'par': par, 'outline': self.polygon(hole.get('outline'), 'the outline')}

        lists = {
            'blocks': self.items(hole, 'blocks', self.polygon),
            'sand': self.items(hole, 'sand', self.area),
            'water': self.items(hole, 'water', self.area),
            'boosts': self.items(hole, 'boosts', self.boost),
            'rotors': self.items(hole, 'rotors', self.rotor),
            'sliders': self.items(hole, 'sliders', self.slider),
            'bumpers': self.items(hole, 'bumpers', self.bumper),
        }
        if len(out['outline']) + sum(len(b) for b in lists['blocks']) > MAX_WALL_CORNERS:
            self.fail(f'the outline and the blocks have more than {MAX_WALL_CORNERS} corners together')
        out.update({k: v for k, v in lists.items() if v})
        if hole.get('house') is True:
            out['house'] = True

        if 'starts' in hole:
            starts = hole['starts']
            if not isinstance(starts, list) or not 1 <= len(starts) <= MAX_TEES:
                self.fail(f'it must have 1 to {MAX_TEES} tees')
        elif 'start' in hole:
            starts = [hole['start']]
        else:
            self.fail('there is no tee')
        tees = [self.point(t, f'tee {i + 1}', on_canvas=True) for i, t in enumerate(starts)]
        cup = self.point(hole.get('cup'), 'the cup', on_canvas=True)

        def on_fairway(p: list) -> bool:
            return (inside_polygon(p[0], p[1], out['outline'])
                    and not any(inside_polygon(p[0], p[1], b) for b in lists['blocks'])
                    and not any(_in_rect(p[0], p[1], r) for r in lists['water']))

        for i, tee in enumerate(tees):
            if not on_fairway(tee):
                self.fail(f'tee {i + 1} is off the fairway or in the water')
        if not on_fairway(cup):
            self.fail('the cup is off the fairway or in the water')
        if len(tees) == 1:
            out['start'] = tees[0]
        else:
            out['starts'] = tees
        out['cup'] = cup
        return out
