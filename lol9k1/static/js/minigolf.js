/*
 * LOL 9001 Minigolf: a tiny top down minigolf game for the downtime between matches.
 * Hot seat for 1-4 players, the logged-in player's rounds go to the leaderboard. Or across the network,
 * every registered player on their own computer, and everybody's rounds go to the leaderboard.
 * No dependencies, just a canvas.
 *
 * lol9k1's own scripts usually live inline in the templates. The game is a file of its own
 * because it's too big for that, static/js otherwise only holds vendored libraries.
 */

/*
 * The rules that don't depend on the game's state, as plain functions.
 */
window.lol9k1MinigolfRules = (function () {
    'use strict';

    const CUP_PULL = 2600;          // px/s² the cup pulls at a ball that's too fast to drop

    return {
        /**
         * The places (0 = first) of the players with these totals. Tied players share
         * a place and the next one after them skips ahead: [27, 27, 36] -> [0, 0, 2].
         */
        places(totals) {
            return totals.map(t => totals.filter(other => other < t).length);
        },

        /**
         * Where a ball goes back to after a splash or after being knocked into the cup. The shooter's ball
         * goes back to where it was putted from. Anybody else's goes back to where it lay before this shot.
         */
        returnSpot(ball, isShooter) {
            return isShooter ? {x: ball.lastX, y: ball.lastY} : {x: ball.shotX, y: ball.shotY};
        },

        /**
         * How a ball too fast to drop is pulled towards the centre of the cup, as a velocity change.
         * (dx, dy) points from the ball to the centre. Dead centre there is no direction to pull in.
         */
        cupPull(dx, dy, dt) {
            const d = Math.sqrt(dx * dx + dy * dy);
            if (d <= 1e-6) {
                return {vx: 0, vy: 0};
            }
            return {vx: dx / d * CUP_PULL * dt, vy: dy / d * CUP_PULL * dt};
        },
    };
})();

(function () {
    'use strict';

    const root = document.getElementById('minigolf');
    if (!root) {
        return;
    }
    const rules = window.lol9k1MinigolfRules;

    // ---------------------------------------------------------------- constants
    // the course is as big as the canvas is in the page
    const W = document.getElementById('minigolfCanvas').width;
    const H = document.getElementById('minigolfCanvas').height;
    const BALL_R = 6;
    const WALL_R = BALL_R + 4;      // walls are drawn 8px thick
    const CUP_R = 10;
    const MAX_STROKES = parseInt(root.dataset.maxStrokes, 10) || 10;
    const MAX_DRAG = 130;           // px of pull for a full power shot
    const MAX_SPEED = 950;          // px/s
    const DT = 1 / 240;             // physics step
    const RESTITUTION = 0.75;
    const DRAG = 0.9;               // exponential slow down per second
    const ROLL = 80;                // constant rolling resistance px/s²
    const SAND_DRAG = 3.5, SAND_ROLL = 420;
    const BOOST_ACC = 1100;
    const STOP_SPEED = 7;
    const SINK_SPEED = 430;         // faster than this and the ball lips out
    const BUMPER_KICK = 240;        // px/s a bumper adds to a ball bouncing off it
    const COLORS = ['#ffffff', '#ffeb3b', '#ff7043', '#4fc3f7'];

    // ---------------------------------------------------------------- course
    function rect(x, y, w, h) {
        return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]];
    }

    // A hole has an outline (the outer wall) and a tee, either one start for everybody or starts, one per
    // seat (player 1, 2, ...), so the players come at the cup from different sides and run into each other.
    // In it: blocks (walls), sand and water and boosts (rects, a boost with its direction), rotors (windmill
    // blades), sliders (moving walls) and bumpers ([x, y, radius], they kick a ball away).
    const CLASSIC = [
        {
            name: 'Warm-up', par: 2,
            outline: rect(60, 140, 520, 120),
            start: [110, 200], cup: [530, 200],
        },
        {
            name: 'Dogleg', par: 3,
            outline: [[60, 240], [440, 240], [440, 40], [580, 40], [580, 360], [60, 360]],
            blocks: [[[580, 280], [580, 360], [500, 360]]],
            start: [110, 300], cup: [510, 90],
        },
        {
            name: 'Pinball', par: 3,
            outline: rect(40, 60, 560, 280),
            blocks: [
                [[320, 160], [360, 200], [320, 240], [280, 200]],
                rect(185, 105, 30, 30), rect(185, 265, 30, 30),
                rect(425, 105, 30, 30), rect(425, 265, 30, 30),
            ],
            start: [90, 200], cup: [550, 200],
        },
        {
            name: 'Beach Day', par: 3,
            outline: [[60, 80], [580, 80], [580, 320], [60, 320]],
            sand: [[230, 130, 180, 140], [500, 80, 80, 70]],
            start: [100, 200], cup: [540, 200],
        },
        {
            name: 'Bridge Over Troubled Water', par: 3,
            outline: rect(40, 60, 560, 280),
            water: [[220, 60, 200, 110], [220, 230, 200, 110]],
            start: [90, 200], cup: [550, 110],
        },
        {
            name: 'Windmill', par: 3,
            outline: rect(60, 120, 520, 160),
            blocks: [rect(300, 120, 40, 50), rect(300, 230, 40, 50)],
            // the blades sweep high above the lanes and only reach down to the door
            rotors: [{cx: 320, cy: 145, len: 90, speed: 1.3, blades: 3, door: [300, 340]}],
            house: true,
            start: [110, 200], cup: [530, 200],
        },
        {
            name: 'Turbo U-Turn', par: 3,
            outline: [[60, 40], [580, 40], [580, 360], [60, 360], [60, 240], [440, 240], [440, 160], [60, 160]],
            boosts: [[250, 70, 100, 60, 1, 0], [470, 170, 80, 60, 0, 1], [250, 270, 100, 60, -1, 0]],
            start: [100, 100], cup: [100, 300],
        },
        {
            name: 'Traffic', par: 3,
            outline: rect(60, 100, 520, 200),
            sliders: [
                {x: 230, y: 124, w: 26, h: 60, ax: 0, ay: 92, speed: 1.6, phase: 0},
                {x: 384, y: 216, w: 26, h: 60, ax: 0, ay: -92, speed: 1.6, phase: 1.3},
            ],
            start: [100, 200], cup: [540, 200],
        },
        {
            name: 'Grand Finale', par: 4,
            outline: rect(40, 40, 560, 320),
            blocks: [rect(200, 40, 20, 220), rect(400, 140, 20, 220)],
            water: [[300, 300, 100, 60]],
            sand: [[440, 40, 160, 50]],
            boosts: [[240, 160, 60, 60, 0, -1]],
            start: [100, 100], cup: [510, 300],
        },
    ];

    // Everybody tees off from a side of their own and aims at the same cup, in the middle of things.
    // Knocking somebody into the water costs them a stroke, and a ball in the way is there to be cleared.
    // Seats 0 and 1 tee off opposite each other, so a game of two is a duel too.
    const BRAWL = [
        {
            name: 'Crossroads', par: 2,
            outline: [[140, 150], [270, 150], [270, 20], [370, 20], [370, 150], [500, 150], [500, 250],
                [370, 250], [370, 380], [270, 380], [270, 250], [140, 250]],
            starts: [[175, 200], [465, 200], [320, 55], [320, 345]], cup: [320, 200],
        },
        {
            name: 'Pocket Pool', par: 2,
            outline: rect(40, 60, 560, 280),
            // the pockets: corners and the middle of the long sides
            water: [[40, 60, 40, 40], [560, 60, 40, 40], [40, 300, 40, 40], [560, 300, 40, 40],
                [300, 60, 40, 26], [300, 314, 40, 26]],
            starts: [[100, 200], [540, 200], [200, 130], [440, 270]], cup: [320, 200],
        },
        {
            name: 'Pinball Wizard', par: 3,
            outline: rect(40, 60, 560, 280),
            bumpers: [[265, 200, 12], [375, 200, 12], [320, 140, 16], [320, 260, 16],
                [180, 120, 10], [460, 280, 10], [180, 280, 10], [460, 120, 10]],
            starts: [[80, 200], [560, 200], [80, 110], [560, 290]], cup: [320, 200],
        },
        {
            name: 'Walk the Plank', par: 3,
            outline: rect(40, 60, 560, 280),
            // planks from both sides lead to a tiny island with the cup
            water: [[180, 60, 280, 110], [180, 230, 280, 110],
                [180, 170, 110, 12], [180, 218, 110, 12], [350, 170, 110, 12], [350, 218, 110, 12]],
            starts: [[90, 200], [550, 200], [90, 120], [550, 280]], cup: [320, 200],
        },
        {
            name: 'Roundabout', par: 3,
            outline: rect(40, 40, 560, 320),
            blocks: [rect(180, 140, 280, 120)],
            bumpers: [[230, 90, 11], [410, 90, 11]],
            starts: [[110, 200], [530, 200], [110, 310], [530, 310]], cup: [320, 90],
        },
        {
            name: 'Bottleneck', par: 3,
            outline: rect(40, 60, 560, 280),
            // a funnel down to a gate just wide enough for one ball
            blocks: [[[300, 60], [390, 60], [390, 183]], [[300, 340], [390, 217], [390, 340]],
                rect(390, 60, 20, 123), rect(390, 217, 20, 123)],
            water: [[560, 60, 40, 280]],
            starts: [[90, 120], [90, 280], [90, 200], [160, 200]], cup: [500, 200],
        },
        {
            name: 'Sumo', par: 3,
            outline: rect(40, 40, 560, 320),
            // an island ring in a moat, two narrow bridges lead onto it
            water: [[140, 40, 360, 70], [140, 290, 360, 70],
                [140, 110, 60, 72], [140, 218, 60, 72], [440, 110, 60, 72], [440, 218, 60, 72]],
            bumpers: [[320, 150, 12], [320, 250, 12]],
            starts: [[80, 200], [560, 200], [80, 80], [560, 320]], cup: [320, 200],
        },
        {
            name: 'Head-On', par: 3,
            outline: [[30, 170], [260, 170], [260, 110], [380, 110], [380, 170], [610, 170], [610, 230],
                [380, 230], [380, 290], [260, 290], [260, 230], [30, 230]],
            water: [[260, 110, 30, 30], [350, 110, 30, 30], [260, 260, 30, 30], [350, 260, 30, 30]],
            sliders: [
                {x: 170, y: 174, w: 16, h: 20, ax: 0, ay: 32, speed: 1.4, phase: 0},
                {x: 454, y: 206, w: 16, h: 20, ax: 0, ay: -32, speed: 1.4, phase: 0},
            ],
            starts: [[60, 200], [580, 200], [100, 200], [540, 200]], cup: [320, 200],
        },
        {
            name: 'Mayhem', par: 3,
            outline: rect(40, 40, 560, 320),
            water: [[300, 40, 40, 30], [300, 330, 40, 30], [40, 180, 30, 40], [570, 180, 30, 40]],
            sand: [[150, 100, 60, 40], [430, 260, 60, 40], [430, 100, 60, 40], [150, 260, 60, 40]],
            bumpers: [[320, 135, 13], [320, 265, 13], [245, 200, 13], [395, 200, 13]],
            starts: [[90, 90], [550, 310], [550, 90], [90, 310]], cup: [320, 200],
        },
    ];

    const PACKS = {
        classic: {holes: CLASSIC, hint: 'Nine classic holes, everybody tees off from the same spot.'},
        brawl: {holes: BRAWL,
            hint: 'Everybody tees off from a different side and goes for the same cup. '
                + 'Bump the others out of the way, knock them into the water, mind the bumpers!'},
    };

    // the map packs as the server knows them, by id: {name, holes}
    const SERVER_COURSES = JSON.parse(root.dataset.courses || '{}');
    let course = null;      // the map pack being played, an id of PACKS
    let HOLES = null;       // its holes

    // The server validates rounds against its own number of holes. Returns why a pack can't be played.
    function courseMismatch(id) {
        const known = SERVER_COURSES[id];
        if (!PACKS[id] || !known) {
            return `This page doesn't know the map pack "${id}". Reload it, maybe?`;
        }
        if (known.holes !== PACKS[id].holes.length) {
            return `${known.name} has ${PACKS[id].holes.length} holes, but the server expects ${known.holes}. Rounds can't be saved.`;
        }
        return null;
    }

    function courseName(id) {
        return SERVER_COURSES[id] ? SERVER_COURSES[id].name : id;
    }

    function usePack(id) {
        course = id;
        HOLES = PACKS[id] ? PACKS[id].holes : CLASSIC;
    }

    // ---------------------------------------------------------------- dom
    const canvas = document.getElementById('minigolfCanvas');
    const ctx = canvas.getContext('2d');
    const setup = document.getElementById('minigolfSetup');
    const playerList = document.getElementById('minigolfPlayers');
    const result = document.getElementById('minigolfResult');
    const statusLine = document.getElementById('minigolfStatus');
    const scorecard = document.getElementById('minigolfScorecard');
    const soundButton = document.getElementById('minigolfSound');
    const me = root.dataset.player || 'You';

    function el(tag, text, className) {
        const e = document.createElement(tag);
        if (text !== undefined) {
            e.textContent = text;
        }
        if (className) {
            e.className = className;
        }
        return e;
    }

    // crisp rendering on high dpi screens
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = W * dpr;
    canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    // ---------------------------------------------------------------- sound
    let audio = null;
    let soundOn = true;
    try {
        soundOn = localStorage.getItem('minigolfSound') !== 'off';
    } catch (e) { /* storage blocked */ }

    function updateSoundButton() {
        soundButton.textContent = soundOn ? '🔊 Sound' : '🔇 Muted';
        soundButton.setAttribute('aria-pressed', String(soundOn));
    }

    soundButton.addEventListener('click', function () {
        soundOn = !soundOn;
        try {
            localStorage.setItem('minigolfSound', soundOn ? 'on' : 'off');
        } catch (e) { /* storage blocked */ }
        updateSoundButton();
    });
    updateSoundButton();

    function beep(freq, duration, type, volume, slideTo) {
        if (!soundOn) {
            return;
        }
        try {
            audio = audio || new (window.AudioContext || window.webkitAudioContext)();
            const t = audio.currentTime;
            const osc = audio.createOscillator();
            const gain = audio.createGain();
            osc.type = type || 'square';
            osc.frequency.setValueAtTime(freq, t);
            if (slideTo) {
                osc.frequency.exponentialRampToValueAtTime(slideTo, t + duration);
            }
            gain.gain.setValueAtTime(volume || 0.08, t);
            gain.gain.exponentialRampToValueAtTime(0.0001, t + duration);
            osc.connect(gain).connect(audio.destination);
            osc.start(t);
            osc.stop(t + duration);
        } catch (e) { /* no audio, no problem */ }
    }

    const sfx = {
        putt: (power) => beep(220 + power * 300, 0.08, 'square', 0.06),
        bonk: (speed) => beep(140 + Math.min(speed, 800) / 4, 0.05, 'triangle', Math.min(0.12, speed / 4000)),
        clack: () => beep(900, 0.04, 'square', 0.05),
        cup: () => {
            beep(660, 0.12, 'square', 0.06);
            setTimeout(() => beep(880, 0.12, 'square', 0.06), 110);
            setTimeout(() => beep(1320, 0.25, 'square', 0.06), 220);
        },
        ace: () => [523, 659, 784, 1047, 784, 1047].forEach((f, i) => setTimeout(() => beep(f, 0.14, 'square', 0.07), i * 110)),
        splash: () => beep(500, 0.4, 'sawtooth', 0.05, 60),
        boing: () => beep(320, 0.12, 'sine', 0.09, 900),
    };

    // ---------------------------------------------------------------- geometry helpers
    function segments(poly) {
        const segs = [];
        for (let i = 0; i < poly.length; i++) {
            const a = poly[i], b = poly[(i + 1) % poly.length];
            segs.push([a[0], a[1], b[0], b[1]]);
        }
        return segs;
    }

    function inRect(x, y, r) {
        return x >= r[0] && x <= r[0] + r[2] && y >= r[1] && y <= r[1] + r[3];
    }

    // Pushes the ball out of segment a-b (moving with velocity wv) and bounces it off.
    // Returns the speed of the impact, 0 if there was none.
    function collideSegment(ball, ax, ay, bx, by, radius, wvx, wvy) {
        const abx = bx - ax, aby = by - ay;
        const len2 = abx * abx + aby * aby;
        let t = len2 ? ((ball.x - ax) * abx + (ball.y - ay) * aby) / len2 : 0;
        t = Math.max(0, Math.min(1, t));
        const qx = ax + abx * t, qy = ay + aby * t;
        const dx = ball.x - qx, dy = ball.y - qy;
        const d2 = dx * dx + dy * dy;
        if (d2 >= radius * radius) {
            return 0;
        }
        const d = Math.sqrt(d2);
        let nx, ny;
        if (d > 1e-6) {
            nx = dx / d;
            ny = dy / d;
        } else {
            const len = Math.sqrt(len2) || 1;
            nx = -aby / len;
            ny = abx / len;
        }
        ball.x += nx * (radius - d);
        ball.y += ny * (radius - d);
        const rvx = ball.vx - wvx, rvy = ball.vy - wvy;
        const vn = rvx * nx + rvy * ny;
        if (vn >= 0) {
            return 0;
        }
        ball.vx -= (1 + RESTITUTION) * vn * nx;
        ball.vy -= (1 + RESTITUTION) * vn * ny;
        ball.moving = true;
        return -vn;
    }

    // ---------------------------------------------------------------- game state
    let players = [];        // {name, isMe, left, color, scores: [], ball}
    let holeIndex = 0;
    let hole = null;         // HOLES[holeIndex] plus precomputed segments
    let turn = 0;            // index into players
    let state = 'setup';     // setup | aim | rolling | between | finished
    let time = 0;            // course clock, drives moving obstacles
    let banner = null;       // {text, sub, until}
    let aim = null;          // {sx, sy, x, y} pointer drag in course coordinates
    let effects = [];        // splashes and sparkles
    let order = [];          // tee order on the current hole
    // A network game, null when playing hot seat. Its moves are replayed in order, net.seq is the next one.
    // See lol9k1/minigolf.py for how a game is kept in sync.
    let net = null;          // {id, seq, latest, epoch, posting, started, replaying, lastShot, pollTimer}

    function prepareHole(def) {
        const h = Object.assign({blocks: [], sand: [], water: [], boosts: [], rotors: [], sliders: [], bumpers: []}, def);
        h.starts = h.starts || [h.start];
        h.flash = h.bumpers.map(() => -1); // course time a bumper was last hit
        h.walls = segments(h.outline);
        h.blocks.forEach(b => h.walls.push(...segments(b)));
        return h;
    }

    function newBall() {
        // lastX/Y: where its player last putted it from. shotX/Y: where it lay when the current shot began.
        return {x: 0, y: 0, vx: 0, vy: 0, lastX: 0, lastY: 0, shotX: 0, shotY: 0, penalized: false,
            onCourse: false, sunk: false, out: false,
            strokes: 0, moving: false, sinkAnim: 0};
    }

    // where the player in this seat tees off
    function teeOf(seat) {
        return hole.starts[seat % hole.starts.length];
    }

    // Bounces the ball off a round bumper, which kicks it away. Returns the speed of the impact, 0 if none.
    function collideBumper(ball, bumper, index) {
        const dx = ball.x - bumper[0], dy = ball.y - bumper[1];
        const reach = bumper[2] + BALL_R;
        const d2 = dx * dx + dy * dy;
        if (d2 >= reach * reach) {
            return 0;
        }
        const d = Math.sqrt(d2);
        const nx = d > 1e-6 ? dx / d : 1, ny = d > 1e-6 ? dy / d : 0;
        ball.x = bumper[0] + nx * reach;
        ball.y = bumper[1] + ny * reach;
        const vn = ball.vx * nx + ball.vy * ny;
        if (vn >= 0) {
            return 0;
        }
        // out as fast as it came in, plus the kick
        const out = Math.min(MAX_SPEED, -vn + BUMPER_KICK);
        ball.vx += (out - vn) * nx;
        ball.vy += (out - vn) * ny;
        ball.moving = true;
        hole.flash[index] = time;
        return -vn;
    }

    function sliderOffset(s, t) {
        const k = Math.sin(t * s.speed + s.phase) * 0.5 + 0.5;
        const dk = Math.cos(t * s.speed + s.phase) * 0.5 * s.speed;
        return {x: s.ax * k, y: s.ay * k, vx: s.ax * dk, vy: s.ay * dk};
    }

    function rotorBlades(r, t) {
        const blades = [];
        for (let i = 0; i < r.blades; i++) {
            const a = t * r.speed + i * Math.PI * 2 / r.blades;
            blades.push([r.cx, r.cy, r.cx + Math.cos(a) * r.len, r.cy + Math.sin(a) * r.len]);
        }
        return blades;
    }

    function startHole(index) {
        holeIndex = index;
        hole = prepareHole(HOLES[index]);
        time = 0;
        effects = [];
        players.forEach(p => {
            p.ball = newBall();
        });
        order = honourOrder(index);
        turn = order.find(i => !players[i].left);
        banner = {text: `Hole ${index + 1}: ${hole.name}`, sub: `Par ${hole.par}`, until: performance.now() + 2200};
        beginTurn();
        renderScorecard();
    }

    // honours: best score on the previous hole tees off first
    function honourOrder(index) {
        const o = players.map((p, i) => i);
        if (index > 0) {
            o.sort((a, b) => players[a].scores[index - 1] - players[b].scores[index - 1] || a - b);
        }
        return o;
    }

    function beginTurn() {
        const p = players[turn];
        if (!p.ball.onCourse) {
            const tee = teeOf(turn);
            p.ball.onCourse = true;
            p.ball.x = p.ball.lastX = tee[0];
            p.ball.y = p.ball.lastY = tee[1];
        }
        state = 'aim';
        aim = null;
        if (myTurn()) {
            setStatus(`${p.name}, it's your turn! Stroke ${p.ball.strokes + 1}.`);
        } else {
            setStatus(`Waiting for ${p.name} to putt... (stroke ${p.ball.strokes + 1})`);
        }
    }

    // in a network game only the player at this computer may putt
    function myTurn() {
        return !net || players[turn].isMe;
    }

    // and not before the server has their last shot
    function canPutt() {
        return myTurn() && !(net && net.posting);
    }

    function setStatus(text) {
        statusLine.textContent = text;
    }

    function shoot(power, dirX, dirY) {
        const p = players[turn];
        const b = p.ball;
        players.forEach(other => {
            other.ball.shotX = other.ball.x;
            other.ball.shotY = other.ball.y;
            other.ball.penalized = false;
        });
        b.lastX = b.x;
        b.lastY = b.y;
        b.vx = dirX * power * MAX_SPEED;
        b.vy = dirY * power * MAX_SPEED;
        b.moving = true;
        b.strokes += 1;
        state = 'rolling';
        if (net) {
            net.lastShot = {power, dx: dirX, dy: dirY, time};
        }
        sfx.putt(power);
        setStatus(`${p.name} putts... (stroke ${b.strokes})`);
        renderScorecard();
    }

    function anythingMoving() {
        return players.some(p => p.ball.onCourse && !p.ball.sunk && !p.ball.out && p.ball.moving)
            || players.some(p => p.ball.sinkAnim > 0 && p.ball.sinkAnim < 1);
    }

    function endOfShot() {
        const p = players[turn];
        const b = p.ball;
        const replayed = net && net.replaying;
        if (replayed) {
            // the shooter's browser has the last word on where the balls ended up
            net.replaying = null;
            takeBalls(replayed.balls);
        }
        if (!b.sunk && b.strokes >= MAX_STROKES) {
            b.out = true;
            b.strokes = MAX_STROKES;
            banner = {text: `${p.name}: ${MAX_STROKES} strokes`, sub: 'Pick it up, buddy.', until: performance.now() + 1500};
        }
        renderScorecard();
        if (net && !replayed) {
            postShot();
        }
        // next player in honour order who still has to play
        const at = order.indexOf(turn);
        for (let i = 1; i <= order.length; i++) {
            const candidate = order[(at + i) % order.length];
            const cb = players[candidate].ball;
            if (!cb.sunk && !cb.out && !players[candidate].left) {
                turn = candidate;
                beginTurn();
                return;
            }
        }
        finishHole();
    }

    function finishHole() {
        players.forEach(p => {
            p.scores[holeIndex] = Math.min(p.ball.strokes, MAX_STROKES);
        });
        renderScorecard();
        state = 'between';
        const last = holeIndex === HOLES.length - 1;
        setTimeout(() => {
            if (state !== 'between') {
                return; // left the game in the meantime
            }
            if (last) {
                finishRound();
            } else {
                startHole(holeIndex + 1);
            }
        }, 1600);
    }

    // ---------------------------------------------------------------- physics
    function step(dt) {
        time += dt;
        const balls = players.map(p => p.ball).filter(b => b.onCourse && !b.sunk && !b.out);

        balls.forEach(b => {
            if (b.moving) {
                b.x += b.vx * dt;
                b.y += b.vy * dt;
            }
            let impact = 0;
            for (let k = 0; k < 2; k++) {
                hole.walls.forEach(s => {
                    impact = Math.max(impact, collideSegment(b, s[0], s[1], s[2], s[3], WALL_R, 0, 0));
                });
            }
            hole.rotors.forEach(r => {
                if (b.x < r.door[0] - BALL_R || b.x > r.door[1] + BALL_R) {
                    return;
                }
                // velocity of the blade at the point closest to the ball
                const rx = b.x - r.cx, ry = b.y - r.cy;
                rotorBlades(r, time).forEach(e => {
                    impact = Math.max(impact, collideSegment(b, e[0], e[1], e[2], e[3], BALL_R + 3,
                        -r.speed * ry, r.speed * rx));
                });
            });
            hole.sliders.forEach(s => {
                const o = sliderOffset(s, time);
                segments(rect(s.x + o.x, s.y + o.y, s.w, s.h)).forEach(seg => {
                    impact = Math.max(impact, collideSegment(b, seg[0], seg[1], seg[2], seg[3], BALL_R, o.vx, o.vy));
                });
            });
            hole.bumpers.forEach((bumper, i) => {
                const hit = collideBumper(b, bumper, i);
                if (hit > 0) {
                    sfx.boing();
                }
            });
            // moving obstacles must not shove a ball through a wall
            hole.walls.forEach(s => collideSegment(b, s[0], s[1], s[2], s[3], WALL_R, 0, 0));
            if (impact > 40) {
                sfx.bonk(impact);
            }
        });

        // balls knock each other around
        for (let i = 0; i < balls.length; i++) {
            for (let j = i + 1; j < balls.length; j++) {
                const a = balls[i], c = balls[j];
                const dx = c.x - a.x, dy = c.y - a.y;
                const d = Math.sqrt(dx * dx + dy * dy);
                if (d >= 2 * BALL_R || d < 1e-6) {
                    continue;
                }
                const nx = dx / d, ny = dy / d;
                const overlap = (2 * BALL_R - d) / 2;
                a.x -= nx * overlap;
                a.y -= ny * overlap;
                c.x += nx * overlap;
                c.y += ny * overlap;
                const vn = (a.vx - c.vx) * nx + (a.vy - c.vy) * ny;
                if (vn > 0) {
                    const j2 = vn * (1 + 0.9) / 2;
                    a.vx -= j2 * nx;
                    a.vy -= j2 * ny;
                    c.vx += j2 * nx;
                    c.vy += j2 * ny;
                    a.moving = c.moving = true;
                    if (vn > 30) {
                        sfx.clack();
                    }
                }
            }
        }

        balls.forEach(b => {
            if (!b.moving) {
                return;
            }
            // terrain
            let drag = DRAG, roll = ROLL, boosted = false;
            if (hole.sand.some(r => inRect(b.x, b.y, r))) {
                drag = SAND_DRAG;
                roll = SAND_ROLL;
            }
            hole.boosts.forEach(r => {
                if (inRect(b.x, b.y, r)) {
                    b.vx += r[4] * BOOST_ACC * dt;
                    b.vy += r[5] * BOOST_ACC * dt;
                    boosted = true;
                }
            });
            if (hole.water.some(r => inRect(b.x, b.y, r))) {
                splash(b);
                return;
            }
            // cup
            const cx = hole.cup[0] - b.x, cy = hole.cup[1] - b.y;
            const cd = Math.sqrt(cx * cx + cy * cy);
            let speed = Math.sqrt(b.vx * b.vx + b.vy * b.vy);
            if (cd < CUP_R - 2) {
                if (speed < SINK_SPEED) {
                    if (b === players[turn].ball) {
                        sink(b);
                    } else {
                        knockedIn(b);
                    }
                    return;
                }
                // too fast: the cup pulls at the ball and it lips out
                const pull = rules.cupPull(cx, cy, dt);
                b.vx += pull.vx;
                b.vy += pull.vy;
            }
            // friction
            const factor = Math.exp(-drag * dt);
            b.vx *= factor;
            b.vy *= factor;
            speed = Math.sqrt(b.vx * b.vx + b.vy * b.vy);
            if (speed > 0) {
                const s = Math.max(0, speed - roll * dt) / speed;
                b.vx *= s;
                b.vy *= s;
                speed *= s;
            }
            if (speed < STOP_SPEED && !boosted) {
                b.vx = b.vy = 0;
                b.moving = false;
            }
        });

        players.forEach(p => {
            if (p.ball.sinkAnim > 0 && p.ball.sinkAnim < 1) {
                p.ball.sinkAnim = Math.min(1, p.ball.sinkAnim + dt * 3);
            }
        });
        effects = effects.filter(e => (e.t += dt) < e.life);
    }

    function splash(b) {
        effects.push({kind: 'splash', x: b.x, y: b.y, t: 0, life: 0.8});
        sfx.splash();
        const owner = players.find(p => p.ball === b);
        const spot = rules.returnSpot(b, owner === players[turn]);
        b.x = spot.x;
        b.y = spot.y;
        b.vx = b.vy = 0;
        b.moving = false;
        // somebody else's putt costs a ball one penalty stroke at most (the server holds them to that)
        const penalty = owner === players[turn] || !b.penalized;
        if (penalty) {
            b.strokes += 1;
            b.penalized = true;
        }
        banner = {text: 'SPLASH!', sub: penalty ? `${owner.name}: +1 penalty stroke` : `${owner.name}: back where it lay`,
            until: performance.now() + 1400};
        renderScorecard();
    }

    // Only the player putting can hole out. A ball knocked into the cup goes back to where it lay.
    function knockedIn(b) {
        const spot = rules.returnSpot(b, false);
        b.x = spot.x;
        b.y = spot.y;
        b.vx = b.vy = 0;
        b.moving = false;
        const owner = players.find(p => p.ball === b);
        banner = {text: 'Nice try!', sub: `${owner.name}'s ball goes back, you can't hole out for them`,
            until: performance.now() + 1600};
    }

    function sink(b) {
        b.sunk = true;
        b.moving = false;
        b.vx = b.vy = 0;
        b.sinkAnim = 0.001;
        const owner = players.find(p => p.ball === b);
        const diff = b.strokes - hole.par;
        let word;
        if (b.strokes === 1) {
            word = 'HOLE IN ONE!!!';
        } else if (diff <= -3) {
            word = 'ALBATROSS!';
        } else if (diff === -2) {
            word = 'EAGLE!';
        } else if (diff === -1) {
            word = 'Birdie!';
        } else if (diff === 0) {
            word = 'Par.';
        } else if (diff === 1) {
            word = 'Bogey.';
        } else {
            word = `+${diff}`;
        }
        banner = {text: word, sub: `${owner.name} holes out in ${b.strokes}`, until: performance.now() + 1600};
        for (let i = 0; i < 24; i++) {
            const a = Math.random() * Math.PI * 2, v = 60 + Math.random() * 120;
            effects.push({kind: 'spark', x: hole.cup[0], y: hole.cup[1], vx: Math.cos(a) * v, vy: Math.sin(a) * v,
                color: COLORS[i % COLORS.length], t: 0, life: 0.9});
        }
        if (b.strokes === 1) {
            sfx.ace();
        } else {
            sfx.cup();
        }
    }

    // ---------------------------------------------------------------- drawing
    function polyPath(poly) {
        ctx.beginPath();
        poly.forEach((pt, i) => (i ? ctx.lineTo(pt[0], pt[1]) : ctx.moveTo(pt[0], pt[1])));
        ctx.closePath();
    }

    function drawBackground() {
        ctx.fillStyle = '#1b4d1e';
        ctx.fillRect(0, 0, W, H);
        ctx.fillStyle = 'rgba(255,255,255,0.03)';
        for (let x = 0; x < W; x += 40) {
            ctx.fillRect(x, 0, 20, H);
        }
    }

    function drawHole() {
        // fairway with mowed stripes
        polyPath(hole.outline);
        ctx.save();
        ctx.clip();
        ctx.fillStyle = '#4caf50';
        ctx.fillRect(0, 0, W, H);
        ctx.fillStyle = '#43a047';
        for (let x = -H; x < W; x += 32) {
            ctx.beginPath();
            ctx.moveTo(x, 0);
            ctx.lineTo(x + 16, 0);
            ctx.lineTo(x + 16 + H, H);
            ctx.lineTo(x + H, H);
            ctx.fill();
        }
        hole.sand.forEach(r => {
            ctx.fillStyle = '#e6d28a';
            roundRect(r[0], r[1], r[2], r[3], 10);
            ctx.fill();
            ctx.fillStyle = '#cdb76a';
            for (let i = 0; i < r[2] * r[3] / 120; i++) {
                const px = r[0] + ((i * 37) % r[2]), py = r[1] + ((i * 53) % r[3]);
                ctx.fillRect(px, py, 2, 2);
            }
        });
        hole.water.forEach(r => {
            ctx.fillStyle = '#1e88e5';
            ctx.fillRect(r[0], r[1], r[2], r[3]);
            ctx.strokeStyle = 'rgba(255,255,255,0.45)';
            ctx.lineWidth = 2;
            for (let y = r[1] + 10; y < r[1] + r[3]; y += 16) {
                ctx.beginPath();
                for (let x = r[0]; x <= r[0] + r[2]; x += 4) {
                    const yy = y + Math.sin(x / 10 + time * 3) * 2;
                    if (x === r[0]) {
                        ctx.moveTo(x, yy);
                    } else {
                        ctx.lineTo(x, yy);
                    }
                }
                ctx.stroke();
            }
        });
        hole.boosts.forEach(r => {
            ctx.fillStyle = 'rgba(255,235,59,0.25)';
            ctx.fillRect(r[0], r[1], r[2], r[3]);
            const cx = r[0] + r[2] / 2, cy = r[1] + r[3] / 2;
            const angle = Math.atan2(r[5], r[4]);
            ctx.save();
            ctx.translate(cx, cy);
            ctx.rotate(angle);
            const shift = (time * 40) % 20;
            ctx.fillStyle = '#ffeb3b';
            for (let i = -1; i <= 1; i++) {
                const x = i * 20 + shift - 10;
                ctx.beginPath();
                ctx.moveTo(x - 6, -12);
                ctx.lineTo(x + 6, 0);
                ctx.lineTo(x - 6, 12);
                ctx.lineTo(x - 2, 0);
                ctx.fill();
            }
            ctx.restore();
        });
        ctx.restore();

        // tees, coloured by whose they are when everybody has one of their own
        const own = hole.starts.length > 1;
        hole.starts.forEach((tee, i) => {
            if (own && players.length && state !== 'setup' && state !== 'finished' && i >= players.length) {
                return;
            }
            ctx.fillStyle = 'rgba(255,255,255,0.25)';
            ctx.fillRect(tee[0] - 14, tee[1] - 14, 28, 28);
            if (own) {
                ctx.strokeStyle = COLORS[i % COLORS.length];
                ctx.lineWidth = 2;
                ctx.strokeRect(tee[0] - 14, tee[1] - 14, 28, 28);
            }
        });

        // cup
        ctx.fillStyle = '#111';
        ctx.beginPath();
        ctx.arc(hole.cup[0], hole.cup[1], CUP_R, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = '#2e7d32';
        ctx.lineWidth = 2;
        ctx.stroke();

        // walls
        ctx.lineJoin = 'round';
        polyPath(hole.outline);
        ctx.strokeStyle = '#6d4c41';
        ctx.lineWidth = 8;
        ctx.stroke();
        ctx.strokeStyle = '#a1887f';
        ctx.lineWidth = 2;
        ctx.stroke();
        hole.blocks.forEach(b => {
            polyPath(b);
            ctx.fillStyle = hole.house ? '#c62828' : '#8d6e63';
            ctx.fill();
            ctx.strokeStyle = '#6d4c41';
            ctx.lineWidth = 8;
            ctx.stroke();
            ctx.strokeStyle = '#bcaaa4';
            ctx.lineWidth = 2;
            ctx.stroke();
        });
        if (hole.house) {
            ctx.fillStyle = '#fff59d';
            hole.blocks.forEach(b => {
                ctx.fillRect(b[0][0] + 8, b[0][1] + 30, 9, 12);
                ctx.fillRect(b[0][0] + 23, b[0][1] + 30, 9, 12);
            });
        }
        hole.bumpers.forEach((bp, i) => {
            const lit = hole.flash[i] >= 0 && time - hole.flash[i] < 0.15;
            ctx.fillStyle = 'rgba(0,0,0,0.3)';
            ctx.beginPath();
            ctx.arc(bp[0] + 3, bp[1] + 3, bp[2], 0, Math.PI * 2);
            ctx.fill();
            ctx.fillStyle = lit ? '#fff59d' : '#e53935';
            ctx.beginPath();
            ctx.arc(bp[0], bp[1], bp[2], 0, Math.PI * 2);
            ctx.fill();
            ctx.strokeStyle = lit ? '#fff' : '#ffcdd2';
            ctx.lineWidth = 3;
            ctx.beginPath();
            ctx.arc(bp[0], bp[1], bp[2] * 0.6, 0, Math.PI * 2);
            ctx.stroke();
            ctx.strokeStyle = '#000';
            ctx.lineWidth = 1;
            ctx.beginPath();
            ctx.arc(bp[0], bp[1], bp[2], 0, Math.PI * 2);
            ctx.stroke();
        });
        hole.sliders.forEach(s => {
            const o = sliderOffset(s, time);
            const x = s.x + o.x, y = s.y + o.y;
            ctx.fillStyle = '#ff9800';
            ctx.fillRect(x, y, s.w, s.h);
            ctx.fillStyle = '#212121';
            for (let i = 0; i < s.h; i += 14) {
                ctx.fillRect(x, y + i, s.w, 7);
            }
            ctx.strokeStyle = '#000';
            ctx.lineWidth = 1;
            ctx.strokeRect(x, y, s.w, s.h);
        });
    }

    function drawFlag() {
        const [x, y] = hole.cup;
        ctx.strokeStyle = '#eee';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(x, y);
        ctx.lineTo(x + 2, y - 34);
        ctx.stroke();
        const wave = Math.sin(time * 6) * 3;
        ctx.fillStyle = '#e53935';
        ctx.beginPath();
        ctx.moveTo(x + 2, y - 34);
        ctx.lineTo(x + 22, y - 29 + wave);
        ctx.lineTo(x + 2, y - 22);
        ctx.fill();
    }

    function drawRotors() {
        hole.rotors.forEach(r => {
            ctx.lineCap = 'round';
            rotorBlades(r, time).forEach(e => {
                ctx.strokeStyle = 'rgba(0,0,0,0.35)';
                ctx.lineWidth = 8;
                ctx.beginPath();
                ctx.moveTo(e[0] + 3, e[1] + 3);
                ctx.lineTo(e[2] + 3, e[3] + 3);
                ctx.stroke();
                ctx.strokeStyle = '#5d4037';
                ctx.lineWidth = 7;
                ctx.beginPath();
                ctx.moveTo(e[0], e[1]);
                ctx.lineTo(e[2], e[3]);
                ctx.stroke();
                ctx.strokeStyle = '#fff8e1';
                ctx.lineWidth = 3;
                ctx.stroke();
            });
            ctx.lineCap = 'butt';
            ctx.fillStyle = '#ffeb3b';
            ctx.beginPath();
            ctx.arc(r.cx, r.cy, 6, 0, Math.PI * 2);
            ctx.fill();
            ctx.strokeStyle = '#000';
            ctx.lineWidth = 1;
            ctx.stroke();
        });
    }

    function drawBall(p) {
        const b = p.ball;
        if (!b.onCourse || b.out || (b.sunk && b.sinkAnim >= 1)) {
            return;
        }
        let x = b.x, y = b.y, r = BALL_R;
        if (b.sunk) {
            x += (hole.cup[0] - x) * b.sinkAnim;
            y += (hole.cup[1] - y) * b.sinkAnim;
            r *= 1 - b.sinkAnim * 0.6;
        }
        const active = players[turn] === p && state === 'aim';
        ctx.fillStyle = 'rgba(0,0,0,0.3)';
        ctx.beginPath();
        ctx.arc(x + 2, y + 2, r, 0, Math.PI * 2);
        ctx.fill();
        ctx.fillStyle = p.color;
        ctx.beginPath();
        ctx.arc(x, y, r, 0, Math.PI * 2);
        ctx.fill();
        ctx.strokeStyle = '#333';
        ctx.lineWidth = 1;
        ctx.stroke();
        if (active) {
            ctx.strokeStyle = p.color;
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.arc(x, y, r + 5 + Math.sin(time * 6) * 2, 0, Math.PI * 2);
            ctx.stroke();
        }
    }

    function aimVector() {
        if (!aim) {
            return null;
        }
        const dx = aim.sx - aim.x, dy = aim.sy - aim.y;
        const len = Math.sqrt(dx * dx + dy * dy);
        if (len < 4) {
            return null;
        }
        return {power: Math.min(len, MAX_DRAG) / MAX_DRAG, dx: dx / len, dy: dy / len};
    }

    function drawAim() {
        const v = aimVector();
        if (state !== 'aim' || !v) {
            return;
        }
        const b = players[turn].ball;
        const length = 30 + v.power * 140;
        ctx.save();
        ctx.setLineDash([6, 6]);
        ctx.lineDashOffset = -time * 30;
        ctx.strokeStyle = 'rgba(255,255,255,0.9)';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(b.x, b.y);
        ctx.lineTo(b.x + v.dx * length, b.y + v.dy * length);
        ctx.stroke();
        ctx.restore();
        // power meter
        const mx = W - 30, my = H - 130, mh = 110;
        ctx.fillStyle = 'rgba(0,0,0,0.5)';
        ctx.fillRect(mx - 2, my - 2, 16, mh + 4);
        const hue = 120 - v.power * 120;
        ctx.fillStyle = `hsl(${hue}, 90%, 50%)`;
        ctx.fillRect(mx, my + mh * (1 - v.power), 12, mh * v.power);
        ctx.strokeStyle = '#fff';
        ctx.strokeRect(mx - 2, my - 2, 16, mh + 4);
    }

    function drawEffects() {
        effects.forEach(e => {
            const k = e.t / e.life;
            if (e.kind === 'splash') {
                ctx.strokeStyle = `rgba(255,255,255,${1 - k})`;
                ctx.lineWidth = 2;
                for (let i = 1; i <= 3; i++) {
                    ctx.beginPath();
                    ctx.arc(e.x, e.y, k * 14 * i, 0, Math.PI * 2);
                    ctx.stroke();
                }
            } else {
                ctx.fillStyle = e.color;
                ctx.globalAlpha = 1 - k;
                ctx.fillRect(e.x + e.vx * e.t - 2, e.y + e.vy * e.t - 2, 4, 4);
                ctx.globalAlpha = 1;
            }
        });
    }

    function drawHud() {
        const p = players[turn];
        const text = `HOLE ${holeIndex + 1}/${HOLES.length}  ·  PAR ${hole.par}  ·  ${p.name.toUpperCase()}  ·  STROKE ${Math.min(p.ball.strokes + (state === 'aim' ? 1 : 0), MAX_STROKES)}`;
        ctx.font = 'bold 12px Verdana, sans-serif';
        const w = ctx.measureText(text).width + 16;
        ctx.fillStyle = 'rgba(0,0,0,0.55)';
        ctx.fillRect(6, 6, w, 22);
        ctx.fillStyle = p.color;
        ctx.fillText(text, 14, 21);

        if (banner && performance.now() < banner.until) {
            const alpha = Math.min(1, (banner.until - performance.now()) / 300);
            ctx.globalAlpha = alpha;
            ctx.textAlign = 'center';
            ctx.font = 'bold 34px Impact, "Arial Black", sans-serif';
            ctx.lineWidth = 6;
            ctx.strokeStyle = '#000';
            ctx.strokeText(banner.text, W / 2, H / 2 - 4);
            ctx.fillStyle = '#ffeb3b';
            ctx.fillText(banner.text, W / 2, H / 2 - 4);
            ctx.font = 'bold 14px Verdana, sans-serif';
            ctx.lineWidth = 4;
            ctx.strokeText(banner.sub, W / 2, H / 2 + 20);
            ctx.fillStyle = '#fff';
            ctx.fillText(banner.sub, W / 2, H / 2 + 20);
            ctx.textAlign = 'left';
            ctx.globalAlpha = 1;
        }
    }

    function roundRect(x, y, w, h, r) {
        ctx.beginPath();
        ctx.moveTo(x + r, y);
        ctx.arcTo(x + w, y, x + w, y + h, r);
        ctx.arcTo(x + w, y + h, x, y + h, r);
        ctx.arcTo(x, y + h, x, y, r);
        ctx.arcTo(x, y, x + w, y, r);
        ctx.closePath();
    }

    function drawAttract() {
        // the title screen shows a random hole in the background
        drawBackground();
        drawHole();
        drawRotors();
        drawFlag();
    }

    function draw() {
        if (state === 'setup' || state === 'finished') {
            drawAttract();
            return;
        }
        drawBackground();
        drawHole();
        players.forEach(drawBall);
        drawRotors();
        drawFlag();
        drawEffects();
        drawAim();
        drawHud();
    }

    // ---------------------------------------------------------------- main loop
    let lastFrame = performance.now();
    let accumulator = 0;

    function frame(now) {
        accumulator += Math.min(0.1, (now - lastFrame) / 1000);
        lastFrame = now;
        while (accumulator >= DT) {
            if (state === 'setup' || state === 'finished') {
                time += DT;
            } else {
                step(DT);
            }
            accumulator -= DT;
        }
        if (state === 'rolling' && !anythingMoving()) {
            endOfShot();
        }
        if (state === 'aim') {
            processNet();
        }
        publishState();
        draw();
        requestAnimationFrame(frame);
    }

    // where the game is at, for styling and for anybody watching the page
    function publishState() {
        if (root.dataset.state !== state) {
            root.dataset.state = state;
        }
        if (root.dataset.hole !== String(holeIndex + 1)) {
            root.dataset.hole = String(holeIndex + 1);
        }
    }

    // ---------------------------------------------------------------- input
    function toCourse(event) {
        const r = canvas.getBoundingClientRect();
        return {x: (event.clientX - r.left) * W / r.width, y: (event.clientY - r.top) * H / r.height};
    }

    canvas.addEventListener('pointerdown', function (event) {
        if (state !== 'aim' || event.button !== 0 || !canPutt()) {
            if (event.button === 2) {
                aim = null;
            }
            return;
        }
        const p = toCourse(event);
        aim = {sx: p.x, sy: p.y, x: p.x, y: p.y};
        canvas.setPointerCapture(event.pointerId);
    });
    canvas.addEventListener('pointermove', function (event) {
        if (aim) {
            const p = toCourse(event);
            aim.x = p.x;
            aim.y = p.y;
        }
    });
    canvas.addEventListener('pointerup', function () {
        const v = aimVector();
        aim = null;
        if (state === 'aim' && canPutt() && v && v.power > 0.03) {
            shoot(v.power, v.dx, v.dy);
        }
    });
    canvas.addEventListener('pointercancel', () => {
        aim = null;
    });
    canvas.addEventListener('contextmenu', (event) => {
        event.preventDefault();
        aim = null;
    });
    window.addEventListener('keydown', (event) => {
        if (event.key === 'Escape') {
            aim = null;
        }
    });

    // ---------------------------------------------------------------- setup screen
    function addPlayerRow(name, locked) {
        const li = el('li');
        const input = el('input');
        input.type = 'text';
        input.maxLength = 16;
        input.value = name;
        input.className = 'minigolfPlayerName';
        input.setAttribute('aria-label', `Player ${playerList.children.length + 1} name`);
        if (locked) {
            input.readOnly = true;
            input.title = 'Your rounds are saved to the leaderboard';
        }
        li.appendChild(input);
        if (!locked) {
            const remove = el('button', '✖', 'minigolfButton');
            remove.type = 'button';
            remove.title = 'Remove player';
            remove.addEventListener('click', () => {
                li.remove();
                updateAddButton();
            });
            li.appendChild(remove);
        } else {
            li.appendChild(el('span', ' (you)'));
        }
        playerList.appendChild(li);
        updateAddButton();
    }

    function updateAddButton() {
        document.getElementById('minigolfAddPlayer').disabled = playerList.children.length >= 4;
    }

    document.getElementById('minigolfAddPlayer').addEventListener('click', function () {
        if (playerList.children.length < 4) {
            addPlayerRow(`Guest ${playerList.children.length}`, false);
            playerList.lastChild.querySelector('input').select();
        }
    });

    document.getElementById('minigolfStart').addEventListener('click', function () {
        const mismatch = courseMismatch(course);
        if (mismatch) {
            setStatus(mismatch);
            return;
        }
        const names = Array.from(playerList.querySelectorAll('input')).map((input, i) =>
            input.value.trim() || `Player ${i + 1}`);
        players = names.map((name, i) => ({name, isMe: i === 0, color: COLORS[i], scores: [], ball: newBall()}));
        setup.hidden = true;
        result.hidden = true;
        startHole(0);
    });

    document.getElementById('minigolfAgain').addEventListener('click', function () {
        if (net) {
            leaveNet();
            return;
        }
        result.hidden = true;
        setup.hidden = false;
        state = 'setup';
        renderScorecard();
        setStatus('Ready.');
        refreshGames();
    });

    // ---------------------------------------------------------------- scorecard & results
    function renderScorecard() {
        const head = scorecard.tHead, body = scorecard.tBodies[0];
        head.textContent = '';
        body.textContent = '';
        if (!players.length) {
            return;
        }
        const hr = el('tr');
        hr.appendChild(el('th', 'Hole'));
        HOLES.forEach((h, i) => hr.appendChild(el('th', String(i + 1), i === holeIndex && state !== 'finished' ? 'current' : '')));
        hr.appendChild(el('th', 'Total'));
        head.appendChild(hr);

        const par = el('tr');
        par.appendChild(el('th', 'Par'));
        HOLES.forEach(h => par.appendChild(el('td', String(h.par))));
        par.appendChild(el('td', String(HOLES.reduce((s, h) => s + h.par, 0)), 'total'));
        body.appendChild(par);

        players.forEach(p => {
            const tr = el('tr');
            const name = el('th');
            const swatch = el('span', '● ', 'minigolfSwatch');
            swatch.style.color = p.color;
            name.appendChild(swatch);
            name.appendChild(document.createTextNode(p.left ? `${p.name} (left)` : p.name));
            tr.appendChild(name);
            HOLES.forEach((h, i) => {
                let value = p.scores[i];
                let cls = '';
                if (value === undefined && i === holeIndex && state !== 'setup' && p.ball.strokes) {
                    value = p.ball.strokes;
                    cls = 'current';
                }
                if (p.scores[i] !== undefined && p.scores[i] < h.par) {
                    cls = 'under';
                }
                tr.appendChild(el('td', value === undefined ? '' : String(value), cls));
            });
            tr.appendChild(el('td', String(total(p)), 'total'));
            body.appendChild(tr);
        });
    }

    function total(p) {
        return p.scores.reduce((s, v) => s + v, 0);
    }

    function toPar(p) {
        const diff = total(p) - HOLES.reduce((s, h) => s + h.par, 0);
        return diff === 0 ? 'E' : (diff > 0 ? `+${diff}` : String(diff));
    }

    function finishRound() {
        state = 'finished';
        aim = null;
        renderScorecard();
        updateNetControls();
        const ranking = players.filter(p => !p.left).sort((a, b) => total(a) - total(b));
        const places = rules.places(ranking.map(total));
        const rows = document.getElementById('minigolfResultRows');
        rows.textContent = '';
        const MEDALS = ['🥇', '🥈', '🥉', '4.'];
        ranking.forEach((p, i) => {
            const tr = el('tr');
            tr.appendChild(el('td', MEDALS[places[i]]));
            tr.appendChild(el('td', p.name));
            tr.appendChild(el('td', `${total(p)} (${toPar(p)})`));
            rows.appendChild(tr);
        });
        result.hidden = false;
        const winners = ranking.filter(p => total(p) === total(ranking[0]));
        if (!ranking.length) {
            setStatus('Everybody left, so nobody wins.');
        } else if (ranking.length === 1) {
            setStatus(`Round finished: ${total(ranking[0])} strokes.`);
        } else if (winners.length > 1) {
            setStatus(`It's a tie! ${winners.map(p => p.name).join(' & ')} share the win.`);
        } else {
            setStatus(`${ranking[0].name} wins!`);
        }
        if (net) {
            // the server saved everybody's rounds when the last ball dropped
            clearTimeout(net.pollTimer);
            document.getElementById('minigolfSaved').textContent = ranking.length
                ? "Everybody's rounds went into the Hall of Fame." : 'Nobody finished, so no rounds were saved.';
            loadLeaderboard();
        } else {
            submitRound(players.find(p => p.isMe));
        }
    }

    function submitRound(player) {
        const saved = document.getElementById('minigolfSaved');
        saved.textContent = 'Saving your round...';
        fetch(root.dataset.submitUrl, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify({course, strokes: player.scores}),
        }).then(response => {
            if (response.status === 401) {
                throw new Error('logged out');
            }
            if (!response.ok || response.redirected) {
                throw new Error(`HTTP ${response.status}`);
            }
            return response.json();
        }).then(data => {
            saved.textContent = `${player.name}'s round (${total(player)}) went into the Hall of Fame.`;
            renderLeaderboard(data);
        }).catch(error => {
            console.error('Saving the minigolf round failed:', error);
            saved.textContent = error.message === 'logged out'
                ? 'You were logged out, so your round could not be saved. Log in again to keep playing.'
                : 'Could not save your round, sorry!';
        });
    }

    // the leaderboard of the map pack picked on the setup screen
    function loadLeaderboard() {
        api('GET', `${root.dataset.leaderboardUrl}?course=${encodeURIComponent(course)}`).then(renderLeaderboard)
            .catch(error => console.error('Loading the minigolf leaderboard failed:', error));
    }

    function renderLeaderboard(data) {
        document.getElementById('minigolfBoardCourse').textContent = courseName(data.course);
        const best = document.getElementById('minigolfBest');
        best.textContent = '';
        if (!data.best.length) {
            const tr = el('tr');
            const td = el('td', 'No rounds played yet. Be the first!');
            td.colSpan = 4;
            tr.appendChild(td);
            best.appendChild(tr);
        }
        data.best.forEach((row, i) => {
            const tr = el('tr');
            [String(i + 1), row.name, String(row.best), String(row.rounds)].forEach(v => tr.appendChild(el('td', v)));
            best.appendChild(tr);
        });
        const recent = document.getElementById('minigolfRecent');
        recent.textContent = '';
        if (!data.recent.length) {
            const tr = el('tr');
            const td = el('td', 'Nothing here yet.');
            td.colSpan = 3;
            tr.appendChild(td);
            recent.appendChild(tr);
        }
        data.recent.forEach(row => {
            const tr = el('tr');
            [row.name, String(row.total), row.played_at.replace('T', ' ')].forEach(v => tr.appendChild(el('td', v)));
            recent.appendChild(tr);
        });
    }

    // ---------------------------------------------------------------- network games
    //
    // Every browser in a game polls it. A shot is simulated by the shooter's browser, which posts how it
    // was played and where all the balls ended up. The others replay the shot from how it was played,
    // so they see it roll, and then put the balls where the shooter's browser says they are.
    // Whenever this browser doesn't agree with the server about the game (a missed poll, a player who
    // left, a reload), it takes the server's state as it is.
    const gamesUrl = root.dataset.gamesUrl;
    const MAX_PLAYERS = parseInt(root.dataset.maxPlayers, 10) || 4;
    const POLL_MS = 1000;
    const LIST_POLL_MS = 3000;
    const lobby = document.getElementById('minigolfLobby');
    const gameList = document.getElementById('minigolfGames');
    const skipButton = document.getElementById('minigolfSkip');
    const leaveButton = document.getElementById('minigolfLeave');
    let listTimer = null;

    function api(method, url, body) {
        return fetch(url, {
            method,
            credentials: 'include',
            headers: body === undefined ? {} : {'Content-Type': 'application/json'},
            body: body === undefined ? undefined : JSON.stringify(body),
        }).then(response => {
            if (response.status === 401) {
                throw new Error('logged out');
            }
            if (response.redirected) {
                throw new Error(`HTTP ${response.status}`);
            }
            return response.json().catch(() => null).then(data => {
                if (!response.ok) {
                    const error = new Error(typeof data === 'string' ? data : `HTTP ${response.status}`);
                    error.status = response.status;
                    throw error;
                }
                return data;
            });
        });
    }

    function failed(what, error) {
        console.error(`${what} failed:`, error);
        setStatus(error.message === 'logged out'
            ? 'You were logged out. Log in again to keep playing.'
            : `${what} failed: ${error.message}`);
    }

    // the open lobbies and the games this player is in, on the setup screen
    function refreshGames() {
        clearTimeout(listTimer);
        if (net || state !== 'setup') {
            return;
        }
        api('GET', gamesUrl).then(renderGames).catch(error => console.error('Loading the games failed:', error))
            .finally(() => {
                if (!net && state === 'setup') {
                    listTimer = setTimeout(refreshGames, LIST_POLL_MS);
                }
            });
    }

    function renderGames(games) {
        if (net) {
            return;
        }
        gameList.textContent = '';
        if (!games.length) {
            gameList.appendChild(el('li', 'No open games right now. Host one!'));
        }
        games.forEach(g => {
            const li = el('li');
            li.appendChild(el('span', `${g.host}'s game (${courseName(g.course)}): ${g.players.join(', ')}`));
            let label = null;
            if (g.status === 'playing') {
                label = 'Resume';
            } else if (g.joined) {
                label = 'Open';
            } else if (g.players.length < MAX_PLAYERS) {
                label = 'Join';
            }
            if (label) {
                const button = el('button', label, 'minigolfButton');
                button.type = 'button';
                button.setAttribute('aria-label', `${label} ${g.host}'s game`);
                button.addEventListener('click', () => {
                    const mismatch = courseMismatch(g.course);
                    if (mismatch) {
                        setStatus(mismatch);
                        return;
                    }
                    const request = label === 'Join' ? api('POST', `${gamesUrl}/${g.id}/join`)
                        : api('GET', `${gamesUrl}/${g.id}`);
                    request.then(enterNet).catch(error => {
                        failed('Joining the game', error);
                        refreshGames();
                    });
                });
                li.appendChild(button);
            } else {
                li.appendChild(el('span', '(full)'));
            }
            gameList.appendChild(li);
        });
    }

    document.getElementById('minigolfHost').addEventListener('click', function () {
        const mismatch = courseMismatch(course);
        if (mismatch) {
            setStatus(mismatch);
            return;
        }
        api('POST', gamesUrl, {course}).then(enterNet).catch(error => failed('Hosting a game', error));
    });

    function enterNet(view) {
        clearTimeout(listTimer);
        usePack(view.course);
        net = {id: view.id, seq: 0, latest: null, epoch: 0, posting: false, started: false, replaying: null,
            lastShot: null, pollTimer: null};
        setup.hidden = true;
        result.hidden = true;
        handle(view);
        schedulePoll();
    }

    function leaveNet(message) {
        if (net) {
            clearTimeout(net.pollTimer);
        }
        net = null;
        players = [];
        state = 'setup';
        aim = null;
        lobby.hidden = true;
        result.hidden = true;
        setup.hidden = false;
        pickPack(courseSelect.value);
        renderScorecard();
        updateNetControls();
        setStatus(message || 'Ready.');
        refreshGames();
    }

    function schedulePoll() {
        clearTimeout(net.pollTimer);
        const n = net;
        n.pollTimer = setTimeout(() => poll(n), POLL_MS);
    }

    function poll(n) {
        if (net !== n || state === 'finished') {
            return;
        }
        if (n.posting) {
            schedulePoll();
            return;
        }
        const epoch = n.epoch;
        api('GET', `${gamesUrl}/${n.id}?since=${Math.max(0, n.seq)}`).then(view => {
            // a poll that was on its way while a shot was sent may not know about it yet
            if (net === n && epoch === n.epoch) {
                handle(view);
            }
        }).catch(error => {
            if (net !== n) {
                return;
            }
            if (error.status === 404) {
                leaveNet('The game was called off.');
                return;
            }
            console.error('Polling the game failed:', error);
        }).finally(() => {
            if (net === n) {
                schedulePoll();
            }
        });
    }

    // the answer to something this player did, newer than any poll that's on its way
    function accept(view) {
        if (net) {
            net.epoch += 1;
            handle(view);
        }
    }

    function handle(view) {
        if (net.started && view.status === 'lobby') {
            return;
        }
        net.latest = view;
        if (view.status === 'lobby') {
            if (view.me === null) {
                leaveNet("You're not in that game anymore.");
                return;
            }
            showLobby(view);
            return;
        }
        lobby.hidden = true;
        if (!net.started) {
            net.started = true;
            players = view.players.map((p, i) => ({name: p.name, isMe: i === view.me, left: p.left,
                color: COLORS[i % COLORS.length], scores: [], ball: newBall()}));
            holeIndex = -1;
            snap(view);
            return;
        }
        processNet();
    }

    function showLobby(view) {
        document.getElementById('minigolfLobbyTitle').textContent = `${view.host}'s game: ${courseName(view.course)}`;
        const list = document.getElementById('minigolfLobbyPlayers');
        list.textContent = '';
        view.players.forEach((p, i) => {
            const li = el('li');
            const swatch = el('span', '● ', 'minigolfSwatch');
            swatch.style.color = COLORS[i % COLORS.length];
            li.appendChild(swatch);
            li.appendChild(document.createTextNode(p.name + (i === view.me ? ' (you)' : '')));
            list.appendChild(li);
        });
        const enough = view.players.length >= 2;
        const start = document.getElementById('minigolfLobbyStart');
        start.hidden = !view.is_host;
        start.disabled = !enough;
        document.getElementById('minigolfLobbyHint').textContent = view.is_host
            ? (enough ? 'Everybody here? Then start the game!'
                : "Waiting for players. Tell them to open Minigolf and join your game.")
            : `Waiting for ${view.host} to start the game.`;
        lobby.hidden = false;
        setStatus(`In ${view.host}'s lobby, ${view.players.length} of ${MAX_PLAYERS} players.`);
    }

    document.getElementById('minigolfLobbyStart').addEventListener('click', function () {
        if (net) {
            api('POST', `${gamesUrl}/${net.id}/start`).then(accept).catch(error => failed('Starting the game', error));
        }
    });

    function leaveGame() {
        if (!net) {
            return;
        }
        const n = net;
        api('POST', `${gamesUrl}/${n.id}/leave`).then(() => {
            if (net === n) {
                leaveNet('You left the game.');
            }
        }).catch(error => {
            if (error.status === 404) {
                leaveNet('The game was called off.');
            } else {
                failed('Leaving the game', error);
            }
        });
    }

    document.getElementById('minigolfLobbyLeave').addEventListener('click', leaveGame);
    leaveButton.addEventListener('click', function () {
        if (window.confirm("Leave the game? Your round won't count.")) {
            leaveGame();
        }
    });

    skipButton.addEventListener('click', function () {
        const view = net && net.latest;
        if (!view || view.turn === null) {
            return;
        }
        api('POST', `${gamesUrl}/${net.id}/skip`, {seat: view.turn, seq: view.seq}).then(accept).catch(error => failed('Skipping', error));
    });

    function updateNetControls() {
        const view = net && net.started && state !== 'finished' ? net.latest : null;
        leaveButton.hidden = !(view && view.me !== null && !view.players[view.me].left);
        skipButton.hidden = !(view && view.can_skip && view.turn !== null);
        if (!skipButton.hidden) {
            skipButton.textContent = `Skip ${view.players[view.turn].name}`;
        }
    }

    // Catches up with the server once this browser is done with what it was showing.
    function processNet() {
        if (!net || !net.started || !net.latest || net.posting || state === 'rolling' || state === 'between') {
            return;
        }
        updateNetControls();
        if (state === 'finished') {
            return;
        }
        const view = net.latest;
        const move = (view.moves || []).find(m => m.seq === net.seq);
        if (move && move.kind === 'shot' && move.hole === holeIndex && move.seat === turn && !players[turn].isMe) {
            net.seq += 1;
            net.replaying = move;
            aim = null;
            time = move.shot.time; // so the windmill and the sliders are where they were
            shoot(move.shot.power, move.shot.dx, move.shot.dy);
            return;
        }
        if (view.seq !== net.seq || view.status !== 'playing' || view.hole !== holeIndex || view.turn !== turn
            || view.players.some((p, i) => p.left !== players[i].left)) {
            snap(view);
        }
    }

    function ballFrom(s, b) {
        b = b || newBall();
        b.vx = b.vy = 0;
        b.moving = false;
        b.onCourse = s.on;
        if (s.on) {
            b.x = b.lastX = s.x;
            b.y = b.lastY = s.y;
        }
        b.strokes = s.strokes;
        if (s.sunk && !b.sunk) {
            b.sinkAnim = 1;
        }
        b.sunk = s.sunk;
        b.out = s.out;
        return b;
    }

    // the balls as the shooter's browser left them, the same ball objects keep their animations
    function takeBalls(balls) {
        players.forEach((p, i) => ballFrom(balls[i], p.ball));
    }

    // Takes the game as the server has it.
    function snap(view) {
        net.seq = view.seq;
        net.replaying = null;
        aim = null;
        view.players.forEach((vp, i) => {
            players[i].scores = vp.scores.slice();
            players[i].left = vp.left;
        });
        if (view.status === 'finished' || view.turn === null) {
            holeIndex = HOLES.length - 1;
            finishRound();
            return;
        }
        if (view.hole !== holeIndex) {
            holeIndex = view.hole;
            hole = prepareHole(HOLES[holeIndex]);
            time = 0;
            effects = [];
            banner = {text: `Hole ${holeIndex + 1}: ${hole.name}`, sub: `Par ${hole.par}`, until: performance.now() + 2200};
        }
        players.forEach((p, i) => {
            p.ball = ballFrom(view.balls[i]);
        });
        order = honourOrder(holeIndex);
        turn = view.turn;
        beginTurn();
        renderScorecard();
        updateNetControls();
        if (view.me !== null && view.players[view.me].left) {
            setStatus("You were skipped for taking too long. You can keep watching, though.");
        }
    }

    function postShot() {
        const n = net;
        const body = {
            seq: n.seq, hole: holeIndex, shot: n.lastShot,
            balls: players.map(p => ({x: p.ball.x, y: p.ball.y, strokes: p.ball.strokes, sunk: p.ball.sunk})),
        };
        n.seq += 1;
        n.epoch += 1;
        n.posting = true;
        api('POST', `${gamesUrl}/${n.id}/moves`, body).then(view => {
            if (net === n) {
                n.latest = view;
            }
        }).catch(error => {
            if (net !== n) {
                return;
            }
            failed('Sending your shot', error);
            // start over from what the server has
            n.seq = -1;
            n.latest = null;
        }).finally(() => {
            n.posting = false;
        });
    }

    // ---------------------------------------------------------------- map packs
    const courseSelect = document.getElementById('minigolfCourse');

    // the pack to play next on this computer, shown on the title screen with its leaderboard
    function pickPack(id) {
        usePack(id);
        hole = prepareHole(HOLES[Math.floor(Math.random() * HOLES.length)]);
        document.getElementById('minigolfCourseHint').textContent = PACKS[id] ? PACKS[id].hint : '';
        const mismatch = courseMismatch(id);
        setStatus(mismatch || 'Ready.');
    }

    courseSelect.addEventListener('change', function () {
        pickPack(courseSelect.value);
        loadLeaderboard();
    });

    // ---------------------------------------------------------------- go
    addPlayerRow(me, true);
    pickPack(courseSelect.value || root.dataset.course);
    refreshGames();
    requestAnimationFrame(frame);
})();
