/* Signal Groups - client.
   The answer key stays on the server; this only ever learns a grouping once it has
   been solved or the board is over. Interaction mirrors NYT Connections: tap a tile
   to select, submit three. Guesses are unlimited and wrong ones cost score. Tiles
   are video, so each carries its own play control. */
'use strict';

const el = (id) => document.getElementById(id);
const state = {
  deck: null,
  board: null,
  tiles: [],
  selected: new Set(),
  solvedIds: new Set(),
  mistakes: 0,
  over: false,
};

let toastTimer = null;

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw new Error(body.error || `request failed (${r.status})`);
  }
  return r.json();
}

/* ---------- rendering ---------- */

function renderBanner() {
  const b = el('banner');
  if (!state.deck || !state.deck.provisional) { b.innerHTML = ''; return; }
  b.innerHTML = `<div class="banner"><strong>Preview board &ndash; labels are not real</strong>${
    escapeHtml(state.deck.notice || '')}</div>`;
}

function renderLegend() {
  if (!state.deck) return;
  el('legend').innerHTML = state.deck.clusters.map((c) => `
    <div class="legend-row">
      <b>${escapeHtml(c.name)}</b>
      <span>${escapeHtml(c.signals.join(', '))}</span>
    </div>`).join('');
}

function renderDots() {
  // Lives are unlimited, so a row of spendable dots no longer means anything.
  // What matters now is the running mistake count, which IS the score - lower better.
  // Reads as "Score  2 mistakes  fewer is better" with the caption in index.html.
  const n = state.mistakes;
  el('dots').innerHTML =
    `<span class="scorenum">${n}</span>` +
    `<span class="scorelabel">mistake${n === 1 ? '' : 's'}</span>`;
}

function tileMarkup(t) {
  return `
    <div class="tile" data-id="${escapeAttr(t.id)}" role="button" tabindex="0"
         aria-pressed="false" aria-label="${escapeAttr(t.title + ', ' + fmtTime(t.at))}">
      <div class="tile-video" data-player>
        <video src="${escapeAttr(t.video)}" poster="${escapeAttr(t.poster)}"
               preload="none" playsinline disableremoteplayback
               disablepictureinpicture controlslist="nodownload noplaybackrate"></video>
        <div class="scrim"></div>
        <button class="play" data-play aria-label="Play clip">&#9654;</button>
      </div>
      <div class="tile-meta"><b>${escapeHtml(t.title)}</b>${t.year} &middot; ${fmtTime(t.at)}</div>
    </div>`;
}

function renderGrid() {
  const live = state.tiles.filter((t) => !state.solvedIds.has(t.id));
  el('grid').innerHTML = live.map(tileMarkup).join('');
  live.forEach((t) => {
    if (!state.selected.has(t.id)) return;
    const node = tileNode(t.id);
    if (node) { node.classList.add('selected'); node.setAttribute('aria-pressed', 'true'); }
  });
  syncControls();
}

function renderSolvedGroup(g) {
  const clips = g.clips.map((c) => {
    const top = (c.signals || [])
      .filter((s) => g.signals.includes(s.type))
      .sort((a, b) => rank(b.probability) - rank(a.probability))[0];
    const sigs = (c.signals || [])
      .filter((s) => s.type && s.type !== 'engagement' && s.type !== 'disengagement')
      .map((s) => `<span class="sig ${escapeAttr(s.probability || '')}">${escapeHtml(s.type)}</span>`)
      .join('');
    const why = top && top.rationale
      ? `<div class="mini-why">&ldquo;${escapeHtml(top.rationale)}&rdquo;</div>`
      : (c.label_source === 'placeholder'
        ? '<div class="mini-why">No inter1 analysis &ndash; preview board</div>' : '');
    return `<div class="mini">
        <img src="clips/${escapeAttr(c.id)}.jpg" alt="">
        <div class="mini-title">${escapeHtml(c.title)}</div>
        <div class="mini-meta">${c.year} &middot; ${fmtTime(c.at)}</div>
        ${why}<div class="mini-sigs">${sigs}</div>
      </div>`;
  }).join('');

  const d = Math.min(g.difficulty == null ? 0 : g.difficulty, 3);
  return `<div class="solved-row d${d}">
      <div class="solved-name">${escapeHtml(g.name)}</div>
      <div class="solved-sub">${escapeHtml(g.signals.join(', '))}</div>
      <div class="solved-clips">${clips}</div>
    </div>`;
}

function addSolved(g) {
  el('solved').insertAdjacentHTML('beforeend', renderSolvedGroup(g));
}

/* ---------- interaction ---------- */

function tileNode(id) {
  return document.querySelector(`.tile[data-id="${cssEsc(id)}"]`);
}

function stopAllVideos(except) {
  document.querySelectorAll('.tile-video').forEach((wrap) => {
    const vid = wrap.querySelector('video');
    if (vid && vid !== except) { vid.pause(); wrap.classList.remove('playing'); }
  });
}

function syncControls() {
  const per = (state.board && state.board.per_group) || 3;
  el('submit').disabled = state.over || state.selected.size !== per;
  el('clear').disabled = state.over || state.selected.size === 0;
}

function toggle(id) {
  if (state.over) return;
  const per = (state.board && state.board.per_group) || 3;
  const node = tileNode(id);
  if (state.selected.has(id)) {
    state.selected.delete(id);
    if (node) { node.classList.remove('selected'); node.setAttribute('aria-pressed', 'false'); }
  } else {
    if (state.selected.size >= per) return;
    state.selected.add(id);
    if (node) { node.classList.add('selected'); node.setAttribute('aria-pressed', 'true'); }
  }
  syncControls();
}

function toast(text, ms = 2200) {
  const t = el('toast');
  clearTimeout(toastTimer);
  if (!text) { t.innerHTML = ''; return; }
  t.innerHTML = `<div class="toast">${escapeHtml(text)}</div>`;
  toastTimer = setTimeout(() => { t.innerHTML = ''; }, ms);
}

async function submit() {
  if (state.over || !state.board) return;
  el('submit').disabled = true;
  const picked = [...state.selected];
  let res;
  try {
    res = await api('/api/guess', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ board: state.board.id, tiles: picked }),
    });
  } catch (e) {
    toast(e.message); syncControls(); return;
  }

  if (res.correct) {
    picked.forEach((id) => state.solvedIds.add(id));
    state.selected.clear();
    addSolved(res.group);
    renderGrid();
    if (state.solvedIds.size === state.tiles.length) {
      state.over = true;
      await finish(true);
    }
    return;
  }

  state.mistakes += 1;
  renderDots();
  picked.forEach((id) => {
    const n = tileNode(id);
    if (n) { n.classList.add('wrong'); setTimeout(() => n.classList.remove('wrong'), 470); }
  });
  toast(res.one_away ? 'One away...' : 'Not a group');

  // Infinite lives: a wrong guess costs score, never the run. The board is always
  // solvable, so the only ending is solving it - and the score is how few mistakes
  // it took to get there.
  syncControls();
}

async function finish(won) {
  syncControls();
  let reveal;
  try {
    reveal = await api(`/api/reveal/${encodeURIComponent(state.board.id)}`);
  } catch (e) { toast(e.message); return; }

  el('solved').innerHTML = reveal.groups.map(renderSolvedGroup).join('');
  el('grid').innerHTML = '';
  toast('');

  // On a preview board there is no inter1 reasoning to show, so don't claim there is.
  const provisional = state.deck && state.deck.provisional;
  const tail = provisional
    ? 'This is a preview board, so there is no inter1 reasoning to show.'
    : 'Each clip above shows what inter1 actually saw and heard.';
  // With unlimited lives the only way to arrive here is by solving it, so there is
  // no "Next time" branch any more - just how few mistakes it cost.
  const n = state.mistakes;
  el('endcard').innerHTML = `
      <div class="endcard">
        <h2>${n === 0 ? 'Perfect' : 'Solved it'}</h2>
        <p>All three groups with <strong>${n}</strong> mistake${n === 1 ? '' : 's'}. ${tail}</p>
        <div class="submitrow">
          <input id="pname" class="nameinput" maxlength="24" placeholder="your name"
                 autocomplete="off" />
          <button class="btn btn-primary" id="submitscore">Post score</button>
        </div>
        <div id="postmsg" class="postmsg"></div>
        <button class="btn" id="next">Next puzzle</button>
      </div>`;
  const next = el('next');
  if (next) next.onclick = () => nextBoard();

  const btn = el('submitscore');
  if (btn) {
    btn.onclick = async () => {
      const nameEl = el('pname');
      const name = (nameEl && nameEl.value.trim()) || 'anonymous';
      btn.disabled = true;                 // one post per finish, not one per click
      try {
        await api('/api/score', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, mistakes: n, board_id: state.board.id }),
        });
        el('postmsg').textContent = 'Posted to the scoreboard.';
        loadScoreboard();
      } catch (e) {
        btn.disabled = false;
        el('postmsg').textContent = e.message;
      }
    };
  }
  loadScoreboard();
}

async function loadScoreboard() {
  try {
    const data = await api('/api/scoreboard');
    const box = el('scoreboard');
    if (!box) return;
    if (!data.scores.length) {
      box.innerHTML = '<div class="sbempty">No scores yet. Be first.</div>';
      return;
    }
    box.innerHTML =
      '<h3>Scoreboard <span class="sbnote">fewest mistakes wins</span></h3>' +
      data.scores.slice(0, 10).map((r, i) => `
        <div class="sbrow">
          <span class="sbrank">${i + 1}</span>
          <span class="sbname">${escapeHtml(r.name)}</span>
          <span class="sbscore">${r.mistakes}</span>
        </div>`).join('');
  } catch (e) { /* scoreboard is non-critical; never block play on it */ }
}

// Live for everyone: poll so a score posted in another browser shows up here
// without a reload. Cheap - it is a small JSON file read behind a lock.
setInterval(loadScoreboard, 10000);

function nextBoard() {
  const pick = el('boardPick');
  pick.selectedIndex = (pick.selectedIndex + 1) % pick.options.length;
  loadBoard(pick.value);
}

/* ---------- boot ---------- */

async function loadBoard(id) {
  state.selected.clear();
  state.solvedIds.clear();
  state.mistakes = 0;
  state.over = false;
  el('solved').innerHTML = '';
  el('endcard').innerHTML = '';
  toast('');
  state.board = await api(`/api/board/${encodeURIComponent(id)}`);
  state.tiles = state.board.tiles;
  renderDots();
  renderGrid();
}

async function boot() {
  try {
    state.deck = await api('/api/deck');
  } catch (e) {
    el('grid').innerHTML = `<div class="banner" style="grid-column:1/-1">
      <strong>No puzzle built yet</strong>${escapeHtml(e.message)}</div>`;
    return;
  }
  renderBanner();
  renderLegend();

  const pick = el('boardPick');
  pick.innerHTML = state.deck.boards
    .map((b, i) => `<option value="${escapeAttr(b.id)}">${i + 1}</option>`).join('');
  pick.onchange = () => loadBoard(pick.value);

  if (!state.deck.boards.length) {
    el('grid').innerHTML = `<div class="banner" style="grid-column:1/-1">
      <strong>Not enough labelled clips</strong>Need at least three groups of three.</div>`;
    return;
  }
  await loadBoard(state.deck.boards[0].id);
}

/* Delegated: the grid re-renders constantly, so bind once at the document root. */
document.addEventListener('click', (ev) => {
  const playBtn = ev.target.closest('[data-play]');
  if (playBtn) {
    ev.stopPropagation();           // playing must not also select the tile
    const wrap = playBtn.closest('[data-player]');
    const vid = wrap && wrap.querySelector('video');
    if (!vid) return;
    if (vid.paused) {
      stopAllVideos(vid);
      vid.currentTime = 0;
      vid.play().then(() => wrap.classList.add('playing')).catch(() => {});
      vid.onended = () => wrap.classList.remove('playing');
      vid.onpause = () => wrap.classList.remove('playing');
    } else {
      vid.pause();
      wrap.classList.remove('playing');
    }
    return;
  }
  const tile = ev.target.closest('.tile');
  if (tile) toggle(tile.dataset.id);
});

document.addEventListener('keydown', (ev) => {
  if (ev.key !== 'Enter' && ev.key !== ' ') return;
  const tile = ev.target.closest && ev.target.closest('.tile');
  if (!tile) return;
  ev.preventDefault();
  toggle(tile.dataset.id);
});

el('submit').onclick = submit;
el('clear').onclick = () => {
  state.selected.clear();
  document.querySelectorAll('.tile.selected').forEach((n) => {
    n.classList.remove('selected'); n.setAttribute('aria-pressed', 'false');
  });
  syncControls();
};
el('shuffle').onclick = () => {
  const live = state.tiles.filter((t) => !state.solvedIds.has(t.id));
  const solved = state.tiles.filter((t) => state.solvedIds.has(t.id));
  for (let i = live.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [live[i], live[j]] = [live[j], live[i]];
  }
  state.tiles = [...solved, ...live];
  renderGrid();
};

/* ---------- helpers ---------- */
function rank(p) { return p === 'high' ? 3 : p === 'medium' ? 2 : p === 'low' ? 1 : 0; }
function fmtTime(s) {
  if (s == null) return '';
  const m = Math.floor(s / 60), sec = Math.floor(s % 60);
  return `${m}:${String(sec).padStart(2, '0')}`;
}
function escapeHtml(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
const escapeAttr = escapeHtml;
function cssEsc(s) { return String(s).replace(/["\\]/g, '\\$&'); }

boot();
