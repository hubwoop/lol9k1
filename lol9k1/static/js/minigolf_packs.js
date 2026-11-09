/*
 * The browser of shared minigolf map packs (/minigolf/packs): a small picture of every hole of a pack,
 * each a link to test that hole in the map editor, and withdrawing a pack.
 * The holes are loaded when a pack scrolls into view, a version's holes never change.
 */
(function () {
    'use strict';

    const root = document.getElementById('minigolfPacks');
    if (!root) {
        return;
    }
    const W = parseInt(root.dataset.width, 10), H = parseInt(root.dataset.height, 10);
    const SCALE = 0.3;
    const LOOK = window.lol9k1MinigolfLook;  // static/js/minigolf.js

    function polygon(ctx, poly) {
        ctx.beginPath();
        poly.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
        ctx.closePath();
    }

    // The hole as it lies before anybody putts, simplified to read at this size, in the game's colours.
    // Tees are white dots here, the game's tee boxes are too faint to see this small.
    function drawHole(canvas, h) {
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        canvas.width = W * SCALE * dpr;
        canvas.height = H * SCALE * dpr;
        const ctx = canvas.getContext('2d');
        ctx.scale(SCALE * dpr, SCALE * dpr);
        ctx.fillStyle = LOOK.rough;
        ctx.fillRect(0, 0, W, H);
        polygon(ctx, h.outline);
        ctx.fillStyle = LOOK.fairway;
        ctx.fill();
        const rects = (list, colour) => (list || []).forEach(r => {
            ctx.fillStyle = colour;
            ctx.fillRect(r[0], r[1], r[2], r[3]);
        });
        rects(h.sand, LOOK.sand);
        rects(h.water, LOOK.water);
        rects(h.boosts, LOOK.boost);
        ctx.lineJoin = 'round';
        polygon(ctx, h.outline);
        ctx.lineWidth = 8;
        ctx.strokeStyle = LOOK.wall;
        ctx.stroke();
        (h.blocks || []).forEach(b => {
            polygon(ctx, b);
            ctx.fillStyle = h.house ? LOOK.house : LOOK.block;
            ctx.fill();
        });
        rects((h.sliders || []).map(s => [s.x, s.y, s.w, s.h]), LOOK.slider);
        const dot = (x, y, r, colour) => {
            ctx.beginPath();
            ctx.arc(x, y, r, 0, Math.PI * 2);
            ctx.fillStyle = colour;
            ctx.fill();
        };
        (h.bumpers || []).forEach(b => dot(b[0], b[1], b[2], LOOK.bumper));
        (h.rotors || []).forEach(r => {
            ctx.strokeStyle = 'rgba(255,255,255,0.8)';
            ctx.lineWidth = 6;
            for (let i = 0; i < r.blades; i++) {
                const a = i * Math.PI * 2 / r.blades;
                ctx.beginPath();
                ctx.moveTo(r.cx, r.cy);
                ctx.lineTo(r.cx + Math.cos(a) * r.len, r.cy + Math.sin(a) * r.len);
                ctx.stroke();
            }
        });
        (h.starts || [h.start]).forEach(t => dot(t[0], t[1], 9, '#fff'));
        dot(h.cup[0], h.cup[1], 12, LOOK.cup);
    }

    // The answer of the server, or an error with its message: it answers a failed request with a JSON string.
    function request(url, options) {
        return fetch(url, {credentials: 'include', ...options}).then(response => {
            if (response.status === 401 || response.redirected) {
                throw new Error('You were logged out. Log in again in another tab, then try again.');
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

    function showHoles(item) {
        const url = root.dataset.courseUrl.replace(/-$/, encodeURIComponent(item.dataset.course));
        const list = item.querySelector('.mgpHoles');
        list.textContent = '';
        request(url).then(data => {
            data.holes.forEach((h, i) => {
                const li = document.createElement('li');
                const link = document.createElement('a');
                link.href = `${item.dataset.editorUrl}&hole=${i + 1}`;
                link.title = `Test hole ${i + 1} in the editor`;
                link.setAttribute('aria-label', `Test hole ${i + 1}, ${h.name}, par ${h.par}`);
                const canvas = document.createElement('canvas');
                // the link's label says what's on it
                canvas.setAttribute('aria-hidden', 'true');
                drawHole(canvas, h);
                const caption = document.createElement('span');
                caption.textContent = `${i + 1}. ${h.name} (par ${h.par})`;
                link.append(canvas, caption);
                li.appendChild(link);
                list.appendChild(li);
            });
        }).catch(error => {
            console.error('Loading the holes failed:', error);
            const li = document.createElement('li');
            li.className = 'mgpHolesFailed';
            li.append(`Couldn't load the holes of ${item.getAttribute('aria-label')}. `
                + 'Check your connection and try again. ');
            const retry = document.createElement('button');
            retry.type = 'button';
            retry.className = 'minigolfButton';
            retry.textContent = 'Retry';
            retry.addEventListener('click', () => showHoles(item));
            li.appendChild(retry);
            list.appendChild(li);
        });
    }

    // "today 17:11" or "yesterday 17:11" for when a pack was published, the date and time otherwise.
    // The full timestamp stays in the title.
    function showWhen(time) {
        const published = time.getAttribute('datetime');
        const day = date => [date.getFullYear(), date.getMonth() + 1, date.getDate()]
            .map(n => String(n).padStart(2, '0')).join('-');
        const today = new Date();
        const yesterday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1);
        const words = {[day(today)]: 'today', [day(yesterday)]: 'yesterday'}[published.slice(0, 10)];
        if (words) {
            time.textContent = `${words} ${published.slice(11, 16)}`;
        }
    }
    root.querySelectorAll('.mgpFacts time[datetime]').forEach(showWhen);

    const items = Array.from(root.querySelectorAll('.mgpPack'));
    if ('IntersectionObserver' in window) {
        const observer = new IntersectionObserver(entries => entries.forEach(entry => {
            if (entry.isIntersecting) {
                observer.unobserve(entry.target);
                showHoles(entry.target);
            }
        }), {rootMargin: '200px'});
        items.forEach(item => observer.observe(item));
    } else {
        items.forEach(showHoles);
    }

    root.querySelectorAll('.mgpWithdraw').forEach(button => button.addEventListener('click', function () {
        const item = button.closest('.mgpPack');
        if (!window.confirm(`Withdraw ${button.dataset.name}? Nobody can pick it anymore, `
            + 'games on it can still be finished.')) {
            return;
        }
        const notice = root.querySelector('.mgpNotice');
        const withdrawn = () => {
            item.remove();
            if (!root.querySelector('.mgpPack')) {
                root.querySelector('.mgpEmpty').hidden = false;
            }
        };
        notice.textContent = '';
        request(`${root.dataset.packsUrl}/${item.dataset.pack}`, {method: 'DELETE'}).then(withdrawn).catch(error => {
            // from an earlier look at the page: it's gone already, which is what was asked for
            if (error.status === 409) {
                withdrawn();
                notice.textContent = `${button.dataset.name} had been withdrawn already.`;
                return;
            }
            console.error('Withdrawing the pack failed:', error);
            window.alert(`Couldn't withdraw ${button.dataset.name}: ${error.message}`);
        });
    }));
})();
