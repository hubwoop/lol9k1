/*
 * LOL 9001 Minigolf: a tiny top down minigolf game for the downtime between matches.
 * Hot seat for 1-4 players, the logged-in player's rounds go to the leaderboard.
 * No dependencies, just a canvas.
 */
(function () {
    'use strict';

    const root = document.getElementById('minigolf');
    if (!root) {
        return;
    }

    // ---------------------------------------------------------------- constants
    const W = 640, H = 400;
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
    const COLORS = ['#ffffff', '#ffeb3b', '#ff7043', '#4fc3f7'];

    // ---------------------------------------------------------------- course
    function rect(x, y, w, h) {
        return [[x, y], [x + w, y], [x + w, y + h], [x, y + h]];
    }

    const HOLES = [
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
    let players = [];        // {name, isMe, color, scores: [], ball}
    let holeIndex = 0;
    let hole = null;         // HOLES[holeIndex] plus precomputed segments
    let turn = 0;            // index into players
    let state = 'setup';     // setup | aim | rolling | between | finished
    let time = 0;            // course clock, drives moving obstacles
    let banner = null;       // {text, sub, until}
    let aim = null;          // {sx, sy, x, y} pointer drag in course coordinates
    let effects = [];        // splashes and sparkles
    let order = [];          // tee order on the current hole

    function prepareHole(def) {
        const h = Object.assign({blocks: [], sand: [], water: [], boosts: [], rotors: [], sliders: []}, def);
        h.walls = segments(h.outline);
        h.blocks.forEach(b => h.walls.push(...segments(b)));
        return h;
    }

    function newBall() {
        return {x: 0, y: 0, vx: 0, vy: 0, lastX: 0, lastY: 0, onCourse: false, sunk: false, out: false,
            strokes: 0, moving: false, sinkAnim: 0};
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
        // honours: best score on the previous hole tees off first
        order = players.map((p, i) => i);
        if (index > 0) {
            order.sort((a, b) => players[a].scores[index - 1] - players[b].scores[index - 1] || a - b);
        }
        turn = order[0];
        banner = {text: `Hole ${index + 1}: ${hole.name}`, sub: `Par ${hole.par}`, until: performance.now() + 2200};
        beginTurn();
        renderScorecard();
    }

    function beginTurn() {
        const p = players[turn];
        if (!p.ball.onCourse) {
            p.ball.onCourse = true;
            p.ball.x = p.ball.lastX = hole.start[0];
            p.ball.y = p.ball.lastY = hole.start[1];
        }
        state = 'aim';
        aim = null;
        setStatus(`${p.name}, it's your turn! Stroke ${p.ball.strokes + 1}.`);
    }

    function setStatus(text) {
        statusLine.textContent = text;
    }

    function shoot(power, dirX, dirY) {
        const p = players[turn];
        const b = p.ball;
        b.lastX = b.x;
        b.lastY = b.y;
        b.vx = dirX * power * MAX_SPEED;
        b.vy = dirY * power * MAX_SPEED;
        b.moving = true;
        b.strokes += 1;
        state = 'rolling';
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
        if (!b.sunk && b.strokes >= MAX_STROKES) {
            b.out = true;
            b.strokes = MAX_STROKES;
            banner = {text: `${p.name}: ${MAX_STROKES} strokes`, sub: 'Pick it up, buddy.', until: performance.now() + 1500};
        }
        renderScorecard();
        // next player in honour order who still has to play
        const at = order.indexOf(turn);
        for (let i = 1; i <= order.length; i++) {
            const candidate = order[(at + i) % order.length];
            const cb = players[candidate].ball;
            if (!cb.sunk && !cb.out) {
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
                    sink(b);
                    return;
                }
                // too fast: the cup pulls at the ball and it lips out
                // (dead centre there is no direction to pull in, and dividing by 0 would make the ball NaN)
                if (cd > 1e-6) {
                    b.vx += cx / cd * 2600 * dt;
                    b.vy += cy / cd * 2600 * dt;
                }
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
        b.x = b.lastX;
        b.y = b.lastY;
        b.vx = b.vy = 0;
        b.moving = false;
        b.strokes += 1; // penalty
        const owner = players.find(p => p.ball === b);
        banner = {text: 'SPLASH!', sub: `${owner.name}: +1 penalty stroke`, until: performance.now() + 1400};
        renderScorecard();
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

        // tee
        ctx.fillStyle = 'rgba(255,255,255,0.25)';
        ctx.fillRect(hole.start[0] - 14, hole.start[1] - 14, 28, 28);

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
        draw();
        requestAnimationFrame(frame);
    }

    // ---------------------------------------------------------------- input
    function toCourse(event) {
        const r = canvas.getBoundingClientRect();
        return {x: (event.clientX - r.left) * W / r.width, y: (event.clientY - r.top) * H / r.height};
    }

    canvas.addEventListener('pointerdown', function (event) {
        if (state !== 'aim' || event.button !== 0) {
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
        if (state === 'aim' && v && v.power > 0.03) {
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
        const names = Array.from(playerList.querySelectorAll('input')).map((input, i) =>
            input.value.trim() || `Player ${i + 1}`);
        players = names.map((name, i) => ({name, isMe: i === 0, color: COLORS[i], scores: [], ball: newBall()}));
        setup.hidden = true;
        result.hidden = true;
        startHole(0);
    });

    document.getElementById('minigolfAgain').addEventListener('click', function () {
        result.hidden = true;
        setup.hidden = false;
        state = 'setup';
        renderScorecard();
        setStatus('Ready.');
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
            name.appendChild(document.createTextNode(p.name));
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
        renderScorecard();
        const ranking = players.slice().sort((a, b) => total(a) - total(b));
        const rows = document.getElementById('minigolfResultRows');
        rows.textContent = '';
        const MEDALS = ['🥇', '🥈', '🥉', '4.'];
        let place = 0;
        ranking.forEach((p, i) => {
            const tr = el('tr');
            // tied players share a place, the next one after them skips ahead (1, 1, 3)
            if (i > 0 && total(p) !== total(ranking[i - 1])) {
                place = i;
            }
            tr.appendChild(el('td', MEDALS[place]));
            tr.appendChild(el('td', p.name));
            tr.appendChild(el('td', `${total(p)} (${toPar(p)})`));
            rows.appendChild(tr);
        });
        result.hidden = false;
        const winners = ranking.filter(p => total(p) === total(ranking[0]));
        if (players.length === 1) {
            setStatus(`Round finished: ${total(ranking[0])} strokes.`);
        } else if (winners.length > 1) {
            setStatus(`It's a tie! ${winners.map(p => p.name).join(' & ')} share the win.`);
        } else {
            setStatus(`${ranking[0].name} wins!`);
        }
        submitRound(players.find(p => p.isMe));
    }

    function submitRound(player) {
        const saved = document.getElementById('minigolfSaved');
        saved.textContent = 'Saving your round...';
        fetch(root.dataset.submitUrl, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            credentials: 'include',
            body: JSON.stringify({strokes: player.scores}),
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

    function renderLeaderboard(data) {
        const best = document.getElementById('minigolfBest');
        best.textContent = '';
        data.best.forEach((row, i) => {
            const tr = el('tr');
            [String(i + 1), row.name, String(row.best), String(row.rounds)].forEach(v => tr.appendChild(el('td', v)));
            best.appendChild(tr);
        });
        const recent = document.getElementById('minigolfRecent');
        recent.textContent = '';
        data.recent.forEach(row => {
            const tr = el('tr');
            [row.name, String(row.total), row.played_at].forEach(v => tr.appendChild(el('td', v)));
            recent.appendChild(tr);
        });
    }

    // ---------------------------------------------------------------- go
    addPlayerRow(me, true);
    hole = prepareHole(HOLES[Math.floor(Math.random() * HOLES.length)]);
    requestAnimationFrame(frame);

    // for the e2e tests and the curious
    window.lol9k1Minigolf = {
        holes: HOLES,
        startHole: (i) => startHole(i),
        state: () => ({state, hole: holeIndex, turn, players: players.map(p => ({name: p.name, scores: p.scores.slice(),
            strokes: p.ball.strokes, x: p.ball.x, y: p.ball.y}))}),
    };
})();
