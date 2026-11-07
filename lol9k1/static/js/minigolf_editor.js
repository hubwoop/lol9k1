/*
 * The minigolf map editor (/minigolf/editor): build holes, test play them and export them as code
 * for lol9k1MinigolfPacks in static/js/minigolf.js.
 *
 * The game on the page (static/js/minigolf.js in editor mode, see window.lol9k1Minigolf) draws the hole
 * being edited, windmills and sliders moving, and plays it on a test run. The editor draws its grid,
 * handles and helpers on a canvas of its own on top of the game's.
 * Everything stays in this browser: the workspace is kept in localStorage, nothing goes to the server.
 */

/*
 * What doesn't depend on the page: holes as plain data, turned into code and back, and checked.
 */
window.lol9k1MinigolfEditorTools = (function () {
    'use strict';

    const BALL_R = 6;
    const WALL_R = BALL_R + 4;
    const CUP_R = 10;
    // the lists of things on a hole, in the order they're exported in
    const LISTS = ['blocks', 'sand', 'water', 'boosts', 'rotors', 'sliders', 'bumpers', 'starts'];

    function rect(x, y, w, h) {
        return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]];
    }

    function clone(value) {
        return JSON.parse(JSON.stringify(value));
    }

    // A hole as the editor keeps it: every list there, even if it's empty, and the tees always as starts.
    function normalize(def) {
        const h = clone(def);
        h.name = typeof h.name === 'string' ? h.name : 'Untitled';
        h.par = Number.isInteger(h.par) ? h.par : 3;
        if (!Array.isArray(h.starts)) {
            h.starts = Array.isArray(h.start) ? [h.start] : [];
        }
        delete h.start;
        LISTS.forEach(k => {
            if (!Array.isArray(h[k])) {
                h[k] = [];
            }
        });
        if (!Array.isArray(h.outline)) {
            h.outline = rect(60, 100, 520, 200);
        }
        if (!Array.isArray(h.cup)) {
            h.cup = [530, 200];
        }
        return h;
    }

    function newHole() {
        return normalize({name: 'New hole', par: 3, outline: rect(60, 100, 520, 200), start: [110, 200], cup: [530, 200]});
    }

    // A hole as the game takes it: no empty lists, a single start or several.
    function toDef(h) {
        const def = {};
        Object.keys(h).forEach(k => {
            if (k === 'starts' || (LISTS.includes(k) && !h[k].length) || (k === 'house' && !h.house)) {
                return;
            }
            def[k] = clone(h[k]);
        });
        if (h.starts.length === 1) {
            def.start = clone(h.starts[0]);
        } else if (h.starts.length) {
            def.starts = clone(h.starts);
        }
        return def;
    }

    // ---------------------------------------------------------------- code
    function num(v) {
        return String(Math.round(v * 1000) / 1000 + 0);
    }

    function quote(s) {
        return `'${String(s).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/\n/g, '\\n')}'`;
    }

    function ident(k) {
        return /^[A-Za-z_$][\w$]*$/.test(k) ? k : quote(k);
    }

    function lit(v) {
        if (typeof v === 'number') {
            return num(v);
        }
        if (typeof v === 'string') {
            return quote(v);
        }
        if (typeof v === 'boolean' || v === null) {
            return String(v);
        }
        if (Array.isArray(v)) {
            return `[${v.map(lit).join(', ')}]`;
        }
        return `{${Object.keys(v).map(k => `${ident(k)}: ${lit(v[k])}`).join(', ')}}`;
    }

    function isRect(p) {
        return p.length === 4 && p[0][1] === p[1][1] && p[1][0] === p[2][0] && p[2][1] === p[3][1]
            && p[3][0] === p[0][0] && p[1][0] > p[0][0] && p[2][1] > p[1][1];
    }

    function polyLit(p) {
        return isRect(p) ? `rect(${num(p[0][0])}, ${num(p[0][1])}, ${num(p[1][0] - p[0][0])}, ${num(p[2][1] - p[1][1])})`
            : lit(p);
    }

    const LINE = 116;

    // key: [items], on one line if it fits, wrapped onto lines of their own if it doesn't
    function listCode(indent, key, items, itemLit) {
        const inline = `${indent}${key}: [${items.map(itemLit).join(', ')}],`;
        if (inline.length <= LINE) {
            return inline;
        }
        const lines = [];
        let line = '';
        items.map(itemLit).forEach(text => {
            if (line && `${indent}    ${line} ${text},`.length > LINE) {
                lines.push(line);
                line = '';
            }
            line += (line ? ' ' : '') + text + ',';
        });
        lines.push(line);
        return `${indent}${key}: [\n${lines.map(l => `${indent}    ${l}`).join('\n')}\n${indent}],`;
    }

    // A hole as code in the style of lol9k1MinigolfPacks, indented for its place in a pack.
    function holeCode(h, indent) {
        indent = indent === undefined ? '        ' : indent;
        const def = toDef(h);
        const i2 = indent + '    ';
        const lines = [`${indent}{`, `${i2}name: ${quote(def.name)}, par: ${num(def.par)},`];
        const done = new Set(['name', 'par', 'start', 'starts', 'cup']);
        if (def.outline) {
            const inline = `${i2}outline: ${polyLit(def.outline)},`;
            lines.push(inline.length <= LINE ? inline : listCode(i2, 'outline', def.outline, lit));
            done.add('outline');
        }
        ['blocks', 'sand', 'water', 'boosts', 'rotors', 'house', 'sliders', 'bumpers'].forEach(k => {
            if (def[k] === undefined) {
                return;
            }
            done.add(k);
            if (k === 'house') {
                lines.push(`${i2}house: ${lit(def.house)},`);
            } else {
                lines.push(listCode(i2, k, def[k], k === 'blocks' ? polyLit : lit));
            }
        });
        Object.keys(def).filter(k => !done.has(k)).forEach(k => lines.push(`${i2}${ident(k)}: ${lit(def[k])},`));
        const tee = def.starts ? `starts: ${lit(def.starts)}` : (def.start ? `start: ${lit(def.start)}` : '');
        const last = `${i2}${tee ? tee + ', ' : ''}cup: ${lit(def.cup)},`;
        if (last.length <= LINE) {
            lines.push(last);
        } else {
            lines.push(listCode(i2, 'starts', def.starts, lit), `${i2}cup: ${lit(def.cup)},`);
        }
        lines.push(`${indent}},`);
        return lines.join('\n');
    }

    function constName(id) {
        return (String(id).replace(/\W+/g, '_').toUpperCase() || 'DRAFT').replace(/^(\d)/, '_$1');
    }

    // The whole pack: the holes for static/js/minigolf.js and its line in COURSES in lol9k1/minigolf.py.
    function packCode(pack) {
        const name = constName(pack.id);
        return [
            '    // in lol9k1/static/js/minigolf.js, in lol9k1MinigolfPacks:',
            `    const ${name} = [`,
            ...pack.holes.map(h => holeCode(h, '        ')),
            '    ];',
            '',
            '    // ...and in what it returns:',
            `        ${ident(pack.id)}: {holes: ${name}, hint: ${quote(pack.hint || '')}},`,
            '',
            '# in lol9k1/minigolf.py, in COURSES:',
            `    ${pyQuote(pack.id)}: {'name': ${pyQuote(pack.name)}, 'holes': ${pack.holes.length}},`,
        ].join('\n');
    }

    function pyQuote(s) {
        return `'${String(s).replace(/\\/g, '\\\\').replace(/'/g, "\\'")}'`;
    }

    // Reads code as it's exported, or as the holes are written in minigolf.js: JavaScript literals,
    // rect(x, y, w, h), comments and trailing commas. Given `const NAME = [...];` it reads the list and
    // ignores what's around it, so a whole exported pack can be pasted.
    // It's parsed, not run, so pasting code can't do anything but make holes.
    function parseCode(text) {
        let pos = 0;
        const declaration = /(?:const|let|var)\s+[\w$]+\s*=\s*/.exec(text);
        const src = declaration ? text.slice(declaration.index + declaration[0].length) : text;

        function fail(what) {
            const line = src.slice(0, pos).split('\n').length;
            throw new Error(`${what} on line ${line}`);
        }

        function skip() {
            for (;;) {
                const m = /^(?:\s+|\/\/[^\n]*|\/\*[\s\S]*?\*\/)/.exec(src.slice(pos));
                if (!m) {
                    return;
                }
                pos += m[0].length;
            }
        }

        function eat(ch) {
            skip();
            if (src[pos] !== ch) {
                fail(`expected ${ch}`);
            }
            pos += 1;
        }

        function peek() {
            skip();
            return src[pos];
        }

        function string() {
            const q = src[pos];
            let out = '';
            pos += 1;
            while (pos < src.length && src[pos] !== q) {
                if (src[pos] === '\\') {
                    const c = src[pos + 1];
                    out += c === 'n' ? '\n' : c === 't' ? '\t' : c;
                    pos += 2;
                } else {
                    out += src[pos++];
                }
            }
            if (src[pos] !== q) {
                fail('unterminated string');
            }
            pos += 1;
            return out;
        }

        function list(close, item) {
            const out = [];
            while (peek() !== close) {
                out.push(item());
                if (peek() === ',') {
                    pos += 1;
                } else if (peek() !== close) {
                    fail(`expected , or ${close}`);
                }
            }
            pos += 1;
            return out;
        }

        function value() {
            const c = peek();
            if (c === '[') {
                pos += 1;
                return list(']', value);
            }
            if (c === '{') {
                pos += 1;
                const obj = {};
                list('}', () => {
                    skip();
                    let key;
                    if (src[pos] === "'" || src[pos] === '"') {
                        key = string();
                    } else {
                        const m = /^[A-Za-z_$][\w$]*/.exec(src.slice(pos));
                        if (!m) {
                            fail('expected a key');
                        }
                        key = m[0];
                        pos += key.length;
                    }
                    eat(':');
                    obj[key] = value();
                });
                return obj;
            }
            if (c === "'" || c === '"') {
                return string();
            }
            const m = /^(?:-?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?|true|false|null|rect\b)/.exec(src.slice(pos));
            if (!m) {
                fail('unexpected ' + (src[pos] === undefined ? 'end' : `"${src[pos]}"`));
            }
            pos += m[0].length;
            if (m[0] === 'rect') {
                eat('(');
                const args = list(')', value);
                if (args.length !== 4 || !args.every(a => typeof a === 'number')) {
                    fail('rect takes x, y, width and height');
                }
                return rect(...args);
            }
            return m[0] === 'true' ? true : m[0] === 'false' ? false : m[0] === 'null' ? null : Number(m[0]);
        }

        const result = value();
        skip();
        if (pos >= src.length || (declaration && src[pos] === ';')
            || /^[\s;,]*$/.test(src.slice(pos).replace(/\/\/[^\n]*|\/\*[\s\S]*?\*\//g, ''))) {
            return result;
        }
        fail('unexpected text after the end');
    }

    // The holes in pasted code: a hole, a list of them or a pack ({holes: [...]}).
    function importHoles(text) {
        const parsed = parseCode(text);
        const holes = Array.isArray(parsed) ? parsed : (parsed && Array.isArray(parsed.holes) ? parsed.holes : [parsed]);
        if (!holes.length) {
            throw new Error('there are no holes in it');
        }
        holes.forEach((h, i) => {
            if (!h || typeof h !== 'object' || !Array.isArray(h.outline) || !Array.isArray(h.cup)) {
                throw new Error(`hole ${i + 1} needs an outline and a cup`);
            }
        });
        return holes.map(normalize);
    }

    // ---------------------------------------------------------------- geometry
    function insidePolygon(x, y, poly) {
        let inside = false;
        for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
            const [xi, yi] = poly[i], [xj, yj] = poly[j];
            if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) {
                inside = !inside;
            }
        }
        return inside;
    }

    function segmentDistance(x, y, ax, ay, bx, by) {
        const abx = bx - ax, aby = by - ay;
        const len2 = abx * abx + aby * aby;
        const t = len2 ? Math.max(0, Math.min(1, ((x - ax) * abx + (y - ay) * aby) / len2)) : 0;
        return Math.hypot(x - ax - abx * t, y - ay - aby * t);
    }

    function polygonDistance(x, y, poly) {
        let best = Infinity;
        poly.forEach((a, i) => {
            const b = poly[(i + 1) % poly.length];
            best = Math.min(best, segmentDistance(x, y, a[0], a[1], b[0], b[1]));
        });
        return best;
    }

    function inRect(x, y, r) {
        return x >= r[0] && x <= r[0] + r[2] && y >= r[1] && y <= r[1] + r[3];
    }

    // ---------------------------------------------------------------- fair tees
    //
    // Like test_every_tee_of_a_hole_is_as_good_as_the_others in tests/e2e/test_minigolf_packs.py:
    // the tees of a hole are as good as each other when a mirror or a turn of the hole that leaves it as
    // it is takes the first tee to every other one.
    function transforms(w, h) {
        const cx = w / 2, cy = h / 2;
        return {
            'mirrored left to right': (x, y) => [2 * cx - x, y],
            'mirrored top to bottom': (x, y) => [x, 2 * cy - y],
            'turned half way round': (x, y) => [2 * cx - x, 2 * cy - y],
            'turned a quarter clockwise': (x, y) => [cx - (y - cy), cy + (x - cx)],
            'turned a quarter anticlockwise': (x, y) => [cx + (y - cy), cy - (x - cx)],
        };
    }

    function r3(v) {
        return Math.round(v * 1000) / 1000 + 0;
    }

    function pointKey(p) {
        return `${r3(p[0])},${r3(p[1])}`;
    }

    function setKey(keys) {
        return Array.from(new Set(keys)).sort().join(';');
    }

    function polygonKey(points, t) {
        const moved = points.map(p => pointKey(t(p[0], p[1])));
        return setKey(moved.map((a, i) => {
            const b = moved[(i + 1) % moved.length];
            return a < b ? `${a}|${b}` : `${b}|${a}`;
        }));
    }

    function rectKey(r, t) {
        const a = t(r[0], r[1]), b = t(r[0] + r[2], r[1] + r[3]);
        return [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[0], b[0]), Math.max(a[1], b[1])].map(r3).join(',');
    }

    // everything on a hole that makes a difference to a ball, moved by t, by what it is
    function shape(h, t) {
        const sliders = [];
        for (let i = 0; i < 50; i++) {
            const time = i / 10;
            sliders.push(setKey(h.sliders.map(s => {
                const k = Math.sin(time * s.speed + s.phase) * 0.5 + 0.5;
                return rectKey([s.x + s.ax * k, s.y + s.ay * k, s.w, s.h], t);
            })));
        }
        return {
            cup: pointKey(t(h.cup[0], h.cup[1])),
            outline: polygonKey(h.outline, t),
            blocks: setKey(h.blocks.map(b => `(${polygonKey(b, t)})`)),
            water: setKey(h.water.map(r => rectKey(r, t))),
            sand: setKey(h.sand.map(r => rectKey(r, t))),
            boosts: setKey(h.boosts.map(b => {
                const cx = b[0] + b[2] / 2, cy = b[1] + b[3] / 2;
                const m = t(cx, cy), d = t(cx + b[4], cy + b[5]);
                return `${rectKey(b, t)}>${pointKey([d[0] - m[0], d[1] - m[1]])}`;
            })),
            bumpers: setKey(h.bumpers.map(b => `${pointKey(t(b[0], b[1]))},${r3(b[2])}`)),
            sliders: sliders.join('/'),
        };
    }

    const THINGS = {cup: 'the cup', outline: 'the outline', blocks: 'the blocks', water: 'the water', sand: 'the sand',
        boosts: 'the boosts', bumpers: 'the bumpers', sliders: 'the sliders'};

    // Why the tees of the hole aren't equally good, a list of messages, empty if they are.
    function unfairTees(h, w, hh) {
        if (h.starts.length < 2) {
            return [];
        }
        if (h.rotors.length) {
            return ['With windmills, whether every tee is as good as the others isn\'t checked.'];
        }
        const same = shape(h, (x, y) => [x, y]);
        const all = transforms(w, hh);
        const problems = [];
        h.starts.slice(1).forEach((tee, i) => {
            let best = null;
            Object.entries(all).forEach(([name, t]) => {
                if (pointKey(t(h.starts[0][0], h.starts[0][1])) !== pointKey(tee)) {
                    return;
                }
                const moved = shape(h, t);
                const off = Object.keys(same).filter(k => same[k] !== moved[k]);
                if (!best || off.length < best.off.length) {
                    best = {name, off};
                }
            });
            if (best && !best.off.length) {
                return;
            }
            const number = i + 2;
            if (!best) {
                problems.push(`Tee ${number} isn't as good as tee 1: no mirror or turn of the course takes tee 1 there.`);
            } else {
                problems.push(`Tee ${number} isn't as good as tee 1: ${best.name}, the hole would be the same `
                    + `but for ${best.off.map(k => THINGS[k]).join(', ')}.`);
            }
        });
        return problems;
    }

    // ---------------------------------------------------------------- checks
    // What's wrong with a hole, as {level: 'error' | 'warning', text}. Errors keep it from being tested.
    function check(h, w, hh) {
        const out = [];
        const error = text => out.push({level: 'error', text});
        const warn = text => out.push({level: 'warning', text});
        if (!h.name.trim()) {
            warn('The hole has no name.');
        }
        if (!Number.isInteger(h.par) || h.par < 1) {
            warn('Par should be a whole number of at least 1.');
        }
        if (h.outline.length < 3) {
            error('The outline needs at least 3 corners.');
            return out;
        }
        const walls = [h.outline, ...h.blocks];
        const wallDistance = (x, y) => Math.min(...walls.map(p => polygonDistance(x, y, p)));
        const onFairway = (x, y) => insidePolygon(x, y, h.outline) && !h.blocks.some(b => insidePolygon(x, y, b));
        const offCanvas = (x, y) => x < 0 || x > w || y < 0 || y > hh;

        if (!h.starts.length) {
            error('There is no tee.');
        }
        h.starts.forEach((tee, i) => {
            const what = h.starts.length > 1 ? `Tee ${i + 1}` : 'The tee';
            if (!onFairway(tee[0], tee[1])) {
                error(`${what} is off the fairway.`);
            } else if (wallDistance(tee[0], tee[1]) < WALL_R) {
                warn(`${what} is so close to a wall that the ball starts inside it.`);
            }
            if (h.water.some(r => inRect(tee[0], tee[1], r))) {
                error(`${what} is in the water.`);
            }
        });
        if (!onFairway(h.cup[0], h.cup[1])) {
            error('The cup is off the fairway.');
        } else if (wallDistance(h.cup[0], h.cup[1]) < WALL_R) {
            warn('The cup is right up against a wall, the ball may not reach it.');
        }
        if (h.water.some(r => inRect(h.cup[0], h.cup[1], r))) {
            error('The cup is in the water.');
        }
        if (h.bumpers.some(b => Math.hypot(b[0] - h.cup[0], b[1] - h.cup[1]) < b[2] + CUP_R - 2)) {
            warn('A bumper covers the cup.');
        }
        const points = [...h.outline, ...h.blocks.flat(), ...h.starts, h.cup];
        if (points.some(p => offCanvas(p[0], p[1]))) {
            warn('Something is off the canvas, balls can\'t go there.');
        }
        // things that would do nothing, without anything else telling
        h.sliders.forEach((s, i) => {
            if (offCanvas(s.x + s.ax, s.y + s.ay) || offCanvas(s.x + s.ax + s.w, s.y + s.ay + s.h)) {
                warn(`Slider ${i + 1} slides off the canvas.`);
            }
        });
        h.boosts.forEach((b, i) => {
            if (!b[4] && !b[5]) {
                warn(`Boost ${i + 1} doesn't push anywhere.`);
            }
        });
        [['Sand', h.sand], ['Water', h.water], ['Boost', h.boosts]].forEach(([what, rects]) => rects.forEach((r, i) => {
            if (!(r[2] > 0 && r[3] > 0)) {
                warn(`${what} ${i + 1} has no size, it does nothing.`);
            }
        }));
        unfairTees(h, w, hh).forEach(warn);
        return out;
    }

    return {rect, clone, normalize, newHole, toDef, holeCode, packCode, parseCode, importHoles, insidePolygon,
        polygonDistance, segmentDistance, inRect, transforms, unfairTees, check, LISTS, BALL_R, WALL_R, CUP_R};
})();

/*
 * The editor page.
 */
(function () {
    'use strict';

    const root = document.getElementById('minigolfEditor');
    const game = window.lol9k1Minigolf;
    if (!root || !game) {
        return;
    }
    const T = window.lol9k1MinigolfEditorTools;
    const PACKS = window.lol9k1MinigolfPacks;
    const SERVER_COURSES = JSON.parse(root.dataset.courses || '{}');
    const W = parseInt(root.dataset.width, 10), H = parseInt(root.dataset.height, 10);
    const CX = W / 2, CY = H / 2;
    const TEE = 14;                 // half the size of a tee box
    const STORAGE_KEY = 'minigolfEditor';
    const MIN_SIZE = 4;

    const $ = id => document.getElementById(id);
    const stage = document.querySelector('#minigolf .minigolfStage');

    // the editor's own canvas, on top of the game's
    const overlay = document.createElement('canvas');
    overlay.className = 'mgeOverlay';
    overlay.setAttribute('aria-label', 'Map editor');
    stage.appendChild(overlay);
    const ctx = overlay.getContext('2d');
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    overlay.width = W * dpr;
    overlay.height = H * dpr;

    // ---------------------------------------------------------------- the workspace
    let pack = null;            // {id, name, hint, holes: [normalized holes]}
    let current = 0;            // the hole being edited
    let selected = null;        // {kind, i, v}: kind outline | cup | one of T.LISTS, i its index, v a corner
    let tool = 'select';
    let undoStack = [], redoStack = [];
    let snapSize = 10;
    let drag = null;
    let hover = null;
    let pointer = null;         // where the pointer is on the course
    let testing = false;

    function hole() {
        return pack.holes[current];
    }

    function loadPack(id) {
        if (id && PACKS[id]) {
            const known = SERVER_COURSES[id];
            pack = {id, name: known ? known.name : id, hint: PACKS[id].hint || '', holes: PACKS[id].holes.map(T.normalize)};
        } else {
            pack = {id: 'draft', name: 'Draft', hint: '', holes: [T.newHole()]};
        }
        current = 0;
        selected = null;
    }

    function snapshot() {
        return JSON.stringify({pack, current});
    }

    function restore(json) {
        const s = JSON.parse(json);
        pack = s.pack;
        current = Math.min(s.current, pack.holes.length - 1);
        selected = null;
    }

    // call before changing the workspace, so the change can be undone
    function checkpoint() {
        undoStack.push(snapshot());
        if (undoStack.length > 200) {
            undoStack.shift();
        }
        redoStack = [];
    }

    function undo() {
        if (undoStack.length) {
            redoStack.push(snapshot());
            restore(undoStack.pop());
            changed();
        }
    }

    function redo() {
        if (redoStack.length) {
            undoStack.push(snapshot());
            restore(redoStack.pop());
            changed();
        }
    }

    function save() {
        try {
            localStorage.setItem(STORAGE_KEY, snapshot());
        } catch (e) { /* storage blocked, the workspace lasts as long as the page */ }
    }

    // after every change: the game shows it, the panels too
    function changed() {
        save();
        if (!testing) {
            game.preview(T.toDef(hole()));
        }
        renderPanels();
    }

    // ---------------------------------------------------------------- things on the hole
    const NAMES = {outline: 'Outline', cup: 'Cup', starts: 'Tee', blocks: 'Block', sand: 'Sand', water: 'Water',
        boosts: 'Boost', bumpers: 'Bumper', sliders: 'Slider', rotors: 'Windmill'};
    const RECTS = ['sand', 'water', 'boosts'];

    function item(sel) {
        const h = hole();
        if (sel.kind === 'outline' || sel.kind === 'cup') {
            return h[sel.kind];
        }
        return h[sel.kind][sel.i];
    }

    function isPolygon(kind) {
        return kind === 'outline' || kind === 'blocks';
    }

    function rectOf(kind, it) {
        return kind === 'sliders' ? {x: it.x, y: it.y, w: it.w, h: it.h} : {x: it[0], y: it[1], w: it[2], h: it[3]};
    }

    function setRect(kind, it, r) {
        if (kind === 'sliders') {
            Object.assign(it, {x: r.x, y: r.y, w: r.w, h: r.h});
        } else {
            it[0] = r.x;
            it[1] = r.y;
            it[2] = r.w;
            it[3] = r.h;
        }
    }

    // the point a thing is moved by, snapped to the grid
    function anchor(kind, it) {
        if (isPolygon(kind)) {
            return it[0];
        }
        if (kind === 'sliders') {
            return [it.x, it.y];
        }
        if (kind === 'rotors') {
            return [it.cx, it.cy];
        }
        return [it[0], it[1]];
    }

    function translate(kind, it, dx, dy) {
        if (isPolygon(kind)) {
            it.forEach(p => {
                p[0] += dx;
                p[1] += dy;
            });
        } else if (kind === 'sliders') {
            it.x += dx;
            it.y += dy;
        } else if (kind === 'rotors') {
            it.cx += dx;
            it.cy += dy;
            it.door = [it.door[0] + dx, it.door[1] + dx];
        } else {
            it[0] += dx;
            it[1] += dy;
        }
    }

    // the same thing moved by t (a mirror or a turn of the course)
    function transformed(kind, it, t) {
        const vec = (x, y) => {
            const a = t(0, 0), b = t(x, y);
            return [b[0] - a[0], b[1] - a[1]];
        };
        const rectBy = (x, y, w, h) => {
            const a = t(x, y), b = t(x + w, y + h);
            return {x: Math.min(a[0], b[0]), y: Math.min(a[1], b[1]), w: Math.abs(b[0] - a[0]), h: Math.abs(b[1] - a[1])};
        };
        if (isPolygon(kind)) {
            return it.map(p => t(p[0], p[1]));
        }
        if (RECTS.includes(kind)) {
            const r = rectBy(it[0], it[1], it[2], it[3]);
            const out = [r.x, r.y, r.w, r.h];
            if (kind === 'boosts') {
                out.push(...vec(it[4], it[5]));
            }
            return out;
        }
        if (kind === 'bumpers') {
            return [...t(it[0], it[1]), it[2]];
        }
        if (kind === 'sliders') {
            const r = rectBy(it.x, it.y, it.w, it.h);
            const [ax, ay] = vec(it.ax, it.ay);
            return Object.assign(T.clone(it), {x: r.x, y: r.y, w: r.w, h: r.h, ax, ay});
        }
        if (kind === 'rotors') {
            const [cx, cy] = t(it.cx, it.cy);
            const doors = [t(it.door[0], it.cy)[0], t(it.door[1], it.cy)[0]].sort((a, b) => a - b);
            const [ex, ey] = vec(1, 0), [fx, fy] = vec(0, 1);
            const mirrored = ex * fy - ey * fx < 0;
            return Object.assign(T.clone(it), {cx, cy, door: doors, speed: mirrored ? -it.speed : it.speed});
        }
        return t(it[0], it[1]);
    }

    // ---------------------------------------------------------------- placing things
    function snap(v) {
        return snapSize ? Math.round(v / snapSize) * snapSize : Math.round(v);
    }

    function snapPoint(p) {
        return [Math.max(0, Math.min(W, snap(p.x))), Math.max(0, Math.min(H, snap(p.y)))];
    }

    function place(kind, p) {
        const [x, y] = snapPoint(p);
        const h = hole();
        const made = {
            starts: () => [x, y],
            blocks: () => T.rect(x - 20, y - 20, 40, 40),
            sand: () => [x - 40, y - 30, 80, 60],
            water: () => [x - 40, y - 30, 80, 60],
            boosts: () => [x - 40, y - 30, 80, 60, 1, 0],
            bumpers: () => [x, y, 12],
            sliders: () => ({x: x - 13, y: y - 30, w: 26, h: 60, ax: 0, ay: 80, speed: 1.5, phase: 0}),
            rotors: () => ({cx: x, cy: y, len: 80, speed: 1.3, blades: 3, door: [x - 20, x + 20]}),
        }[kind]();
        checkpoint();
        h[kind].push(made);
        selected = {kind, i: h[kind].length - 1};
        changed();
    }

    function removeSelected() {
        if (!selected) {
            return;
        }
        const h = hole();
        if (isPolygon(selected.kind) && selected.v !== undefined) {
            const poly = item(selected);
            if (poly.length > 3) {
                checkpoint();
                poly.splice(selected.v, 1);
                selected = {kind: selected.kind, i: selected.i};
                changed();
            }
            return;
        }
        if (selected.kind === 'outline' || selected.kind === 'cup') {
            return;
        }
        checkpoint();
        h[selected.kind].splice(selected.i, 1);
        selected = null;
        changed();
    }

    function duplicateSelected() {
        if (!selected || selected.kind === 'outline' || selected.kind === 'cup') {
            return;
        }
        const copy = T.clone(item(selected));
        const step = snapSize || 10;
        translate(selected.kind, copy, step * 2, step * 2);
        checkpoint();
        hole()[selected.kind].push(copy);
        selected = {kind: selected.kind, i: hole()[selected.kind].length - 1};
        changed();
    }

    // copies of the selected thing, mirrored or turned
    function mirrorSelected(names) {
        if (!selected || selected.kind === 'outline' || selected.kind === 'cup') {
            return;
        }
        const all = T.transforms(W, H);
        const it = item(selected);
        checkpoint();
        names.forEach(name => hole()[selected.kind].push(transformed(selected.kind, it, all[name])));
        changed();
    }

    function nudge(dx, dy) {
        if (!selected) {
            return;
        }
        checkpoint();
        if (isPolygon(selected.kind) && selected.v !== undefined) {
            const p = item(selected)[selected.v];
            p[0] += dx;
            p[1] += dy;
        } else {
            translate(selected.kind, item(selected), dx, dy);
        }
        changed();
    }

    // ---------------------------------------------------------------- hit testing
    function scale() {
        return overlay.getBoundingClientRect().width / W || 1;
    }

    function handleSize() {
        return 5 / scale();
    }

    function toCourse(event) {
        const r = overlay.getBoundingClientRect();
        return {x: (event.clientX - r.left) * W / r.width, y: (event.clientY - r.top) * H / r.height};
    }

    // the handles of the selected thing: {x, y, action, ...}
    function handles(sel) {
        if (!sel) {
            return [];
        }
        const it = item(sel);
        const out = [];
        if (isPolygon(sel.kind)) {
            it.forEach((p, v) => {
                out.push({x: p[0], y: p[1], action: 'vertex', v});
                const q = it[(v + 1) % it.length];
                out.push({x: (p[0] + q[0]) / 2, y: (p[1] + q[1]) / 2, action: 'insert', v: v + 1, small: true});
            });
        } else if (RECTS.includes(sel.kind) || sel.kind === 'sliders') {
            const r = rectOf(sel.kind, it);
            [[r.x, r.y], [r.x + r.w, r.y], [r.x + r.w, r.y + r.h], [r.x, r.y + r.h]].forEach((p, c) =>
                out.push({x: p[0], y: p[1], action: 'corner', c}));
            if (sel.kind === 'sliders') {
                out.push({x: r.x + it.ax + r.w / 2, y: r.y + it.ay + r.h / 2, action: 'travel', round: true});
            }
        } else if (sel.kind === 'bumpers') {
            out.push({x: it[0] + it[2], y: it[1], action: 'radius', round: true});
        } else if (sel.kind === 'rotors') {
            out.push({x: it.cx + it.len, y: it.cy, action: 'length', round: true});
            out.push({x: it.door[0], y: it.cy + it.len + 10, action: 'door', d: 0});
            out.push({x: it.door[1], y: it.cy + it.len + 10, action: 'door', d: 1});
        }
        return out;
    }

    // what's at this point of the course, the topmost thing first
    function hitTest(p) {
        const tol = 6 / scale();
        const near = handles(selected).find(hd => Math.abs(hd.x - p.x) <= handleSize() + tol / 2
            && Math.abs(hd.y - p.y) <= handleSize() + tol / 2);
        if (near) {
            return {handle: near};
        }
        const h = hole();
        if (Math.hypot(h.cup[0] - p.x, h.cup[1] - p.y) <= T.CUP_R + tol) {
            return {kind: 'cup'};
        }
        const lists = [
            ['starts', t => Math.abs(t[0] - p.x) <= TEE && Math.abs(t[1] - p.y) <= TEE],
            ['rotors', r => Math.hypot(r.cx - p.x, r.cy - p.y) <= 10 + tol],
            ['bumpers', b => Math.hypot(b[0] - p.x, b[1] - p.y) <= b[2] + tol / 2],
            ['sliders', s => T.inRect(p.x, p.y, [s.x, s.y, s.w, s.h])],
            ['blocks', b => T.insidePolygon(p.x, p.y, b) || T.polygonDistance(p.x, p.y, b) <= tol],
            ['boosts', r => T.inRect(p.x, p.y, r)],
            ['water', r => T.inRect(p.x, p.y, r)],
            ['sand', r => T.inRect(p.x, p.y, r)],
        ];
        for (const [kind, hit] of lists) {
            for (let i = h[kind].length - 1; i >= 0; i--) {
                if (hit(h[kind][i])) {
                    return {kind, i};
                }
            }
        }
        if (T.insidePolygon(p.x, p.y, h.outline) || T.polygonDistance(p.x, p.y, h.outline) <= tol) {
            return {kind: 'outline'};
        }
        return null;
    }

    function sameThing(a, b) {
        return a && b && a.kind === b.kind && a.i === b.i;
    }

    // ---------------------------------------------------------------- pointer
    overlay.addEventListener('pointerdown', function (event) {
        if (event.button !== 0 || testing) {
            return;
        }
        const p = toCourse(event);
        if (tool !== 'select') {
            place(tool, p);
            if (!event.shiftKey) {
                setTool('select');
            }
            return;
        }
        const hit = hitTest(p);
        if (hit && hit.handle) {
            const hd = hit.handle;
            drag = {action: hd.action, handle: hd, sel: {kind: selected.kind, i: selected.i}, start: p,
                orig: T.clone(item(selected)), saved: false};
            if (hd.action === 'insert') {
                checkpoint();
                drag.saved = true;
                item(selected).splice(hd.v, 0, snapPoint(p));
                drag.action = 'vertex';
                drag.handle = {action: 'vertex', v: hd.v};
                selected = {kind: selected.kind, i: selected.i, v: hd.v};
                changed();
            } else if (hd.action === 'vertex') {
                selected = {kind: selected.kind, i: selected.i, v: hd.v};
                renderPanels();
            }
        } else if (hit) {
            if (!sameThing(selected, hit) || selected.v !== undefined) {
                selected = {kind: hit.kind, i: hit.i};
                renderPanels();
            }
            // the outline stays put, it's what's clicked when there's nothing else
            if (hit.kind !== 'outline') {
                drag = {action: 'move', sel: selected, start: p, orig: T.clone(item(selected)), saved: false};
            }
        } else if (selected) {
            selected = null;
            renderPanels();
        }
        if (drag) {
            overlay.setPointerCapture(event.pointerId);
        }
    });

    overlay.addEventListener('pointermove', function (event) {
        pointer = toCourse(event);
        if (drag) {
            dragTo(pointer);
        } else if (!testing) {
            hover = tool === 'select' ? hitTest(pointer) : null;
            overlay.style.cursor = tool !== 'select' ? 'copy'
                : hover && hover.handle ? 'pointer'
                    : hover && hover.kind !== 'outline' ? 'move' : 'default';
        }
        showCoords();
    });

    overlay.addEventListener('pointerleave', function () {
        pointer = null;
        hover = null;
        showCoords();
    });

    function endDrag() {
        drag = null;
    }

    overlay.addEventListener('pointerup', endDrag);
    overlay.addEventListener('pointercancel', endDrag);

    function dragTo(p) {
        const kind = drag.sel.kind;
        const it = item(drag.sel);
        const before = JSON.stringify(it);
        const orig = drag.orig;
        // every move starts over from where the thing was, so snapping doesn't add up
        const fresh = T.clone(orig);
        const [sx, sy] = snapPoint(p);
        if (drag.action === 'move') {
            const a = anchor(kind, orig);
            const [nx, ny] = snapPoint({x: a[0] + p.x - drag.start.x, y: a[1] + p.y - drag.start.y});
            translate(kind, fresh, nx - a[0], ny - a[1]);
        } else if (drag.action === 'vertex') {
            fresh.splice(0, fresh.length, ...T.clone(it));
            fresh[drag.handle.v] = [sx, sy];
        } else if (drag.action === 'corner') {
            const r = rectOf(kind, orig);
            const c = drag.handle.c;
            // the opposite corner stays where it is
            const fx = c === 1 || c === 2 ? r.x : r.x + r.w, fy = c >= 2 ? r.y : r.y + r.h;
            const x0 = Math.min(fx, sx), x1 = Math.max(fx, sx), y0 = Math.min(fy, sy), y1 = Math.max(fy, sy);
            setRect(kind, fresh, {x: x0, y: y0, w: Math.max(MIN_SIZE, x1 - x0), h: Math.max(MIN_SIZE, y1 - y0)});
        } else if (drag.action === 'travel') {
            fresh.ax = snap(p.x - orig.w / 2) - orig.x;
            fresh.ay = snap(p.y - orig.h / 2) - orig.y;
        } else if (drag.action === 'radius') {
            fresh[2] = Math.max(3, Math.round(Math.hypot(p.x - orig[0], p.y - orig[1])));
        } else if (drag.action === 'length') {
            fresh.len = Math.max(10, Math.round(Math.hypot(p.x - orig.cx, p.y - orig.cy)));
        } else if (drag.action === 'door') {
            fresh.door[drag.handle.d] = sx;
            fresh.door.sort((a, b) => a - b);
        }
        if (JSON.stringify(fresh) === before) {
            return;
        }
        if (!drag.saved) {
            checkpoint();
            drag.saved = true;
        }
        // in place, so the selection stays on it
        if (Array.isArray(it)) {
            it.splice(0, it.length, ...fresh);
        } else {
            Object.keys(it).forEach(k => delete it[k]);
            Object.assign(it, fresh);
        }
        changed();
    }

    function showCoords() {
        const at = pointer ? `x ${Math.round(pointer.x)}, y ${Math.round(pointer.y)}` : '';
        let what = '';
        if (selected) {
            what = describe(selected);
        }
        $('mgeCoords').textContent = [at, what].filter(Boolean).join('  ·  ') || ' ';
    }

    function describe(sel) {
        const h = hole();
        let text = NAMES[sel.kind];
        if (sel.kind === 'starts' && h.starts.length > 1) {
            text += ` ${sel.i + 1}`;
        } else if (sel.i !== undefined && sel.kind !== 'starts') {
            text += ` ${sel.i + 1}`;
        }
        if (sel.v !== undefined) {
            text += `, corner ${sel.v + 1}`;
        }
        return text;
    }

    // ---------------------------------------------------------------- keyboard
    function typing(event) {
        const t = event.target;
        return t && !t.readOnly && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT'
            || t.isContentEditable);
    }

    const TOOL_KEYS = {v: 'select', e: 'starts', b: 'blocks', s: 'sand', w: 'water', o: 'boosts', u: 'bumpers',
        l: 'sliders', m: 'rotors'};

    window.addEventListener('keydown', function (event) {
        if (typing(event)) {
            return;
        }
        const key = event.key;
        const mod = event.ctrlKey || event.metaKey;
        if (key === 't' && !mod) {
            toggleTest();
            event.preventDefault();
            return;
        }
        if (testing) {
            return;
        }
        if (mod && key.toLowerCase() === 'z') {
            if (event.shiftKey) {
                redo();
            } else {
                undo();
            }
        } else if (mod && key === 'y') {
            redo();
        } else if (mod && key === 'd') {
            duplicateSelected();
        } else if (key === 'Delete' || key === 'Backspace') {
            removeSelected();
        } else if (key === 'Escape') {
            selected = null;
            setTool('select');
            renderPanels();
        } else if (key.startsWith('Arrow') && selected) {
            const step = event.shiftKey ? 1 : (snapSize || 1);
            const d = {ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step]}[key];
            nudge(d[0], d[1]);
        } else if (key === '[' || key === ']') {
            goToHole(current + (key === '[' ? -1 : 1));
        } else if (!mod && TOOL_KEYS[key]) {
            setTool(TOOL_KEYS[key]);
        } else {
            return;
        }
        event.preventDefault();
    });

    // ---------------------------------------------------------------- toolbar
    function setTool(name) {
        tool = name;
        document.querySelectorAll('#mgeTools [data-tool]').forEach(b => {
            b.setAttribute('aria-pressed', String(b.dataset.tool === tool));
        });
    }

    document.querySelectorAll('#mgeTools [data-tool]').forEach(b => {
        b.addEventListener('click', () => setTool(b.dataset.tool));
    });
    $('mgeUndo').addEventListener('click', undo);
    $('mgeRedo').addEventListener('click', redo);
    $('mgeSnap').addEventListener('change', function () {
        snapSize = parseInt(this.value, 10) || 0;
    });
    $('mgeTest').addEventListener('click', toggleTest);

    function toggleTest() {
        if (testing) {
            testing = false;
            game.stop();
            game.preview(T.toDef(hole()));
        } else {
            const errors = T.check(hole(), W, H).filter(c => c.level === 'error');
            if (errors.length) {
                $('minigolfStatus').textContent = `Can't test this hole: ${errors[0].text}`;
                return;
            }
            testing = true;
            selected = null;
            drag = null;
            game.test(T.toDef(hole()), parseInt($('mgePlayers').value, 10) || 1);
        }
        root.dataset.testing = String(testing);
        overlay.hidden = testing;
        $('mgeSide').disabled = testing;
        $('mgeTest').textContent = testing ? '■ Stop test' : '▶ Test';
        document.querySelectorAll('#mgeTools [data-tool], #mgeUndo, #mgeRedo').forEach(b => {
            b.disabled = testing;
        });
        renderPanels();
    }

    // ---------------------------------------------------------------- side panel
    function goToHole(index) {
        if (index < 0 || index >= pack.holes.length || index === current) {
            return;
        }
        current = index;
        selected = null;
        save();
        game.preview(T.toDef(hole()));
        renderPanels();
    }

    $('mgeLoad').addEventListener('click', function () {
        checkpoint();
        loadPack($('mgeLoadPack').value);
        changed();
    });

    function packField(id, key) {
        $(id).addEventListener('change', function () {
            checkpoint();
            pack[key] = this.value.trim();
            changed();
        });
    }

    packField('mgePackId', 'id');
    packField('mgePackName', 'name');
    packField('mgePackHint', 'hint');

    $('mgeAddHole').addEventListener('click', function () {
        checkpoint();
        pack.holes.splice(current + 1, 0, T.newHole());
        current += 1;
        selected = null;
        changed();
    });
    $('mgeDuplicateHole').addEventListener('click', function () {
        checkpoint();
        const copy = T.clone(hole());
        copy.name += ' (copy)';
        pack.holes.splice(current + 1, 0, copy);
        current += 1;
        selected = null;
        changed();
    });
    $('mgeDeleteHole').addEventListener('click', function () {
        if (pack.holes.length < 2) {
            return;
        }
        checkpoint();
        pack.holes.splice(current, 1);
        current = Math.min(current, pack.holes.length - 1);
        selected = null;
        changed();
    });

    function moveHole(by) {
        const to = current + by;
        if (to < 0 || to >= pack.holes.length) {
            return;
        }
        checkpoint();
        const [h] = pack.holes.splice(current, 1);
        pack.holes.splice(to, 0, h);
        current = to;
        changed();
    }

    $('mgeHoleUp').addEventListener('click', () => moveHole(-1));
    $('mgeHoleDown').addEventListener('click', () => moveHole(1));

    $('mgeHoleName').addEventListener('change', function () {
        checkpoint();
        hole().name = this.value;
        changed();
    });
    $('mgeHolePar').addEventListener('change', function () {
        const par = parseInt(this.value, 10);
        if (Number.isInteger(par)) {
            checkpoint();
            hole().par = par;
            changed();
        }
    });
    $('mgeHoleHouse').addEventListener('change', function () {
        checkpoint();
        if (this.checked) {
            hole().house = true;
        } else {
            delete hole().house;
        }
        changed();
    });

    // sets an input's value, unless somebody's typing in it
    function setValue(input, value) {
        if (document.activeElement !== input) {
            input.value = value;
        }
    }

    function renderPanels() {
        const h = hole();
        setValue($('mgePackId'), pack.id);
        setValue($('mgePackName'), pack.name);
        setValue($('mgePackHint'), pack.hint);
        const list = $('mgeHoles');
        list.textContent = '';
        pack.holes.forEach((ho, i) => {
            const li = document.createElement('li');
            const b = document.createElement('button');
            b.type = 'button';
            b.textContent = `${ho.name} (par ${ho.par})`;
            if (i === current) {
                b.setAttribute('aria-current', 'true');
            }
            const problems = T.check(ho, W, H);
            if (problems.length) {
                b.dataset.problems = problems.some(c => c.level === 'error') ? 'error' : 'warning';
            }
            b.addEventListener('click', () => goToHole(i));
            li.appendChild(b);
            list.appendChild(li);
        });
        setValue($('mgeHoleName'), h.name);
        setValue($('mgeHolePar'), String(h.par));
        $('mgeHoleHouse').checked = !!h.house;
        $('mgeUndo').disabled = testing || !undoStack.length;
        $('mgeRedo').disabled = testing || !redoStack.length;
        renderSelection();
        renderChecks();
        showCoords();
    }

    // ---------------------------------------------------------------- properties of the selected thing
    // per kind: [label, get, set] of its numbers
    function fields(kind, it) {
        const at = i => [() => it[i], v => {
            it[i] = v;
        }];
        const key = k => [() => it[k], v => {
            it[k] = v;
        }];
        switch (kind) {
        case 'cup':
        case 'starts':
            return [['x', ...at(0)], ['y', ...at(1)]];
        case 'sand':
        case 'water':
        case 'boosts':
            return [['x', ...at(0)], ['y', ...at(1)], ['width', ...at(2)], ['height', ...at(3)]];
        case 'bumpers':
            return [['x', ...at(0)], ['y', ...at(1)], ['radius', ...at(2)]];
        case 'sliders':
            return [['x', ...key('x')], ['y', ...key('y')], ['width', ...key('w')], ['height', ...key('h')],
                ['slides x', ...key('ax')], ['slides y', ...key('ay')], ['speed', ...key('speed'), 0.1],
                ['phase', ...key('phase'), 0.1]];
        case 'rotors':
            return [['centre x', ...key('cx')], ['centre y', ...key('cy')], ['length', ...key('len')],
                ['speed', ...key('speed'), 0.1], ['blades', ...key('blades')],
                ['door from x', () => it.door[0], v => {
                    it.door[0] = v;
                }], ['door to x', () => it.door[1], v => {
                    it.door[1] = v;
                }]];
        default:
            if (isPolygon(kind) && selectedVertex()) {
                const p = selectedVertex();
                return [['corner x', () => p[0], v => {
                    p[0] = v;
                }], ['corner y', () => p[1], v => {
                    p[1] = v;
                }]];
            }
            return [];
        }
    }

    function selectedVertex() {
        return selected && selected.v !== undefined ? item(selected)[selected.v] : null;
    }

    const DIRECTIONS = [['→ right', 1, 0], ['← left', -1, 0], ['↓ down', 0, 1], ['↑ up', 0, -1],
        ['↘', Math.SQRT1_2, Math.SQRT1_2], ['↙', -Math.SQRT1_2, Math.SQRT1_2],
        ['↗', Math.SQRT1_2, -Math.SQRT1_2], ['↖', -Math.SQRT1_2, -Math.SQRT1_2]];

    let renderedSelection = null;

    function button(text, onClick, label) {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'minigolfButton';
        b.textContent = text;
        if (label) {
            b.setAttribute('aria-label', label);
            b.title = label;
        }
        b.addEventListener('click', onClick);
        return b;
    }

    function renderSelection() {
        const box = $('mgeSelection');
        const key = selected ? `${selected.kind}/${selected.i}/${selected.v}/${current}` : '';
        if (key === renderedSelection) {
            // the same thing, just update its numbers
            box.querySelectorAll('input[data-field]').forEach((input, n) => {
                const f = fields(selected.kind, item(selected))[n];
                if (f) {
                    setValue(input, String(Math.round(f[1]() * 1000) / 1000));
                }
            });
            const dir = box.querySelector('select');
            if (dir) {
                dir.value = String(directionIndex(item(selected)));
            }
            return;
        }
        renderedSelection = key;
        box.textContent = '';
        if (!selected) {
            box.appendChild(Object.assign(document.createElement('p'), {className: 'minigolfHint',
                textContent: 'Nothing. Click something on the course.'}));
            return;
        }
        const it = item(selected);
        const title = document.createElement('p');
        title.className = 'mgeSelectedName';
        title.textContent = describe(selected);
        box.appendChild(title);
        if (selected.kind === 'starts' && hole().starts.length > 1) {
            const n = hole().starts.length;
            const seats = [];
            for (let s = selected.i; s < 8; s += n) {
                seats.push(s + 1);
            }
            box.appendChild(Object.assign(document.createElement('p'), {className: 'minigolfHint',
                textContent: `Player ${seats.filter(s => s <= 4).join(', ')} tees off here.`}));
        }
        if (isPolygon(selected.kind) && selected.v === undefined) {
            box.appendChild(Object.assign(document.createElement('p'), {className: 'minigolfHint',
                textContent: `${it.length} corners. Drag a corner, or a midpoint for a new corner. `
                    + 'Click a corner to edit it, Del removes it.'}));
        }
        const grid = document.createElement('div');
        grid.className = 'mgeFields';
        fields(selected.kind, it).forEach(([label, get, set, step]) => {
            const id = `mgeField_${label.replace(/\W+/g, '_')}`;
            const l = document.createElement('label');
            l.htmlFor = id;
            l.textContent = label;
            const input = document.createElement('input');
            input.type = 'number';
            input.id = id;
            input.step = String(step || 1);
            input.dataset.field = label;
            input.value = String(Math.round(get() * 1000) / 1000);
            input.addEventListener('change', function () {
                const v = parseFloat(this.value);
                if (!Number.isFinite(v)) {
                    return;
                }
                checkpoint();
                set(v);
                if (selected.kind === 'rotors') {
                    item(selected).door.sort((a, b) => a - b);
                }
                changed();
            });
            grid.append(l, input);
        });
        if (selected.kind === 'boosts') {
            const l = document.createElement('label');
            l.htmlFor = 'mgeBoostDirection';
            l.textContent = 'pushes';
            const select = document.createElement('select');
            select.id = 'mgeBoostDirection';
            DIRECTIONS.forEach(([name], i) => select.appendChild(new Option(name, String(i))));
            select.value = String(directionIndex(it));
            select.addEventListener('change', function () {
                const d = DIRECTIONS[parseInt(this.value, 10)];
                checkpoint();
                item(selected)[4] = d[1];
                item(selected)[5] = d[2];
                changed();
            });
            grid.append(l, select);
        }
        box.appendChild(grid);

        const actions = document.createElement('p');
        actions.className = 'mgeRow';
        if (selected.kind !== 'outline' && selected.kind !== 'cup') {
            actions.append(
                button('Mirror ↔', () => mirrorSelected(['mirrored left to right']), 'Mirror copy left to right'),
                button('Mirror ↕', () => mirrorSelected(['mirrored top to bottom']), 'Mirror copy top to bottom'),
                button('Turn 180°', () => mirrorSelected(['turned half way round']), 'Copy turned half way round'),
                button('All 4', () => mirrorSelected(['turned half way round', 'mirrored left to right',
                    'mirrored top to bottom']), 'Copies all four ways round'),
                button('Duplicate', duplicateSelected),
                button('Delete', removeSelected));
        } else if (selectedVertex() && item(selected).length > 3) {
            actions.append(button('Delete corner', removeSelected));
        }
        box.appendChild(actions);
    }

    function directionIndex(boost) {
        let best = 0;
        DIRECTIONS.forEach((d, i) => {
            if (d[1] * boost[4] + d[2] * boost[5] > DIRECTIONS[best][1] * boost[4] + DIRECTIONS[best][2] * boost[5]) {
                best = i;
            }
        });
        return best;
    }

    function renderChecks() {
        const ul = $('mgeChecks');
        ul.textContent = '';
        const problems = T.check(hole(), W, H);
        if (!problems.length) {
            const li = document.createElement('li');
            li.className = 'ok';
            li.textContent = hole().starts.length > 1 ? 'All good, every tee is as good as the others.' : 'All good.';
            ul.appendChild(li);
        }
        problems.forEach(c => {
            const li = document.createElement('li');
            li.className = c.level;
            li.textContent = c.text;
            ul.appendChild(li);
        });
        // and for the pack: the server knows how many holes its packs have
        const known = SERVER_COURSES[pack.id];
        $('mgePackNote').textContent = known && known.holes !== pack.holes.length
            ? `The server expects ${known.holes} holes in ${known.name}, this pack has ${pack.holes.length}: `
                + 'change it in COURSES in lol9k1/minigolf.py too.'
            : '';
    }

    // ---------------------------------------------------------------- export & import
    function exportText(text, what) {
        const area = $('mgeExportText');
        area.value = text;
        const message = $('mgeExportMessage');
        const done = () => {
            message.textContent = `Copied ${what} to the clipboard.`;
        };
        const manual = () => {
            area.focus();
            area.select();
            message.textContent = `Here's ${what}, copy it from below.`;
        };
        try {
            navigator.clipboard.writeText(text).then(done, manual);
        } catch (e) {
            manual();
        }
    }

    $('mgeExportHole').addEventListener('click', () => exportText(T.holeCode(hole()), 'the hole'));
    $('mgeExportPack').addEventListener('click', () => exportText(T.packCode(pack), 'the pack'));
    $('mgeImport').addEventListener('click', function () {
        const message = $('mgeImportMessage');
        let holes;
        try {
            holes = T.importHoles($('mgeImportText').value);
        } catch (e) {
            message.textContent = `Couldn't import that: ${e.message}.`;
            return;
        }
        checkpoint();
        pack.holes.splice(current + 1, 0, ...holes);
        current += 1;
        selected = null;
        changed();
        message.textContent = holes.length === 1 ? 'Imported 1 hole.' : `Imported ${holes.length} holes.`;
    });

    // ---------------------------------------------------------------- drawing
    function drawGrid() {
        if (!$('mgeGrid').checked) {
            return;
        }
        const step = snapSize >= 10 ? snapSize : 10;
        for (let x = 0; x <= W; x += step) {
            ctx.fillStyle = x % 100 === 0 ? 'rgba(255,255,255,0.22)' : 'rgba(255,255,255,0.07)';
            ctx.fillRect(x - 0.5, 0, 1, H);
        }
        for (let y = 0; y <= H; y += step) {
            ctx.fillStyle = y % 100 === 0 ? 'rgba(255,255,255,0.22)' : 'rgba(255,255,255,0.07)';
            ctx.fillRect(0, y - 0.5, W, 1);
        }
    }

    function drawAxes() {
        if (!$('mgeAxes').checked) {
            return;
        }
        ctx.save();
        ctx.setLineDash([8, 6]);
        ctx.strokeStyle = 'rgba(255,235,59,0.8)';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(CX, 0);
        ctx.lineTo(CX, H);
        ctx.moveTo(0, CY);
        ctx.lineTo(W, CY);
        // the square a quarter turn keeps on the canvas
        ctx.rect(CX - CY, 0, 2 * CY, H);
        ctx.stroke();
        ctx.restore();
    }

    function polyPath(poly) {
        ctx.beginPath();
        poly.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
        ctx.closePath();
    }

    // the outline of a thing, to show it's selected or under the pointer
    function outlineOf(sel) {
        const it = item(sel);
        if (isPolygon(sel.kind)) {
            polyPath(it);
        } else if (RECTS.includes(sel.kind) || sel.kind === 'sliders') {
            const r = rectOf(sel.kind, it);
            ctx.beginPath();
            ctx.rect(r.x, r.y, r.w, r.h);
        } else if (sel.kind === 'bumpers') {
            ctx.beginPath();
            ctx.arc(it[0], it[1], it[2] + 2, 0, Math.PI * 2);
        } else if (sel.kind === 'rotors') {
            ctx.beginPath();
            ctx.arc(it.cx, it.cy, it.len, 0, Math.PI * 2);
        } else if (sel.kind === 'starts') {
            ctx.beginPath();
            ctx.rect(it[0] - TEE - 2, it[1] - TEE - 2, 2 * TEE + 4, 2 * TEE + 4);
        } else if (sel.kind === 'cup') {
            ctx.beginPath();
            ctx.arc(it[0], it[1], T.CUP_R + 4, 0, Math.PI * 2);
        }
    }

    function drawHelpers() {
        const h = hole();
        ctx.save();
        // where the sliders slide, from one end to the other
        ctx.setLineDash([4, 4]);
        ctx.lineWidth = 1;
        h.sliders.forEach(s => {
            ctx.strokeStyle = 'rgba(255,152,0,0.9)';
            ctx.strokeRect(s.x, s.y, s.w, s.h);
            ctx.strokeRect(s.x + s.ax, s.y + s.ay, s.w, s.h);
            ctx.beginPath();
            ctx.moveTo(s.x + s.w / 2, s.y + s.h / 2);
            ctx.lineTo(s.x + s.ax + s.w / 2, s.y + s.ay + s.h / 2);
            ctx.stroke();
        });
        // windmill blades only hit balls between their doors
        h.rotors.forEach(r => {
            ctx.strokeStyle = 'rgba(255,255,255,0.6)';
            ctx.beginPath();
            ctx.arc(r.cx, r.cy, r.len, 0, Math.PI * 2);
            ctx.stroke();
            ctx.strokeStyle = 'rgba(255,235,59,0.9)';
            r.door.forEach(x => {
                ctx.beginPath();
                ctx.moveTo(x, r.cy - r.len);
                ctx.lineTo(x, r.cy + r.len + 10);
                ctx.stroke();
            });
        });
        ctx.restore();
        // tee numbers, which player tees off where
        if (h.starts.length > 1) {
            ctx.font = 'bold 11px Verdana, sans-serif';
            ctx.textAlign = 'center';
            h.starts.forEach((t, i) => {
                ctx.fillStyle = 'rgba(0,0,0,0.6)';
                ctx.fillRect(t[0] - 7, t[1] - TEE - 15, 14, 13);
                ctx.fillStyle = '#fff';
                ctx.fillText(String(i + 1), t[0], t[1] - TEE - 5);
            });
            ctx.textAlign = 'left';
        }
    }

    function drawSelection() {
        if (hover && !hover.handle && !sameThing(hover, selected) && !drag) {
            outlineOf(hover);
            ctx.strokeStyle = 'rgba(255,255,255,0.7)';
            ctx.lineWidth = 1.5 / scale();
            ctx.stroke();
        }
        if (!selected) {
            return;
        }
        outlineOf(selected);
        ctx.strokeStyle = '#ffeb3b';
        ctx.lineWidth = 2 / scale();
        ctx.stroke();
        const hs = handleSize();
        handles(selected).forEach(hd => {
            const active = hd.action === 'vertex' && selected.v === hd.v;
            ctx.fillStyle = active ? '#ffeb3b' : '#fff';
            ctx.strokeStyle = '#000';
            ctx.lineWidth = 1 / scale();
            ctx.beginPath();
            if (hd.round || hd.small) {
                ctx.arc(hd.x, hd.y, hd.small ? hs * 0.7 : hs, 0, Math.PI * 2);
            } else {
                ctx.rect(hd.x - hs, hd.y - hs, 2 * hs, 2 * hs);
            }
            if (hd.small) {
                ctx.globalAlpha = 0.7;
            }
            ctx.fill();
            ctx.stroke();
            ctx.globalAlpha = 1;
        });
    }

    function draw() {
        if (!overlay.hidden) {
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
            ctx.clearRect(0, 0, W, H);
            drawGrid();
            drawAxes();
            drawHelpers();
            drawSelection();
            if (tool !== 'select' && pointer) {
                const [x, y] = snapPoint(pointer);
                ctx.fillStyle = 'rgba(255,235,59,0.9)';
                ctx.beginPath();
                ctx.arc(x, y, 3, 0, Math.PI * 2);
                ctx.fill();
            }
        }
        requestAnimationFrame(draw);
    }

    // ---------------------------------------------------------------- go
    (function start() {
        let restored = false;
        try {
            const saved = localStorage.getItem(STORAGE_KEY);
            if (saved) {
                restore(saved);
                pack.holes = pack.holes.map(T.normalize);
                restored = pack.holes.length > 0;
            }
        } catch (e) { /* storage blocked or garbage in it */ }
        if (!restored) {
            loadPack($('minigolf').dataset.course);
        }
        if (PACKS[pack.id]) {
            $('mgeLoadPack').value = pack.id;
        }
    })();
    setTool('select');
    game.preview(T.toDef(hole()));
    renderPanels();
    // for tests and the browser console
    window.lol9k1MinigolfEditor = {
        get pack() {
            return T.clone(pack);
        },
        get current() {
            return current;
        },
        get selected() {
            return selected && T.clone(selected);
        },
    };
    requestAnimationFrame(draw);
})();
