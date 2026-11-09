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

    function polygon(ctx, poly) {
        ctx.beginPath();
        poly.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])));
        ctx.closePath();
    }

    // the hole as it lies before anybody putts, in the game's colours (see drawHole in minigolf.js)
    function drawHole(canvas, h) {
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        canvas.width = W * SCALE * dpr;
        canvas.height = H * SCALE * dpr;
        const ctx = canvas.getContext('2d');
        ctx.scale(SCALE * dpr, SCALE * dpr);
        ctx.fillStyle = '#2e7d32';
        ctx.fillRect(0, 0, W, H);
        polygon(ctx, h.outline);
        ctx.fillStyle = '#4caf50';
        ctx.fill();
        ctx.lineWidth = 8;
        ctx.strokeStyle = '#8d6e63';
        ctx.stroke();
        (h.sand || []).forEach(r => {
            ctx.fillStyle = '#e6d28a';
            ctx.fillRect(r[0], r[1], r[2], r[3]);
        });
        (h.water || []).forEach(r => {
            ctx.fillStyle = '#1e88e5';
            ctx.fillRect(r[0], r[1], r[2], r[3]);
        });
        (h.boosts || []).forEach(b => {
            ctx.fillStyle = 'rgba(255,235,59,0.5)';
            ctx.fillRect(b[0], b[1], b[2], b[3]);
        });
        (h.blocks || []).forEach(b => {
            polygon(ctx, b);
            ctx.fillStyle = h.house ? '#c62828' : '#8d6e63';
            ctx.fill();
        });
        (h.sliders || []).forEach(s => {
            ctx.fillStyle = '#6d4c41';
            ctx.fillRect(s.x, s.y, s.w, s.h);
        });
        (h.bumpers || []).forEach(b => {
            ctx.beginPath();
            ctx.arc(b[0], b[1], b[2], 0, Math.PI * 2);
            ctx.fillStyle = '#e91e63';
            ctx.fill();
        });
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
        (h.starts || [h.start]).forEach(t => {
            ctx.fillStyle = '#fff';
            ctx.beginPath();
            ctx.arc(t[0], t[1], 9, 0, Math.PI * 2);
            ctx.fill();
        });
        ctx.fillStyle = '#111';
        ctx.beginPath();
        ctx.arc(h.cup[0], h.cup[1], 12, 0, Math.PI * 2);
        ctx.fill();
    }

    function showHoles(item) {
        const url = root.dataset.courseUrl.replace(/-$/, encodeURIComponent(item.dataset.course));
        const list = item.querySelector('.mgpHoles');
        fetch(url, {credentials: 'include'}).then(response => {
            if (!response.ok || response.redirected) {
                throw new Error(`HTTP ${response.status}`);
            }
            return response.json();
        }).then(data => {
            data.holes.forEach((h, i) => {
                const li = document.createElement('li');
                const link = document.createElement('a');
                link.href = `${item.dataset.editorUrl}&hole=${i + 1}`;
                link.title = `Test hole ${i + 1} in the editor`;
                link.setAttribute('aria-label', `Test hole ${i + 1}, ${h.name}, par ${h.par}`);
                const canvas = document.createElement('canvas');
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
            li.textContent = "Couldn't load the holes.";
            list.appendChild(li);
        });
    }

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
        fetch(`${root.dataset.packsUrl}/${item.dataset.pack}`, {method: 'DELETE', credentials: 'include'})
            .then(response => {
                if (!response.ok || response.redirected) {
                    throw new Error(`HTTP ${response.status}`);
                }
                item.remove();
            }).catch(error => {
                window.alert(`Couldn't withdraw the pack: ${error.message}`);
            });
    }));
})();
