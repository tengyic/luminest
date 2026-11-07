/* Luminfest workbench client. Vanilla JS, no build step.
 *
 * Layout: sidebar | main (canvas + transcript + composer) | details.
 * Core interaction: hover-to-select on the simulation iframe, then
 * "Explain this" (agent chat with selection context) or
 * "Request change…" (categorized change request, student-bounded).
 */
'use strict';

(() => {
  const $ = (id) => document.getElementById(id);

  const els = {
    sidebar: $('sidebar'), sidebarToggle: $('sidebar-toggle'),
    simList: $('sim-list'), sessionList: $('session-list'), newSession: $('new-session-btn'),
    roleToggle: $('role-toggle'), authRow: $('auth-row'), tokenInput: $('token-input'), tokenSave: $('token-save'),
    telemetryRow: $('telemetry-row'), telemetryToggle: $('telemetry-toggle'),
    connDot: $('conn-dot'), connText: $('conn-text'),
    simTitle: $('sim-title'), statusPill: $('status-pill'), simRefresh: $('sim-refresh'),
    canvasStage: $('canvas-stage'), frame: $('sim-frame'), overlay: $('sim-overlay'),
    hoverBox: $('hover-box'), selectBox: $('select-box'), popover: $('select-popover'),
    popoverLabel: $('popover-label'), btnExplain: $('btn-explain'), btnRequest: $('btn-request'),
    canvasEmpty: $('canvas-empty'), canvasNote: $('canvas-note'),
    transcript: $('transcript'), cancelBtn: $('cancel-btn'),
    boundaryNote: $('boundary-note'),
    studentComposer: $('student-composer'), teacherComposer: $('teacher-composer'),
    categoryRow: $('category-row'), studentNote: $('student-note'), studentSend: $('student-send'),
    studentHint: $('student-hint'), teacherInput: $('teacher-input'), teacherSend: $('teacher-send'),
    detailStatus: $('detail-status'), detailSim: $('detail-sim'), detailVersion: $('detail-version'),
    detailRole: $('detail-role'), selectionInfo: $('selection-info'),
    requestsInfo: $('requests-info'), toolsInfo: $('tools-info'),
    courseStudio: $('course-studio'), studioFile: $('studio-file'), studioUrl: $('studio-url'),
    studioTitle: $('studio-title'), studioSubject: $('studio-subject'),
    studioPreview: $('studio-preview'), studioSave: $('studio-save'),
    studioStatus: $('studio-status'), studioPlan: $('studio-plan'),
    taStudio: $('ta-studio'), taConcept: $('ta-concept'), taMessage: $('ta-message'),
    taSend: $('ta-send'), taStatus: $('ta-status'), taJobs: $('ta-jobs'), taResults: $('ta-results'),
    devToggle: $('dev-toggle'), devPanel: $('dev-panel'), devMode: $('dev-mode'), devRaw: $('dev-raw'),
    toast: $('toast'),
  };

  const STORAGE = { sessions: 'luminfest.sessions.v1', token: 'luminfest.token', role: 'luminfest.role' };

  const state = {
    role: sessionStorage.getItem(STORAGE.role) || 'student',
    // The role the *server* will hold this session to. `null` means "not asked yet";
    // the local toggle is presentation only and never decides a permission.
    serverRole: null,
    token: sessionStorage.getItem(STORAGE.token) || '',
    apiOnline: false,
    sims: [],
    sessions: [],
    activeSessionId: null,
    activeSimId: null,
    activeSimVersion: null,
    status: 'idle',           // idle | running | error
    devMode: false,
    lastSelection: null,      // {kind, selector, text, rect}
    pendingCategory: null,
    controller: null,         // AbortController for the running turn
  };

  // ------------------------------------------------------------ utilities

  function toast(message, ms = 3200) {
    els.toast.textContent = message;
    els.toast.classList.remove('hidden');
    clearTimeout(toast._t);
    toast._t = setTimeout(() => els.toast.classList.add('hidden'), ms);
  }

  function setStatus(status) {
    state.status = status;
    els.statusPill.dataset.status = status;
    els.statusPill.textContent = status;
    els.detailStatus.textContent = status;
    els.cancelBtn.classList.toggle('hidden', status !== 'running');
    els.studentSend.disabled = status === 'running';
    els.teacherSend.disabled = status === 'running';
  }

  function authHeaders(extra = {}) {
    const headers = { 'Content-Type': 'application/json', ...extra };
    if (state.token) headers.Authorization = 'Bearer ' + state.token;
    return headers;
  }

  async function api(path, options = {}) {
    const response = await fetch(path, { ...options, headers: authHeaders(options.headers || {}) });
    if (response.status === 401) {
      els.authRow.classList.remove('hidden');
      throw new Error('Unauthorized — paste a valid access token in the sidebar');
    }
    if (!response.ok) {
      let detail = response.statusText;
      try { detail = (await response.json()).detail || detail; } catch { /* keep */ }
      const err = new Error(detail);
      err.status = response.status;
      throw err;
    }
    return response.json();
  }

  function saveSessions() {
    try { localStorage.setItem(STORAGE.sessions, JSON.stringify(state.sessions)); }
    catch { /* storage full — history stays in memory for this tab */ }
  }

  function activeSession() {
    return state.sessions.find((s) => s.id === state.activeSessionId) || null;
  }

  function newSession(title = 'New session') {
    const session = {
      id: 's-' + Date.now() + '-' + Math.random().toString(36).slice(2, 7),
      title, createdAt: Date.now(), simId: state.activeSimId, messages: [],
    };
    state.sessions.unshift(session);
    state.activeSessionId = session.id;
    saveSessions();
    renderSessions();
    renderTranscript();
    return session;
  }

  function sessionForCurrentTurn() {
    return activeSession() || newSession();
  }

  // ------------------------------------------------------------- messages

  function pushMessage(message) {
    const session = sessionForCurrentTurn();
    session.messages.push(message);
    if (message.role === 'user' && session.messages.filter((m) => m.role === 'user').length === 1) {
      session.title = (message.text || '').slice(0, 40) || session.title;
    }
    saveSessions();
    renderTranscript();
  }

  function currentAssistant() {
    const session = activeSession();
    if (!session) return null;
    const last = session.messages[session.messages.length - 1];
    return last && last.role === 'assistant' && last.live ? last : null;
  }

  function renderTranscript() {
    const session = activeSession();
    els.transcript.textContent = '';
    if (!session) return;
    for (const message of session.messages) {
      els.transcript.appendChild(renderMessage(message));
    }
    els.transcript.scrollTop = els.transcript.scrollHeight;
  }

  function renderMessage(message) {
    const div = document.createElement('div');
    div.className = 'msg ' + message.role;
    if (message.role === 'assistant') {
      if (state.devMode && message.reasoning) {
        const r = document.createElement('div');
        r.className = 'reasoning';
        r.textContent = 'reasoning: ' + message.reasoning;
        div.appendChild(r);
      }
      div.append(document.createTextNode(message.text || ''));
      for (const tool of message.tools || []) div.appendChild(renderToolCard(tool));
      if (message.context) {
        const c = document.createElement('div');
        c.className = 'msg-context';
        c.textContent = 'selection: ' + message.context;
        div.appendChild(c);
      }
    } else if (message.role === 'user') {
      div.append(document.createTextNode(message.text || ''));
      if (message.selection) {
        const c = document.createElement('div');
        c.className = 'msg-context';
        c.textContent = 'selection: ' + JSON.stringify(message.selection);
        div.appendChild(c);
      }
    } else {
      div.textContent = message.text || '';
    }
    return div;
  }

  function renderToolCard(tool) {
    const card = document.createElement('details');
    card.className = 'tool-card';
    if (tool.ok !== undefined) card.dataset.ok = String(tool.ok);
    const summary = document.createElement('summary');
    const state2 = document.createElement('span');
    state2.className = 'tool-state';
    state2.textContent = tool.ok === undefined ? 'running' : tool.ok ? 'ok' : 'error';
    summary.textContent = '🔧 ' + tool.name + ' ';
    summary.appendChild(state2);
    card.appendChild(summary);
    const body = document.createElement('div');
    body.className = 'tool-body';
    if (tool.arguments !== undefined) {
      const pre = document.createElement('pre');
      pre.textContent = 'args: ' + safeJson(tool.arguments);
      body.appendChild(pre);
    }
    if (tool.summary !== undefined) {
      const pre = document.createElement('pre');
      pre.textContent = 'result: ' + tool.summary + (tool.data ? '\n' + safeJson(tool.data) : '');
      body.appendChild(pre);
    }
    card.appendChild(body);
    return card;
  }

  function safeJson(value) {
    try { return typeof value === 'string' ? value : JSON.stringify(value); }
    catch { return String(value); }
  }

  // ------------------------------------------------------------ simulation

  // An iframe navigation cannot carry the Authorization header — only `src` travels.
  // So the canvas exchanges its session bearer for a short-lived, single-simulation
  // token and puts *that* in the URL. The bearer itself never enters a URL, where it
  // would persist in history and in whatever referrer the simulation emits.
  async function simFrameUrl(simId, version) {
    const suffix = (version === undefined || version === null || version === '')
      ? '' : '&version=' + encodeURIComponent(version);
    if (!state.apiOnline) return `/web/sims/${simId}.html`;
    try {
      const grant = await api(`/api/v1/sims/${simId}/frame-token`, { method: 'POST' });
      if (grant && grant.url) return grant.url + suffix;
    } catch (err) {
      // Say why the canvas is empty. A silent blank frame is indistinguishable from a
      // broken simulation, and the usual cause is an expired or missing session.
      noteCanvas('Could not authorise the simulation frame: ' + err.message);
    }
    // Development / anonymous fallback only: production `principal()` refuses this
    // request, and the note above has already named the reason.
    return `/api/v1/sims/${simId}/raw` + (suffix ? '?' + suffix.slice(1) : '');
  }

  async function loadSimList() {
    try {
      const data = await api('/api/v1/sims');
      state.sims = data.sims || [];
      state.apiOnline = true;
      setConn(true, 'API connected');
    } catch (err) {
      state.apiOnline = false;
      state.sims = [{ id: 'supply-demand', title: 'Supply & Demand (local seed)', latest_version: 0 }];
      setConn(false, 'API offline — local seed only');
      if (err.message && !/Failed to fetch|NetworkError/.test(err.message)) toast(err.message);
    }
    renderSimList();
    if (!state.activeSimId && state.sims.length) selectSim(state.sims[0].id);
  }

  function setConn(ok, text) {
    els.connDot.className = 'conn-dot ' + (ok ? 'ok' : 'bad');
    els.connText.textContent = text;
  }

  function renderSimList() {
    els.simList.textContent = '';
    for (const sim of state.sims) {
      const li = document.createElement('li');
      if (sim.id === state.activeSimId) li.classList.add('active');
      const icon = document.createElement('span'); icon.className = 'sim-icon'; icon.textContent = '▦';
      const name = document.createElement('span'); name.textContent = sim.title || sim.id;
      const meta = document.createElement('span'); meta.className = 'sim-meta';
      meta.textContent = 'v' + (sim.latest_version ?? sim.version ?? '?');
      li.append(icon, name, meta);
      li.addEventListener('click', () => selectSim(sim.id));
      els.simList.appendChild(li);
    }
  }

  async function selectSim(simId) {
    state.activeSimId = simId;
    state.lastSelection = null;
    clearSelection();
    hidePopover();
    renderSimList();
    els.canvasEmpty.classList.add('hidden');
    const session = activeSession();
    if (session) { session.simId = simId; saveSessions(); }
    await refreshSimMeta(true);
  }

  async function refreshSimMeta(force = false) {
    const simId = state.activeSimId;
    if (!simId) return;
    let meta = null;
    if (state.apiOnline) {
      try { meta = await api(`/api/v1/sims/${simId}`); }
      catch { /* keep current view; offline fallback below */ }
    }
    if (meta) {
      const version = meta.latest_version ?? meta.version;
      const changed = state.activeSimVersion !== null && version !== state.activeSimVersion;
      state.activeSimVersion = version;
      els.detailSim.textContent = meta.title || simId;
      els.detailVersion.textContent = 'v' + version;
      els.simTitle.textContent = (meta.title || simId) + ' · v' + version;
      if (meta.requests !== undefined) els.requestsInfo.textContent = `${meta.requests} filed request(s)`;
      const cached = state.sims.find((s) => s.id === simId);
      if (cached) { cached.latest_version = version; cached.title = meta.title; renderSimList(); }
      if (changed || force) {
        els.frame.src = await simFrameUrl(simId, version);
        noteCanvas('Simulation reloaded at v' + version);
      }
    } else {
      els.frame.src = await simFrameUrl(simId);
      els.detailSim.textContent = simId;
      els.detailVersion.textContent = 'local';
      els.simTitle.textContent = simId + ' (offline seed)';
      if (force) noteCanvas('Loaded local seed copy — API offline');
    }
  }

  function noteCanvas(text) {
    els.canvasNote.textContent = text;
    els.canvasNote.classList.remove('hidden');
    clearTimeout(noteCanvas._t);
    noteCanvas._t = setTimeout(() => els.canvasNote.classList.add('hidden'), 4000);
  }

  // --------------------------------------- hover-to-select on the iframe
  // The iframe is sandboxed with allow-scripts ONLY — deliberately not
  // allow-same-origin, so neither side can touch the other's document or
  // storage (the parent's token is unreachable from sim script). Selection
  // therefore arrives via postMessage from the server-injected agent bridge
  // (web/luminfest-agent.js): {type:'luminfest:hover'|'luminfest:select'|'luminfest:ready'}.
  // Every message is validated: it must come from the sim frame's own
  // contentWindow and carry a known luminfest: type. Graph series are picked
  // through the data-series convention (see README). If no bridge announces
  // itself (e.g. the sim was loaded without the API), we say so instead of
  // pretending selection works.

  let bridgeReady = false;
  let bridgeTimer = null;
  // The document the bridge announced itself for. The injected script runs while
  // the frame is still parsing, so `luminfest:ready` is delivered *before* the
  // frame's `load` event — and a naive reset in the load handler turned every
  // working simulation into "bridge is missing" two seconds later.
  let bridgeSrc = '';

  els.frame.addEventListener('load', () => {
    if (els.frame.src !== bridgeSrc) bridgeReady = false;
    clearTimeout(bridgeTimer);
    bridgeTimer = setTimeout(() => {
      if (!bridgeReady) {
        noteCanvas('Hover-select unavailable: this simulation was not served ' +
                   'through the API, so the agent bridge is missing.');
      }
    }, 2000);
  });

  window.addEventListener('message', (event) => {
    // Only trust messages originating from the sim frame itself.
    if (event.source !== els.frame.contentWindow) return;
    const data = event.data;
    if (!data || typeof data.type !== 'string' || !data.type.startsWith('luminfest:')) return;
    if (data.type === 'luminfest:ready') {
      bridgeReady = true;
      bridgeSrc = els.frame.src;
      clearTimeout(bridgeTimer);
      return;
    }
    if (data.type === 'luminfest:hover' && data.rect) {
      placeBox(els.hoverBox, data.rect);
      els.hoverBox.classList.remove('hidden');
      return;
    }
    if (data.type === 'luminfest:select' && data.selection && data.selection.selector) {
      applySelection(data.selection);
    }
  });

  function placeBox(box, rect) {
    box.style.left = rect.x + 'px';
    box.style.top = rect.y + 'px';
    box.style.width = Math.max(rect.width, 4) + 'px';
    box.style.height = Math.max(rect.height, 4) + 'px';
  }

  function applySelection(selection) {
    state.lastSelection = selection;
    placeBox(els.selectBox, selection.rect);
    els.selectBox.classList.remove('hidden');
    els.selectionInfo.innerHTML = '';
    const strong = document.createElement('b');
    strong.textContent = selection.kind + ' · ' + selection.selector;
    els.selectionInfo.appendChild(strong);
    els.selectionInfo.appendChild(document.createTextNode('\n' + (selection.text || '(no text)') +
      `\nrect: ${selection.rect.x},${selection.rect.y} ${selection.rect.w}×${selection.rect.h}`));
    showPopover(selection.rect);
    renderTranscript(); // dev-mode reasoning visibility may change
  }

  function clearSelection() {
    els.selectBox.classList.add('hidden');
    els.hoverBox.classList.add('hidden');
    state.lastSelection = null;
  }

  function showPopover(rect) {
    els.popoverLabel.textContent = state.lastSelection
      ? `${state.lastSelection.kind}: ${state.lastSelection.selector}` : '';
    els.popover.classList.remove('hidden');
    const stage = els.canvasStage.getBoundingClientRect();
    const left = Math.min(rect.x + rect.width + 10, stage.width - 190);
    const top = Math.min(rect.y + 6, stage.height - 110);
    els.popover.style.left = Math.max(8, left) + 'px';
    els.popover.style.top = Math.max(8, top) + 'px';
  }

  function hidePopover() {
    els.popover.classList.add('hidden');
  }

  // Clicks elsewhere on the overlay dismiss the popover.
  els.overlay.addEventListener('mousedown', (event) => {
    if (!els.popover.contains(event.target)) hidePopover();
  });

  // ------------------------------------------------------------- actions

  els.btnExplain.addEventListener('click', () => {
    const selection = state.lastSelection;
    hidePopover();
    if (!selection) { toast('Nothing selected'); return; }
    const label = selection.text || selection.selector;
    const message = `Explain this ${selection.kind} ("${label}") in the current simulation.`;
    pushMessage({ role: 'user', text: message, selection });
    runAgentTurn({ message, selection });
  });

  els.btnRequest.addEventListener('click', () => {
    hidePopover();
    if (state.role === 'teacher') {
      setRole('student', { keepBoundary: false });
      toast('Switched to Student composer to file a categorized change request');
    }
    els.studentComposer.scrollIntoView({ block: 'nearest' });
    els.studentHint.className = 'student-hint';
    els.studentHint.textContent = state.lastSelection
      ? `Attached selection: ${state.lastSelection.selector} — pick a category and describe the problem.`
      : 'Pick a category and describe the problem (optionally select something on the canvas first).';
    els.studentNote.focus();
  });

  // ------------------------------------------------------------- streaming
  // POST /api/v1/agent/stream (SSE). Event types: turn_start, message_delta
  // (the reasoning channel rides on it with channel:'reasoning'), tool_call,
  // tool_result, turn_end, error.

  async function runAgentTurn({ message, selection }) {
    const session = sessionForCurrentTurn();
    pushMessage({ role: 'assistant', text: '', tools: [], live: true });
    setStatus('running');
    state.controller = new AbortController();

    // Server contract (main.py AgentTurnInput): {session_id, message,
    // developer_mode, context}. `context` carries client-side state (selection,
    // sim_id, role) that tools may read; it is never sent to the model as
    // instructions. History is deliberately not replayed — the harness memory
    // tools carry it, so the server owns that source of truth.
    const body = {
      session_id: session.id.slice(0, 64),
      message,
      developer_mode: state.devMode,
      context: { selection: selection || null, sim_id: state.activeSimId, role: state.role },
    };

    try {
      const response = await fetch('/api/v1/agent/stream', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify(body),
        signal: state.controller.signal,
      });
      if (!response.ok || !response.body) {
        let detail = response.statusText;
        try { detail = (await response.json()).detail || detail; } catch { /* keep */ }
        throw new Error(`Agent stream unavailable (${response.status}): ${detail}`);
      }
      await consumeSse(response, session);
      finalizeAssistant(session, 'complete');
      setStatus('idle');
    } catch (err) {
      const live = currentAssistant();
      if (err.name === 'AbortError') {
        if (live) { live.text = live.text || '(cancelled)'; }
        pushMessage({ role: 'system', text: 'Turn cancelled.' });
        finalizeAssistant(session, 'cancelled');
        setStatus('idle');
      } else {
        if (live) { live.text = live.text || '(no response)'; }
        pushMessage({ role: 'system', text: 'Error: ' + err.message });
        finalizeAssistant(session, 'error');
        setStatus('error');
      }
    } finally {
      state.controller = null;
      refreshSimMeta(); // a finished turn may have bumped the sim version
    }
  }

  async function consumeSse(response, session) {
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let boundary;
      while ((boundary = buffer.indexOf('\n\n')) !== -1) {
        const rawEvent = buffer.slice(0, boundary);
        buffer = buffer.slice(boundary + 2);
        handleSseEvent(rawEvent, session);
      }
    }
  }

  function handleSseEvent(rawEvent, session) {
    let eventName = 'message';
    const dataLines = [];
    for (const line of rawEvent.split('\n')) {
      if (line.startsWith('event:')) eventName = line.slice(6).trim();
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
    }
    if (!dataLines.length) return;
    let data;
    try { data = JSON.parse(dataLines.join('\n')); } catch { data = { text: dataLines.join('\n') }; }
    if (els.devRaw.checked) console.log('[sse]', eventName, data);

    const live = currentAssistant() || { role: 'assistant', text: '', tools: [], live: true };
    if (!live.tools) live.tools = [];

    switch (eventName) {
      case 'turn_start':
        setStatus('running');
        break;
      case 'message_delta':
        // The reasoning channel rides on message_delta with channel:'reasoning'
        // (agent_loop.py), never on the wire without developer_mode.
        if (data.channel === 'reasoning') {
          live.reasoning = (live.reasoning || '') + (data.text || '');
        } else {
          live.text += data.text || '';
        }
        break;
      case 'tool_call':
        live.tools.push({ id: data.id, name: data.name, arguments: data.arguments });
        els.toolsInfo.textContent = `${data.name} — running`;
        break;
      case 'tool_result': {
        const card = live.tools.find((t) => t.id === data.id) ||
                     live.tools[live.tools.length - 1];
        if (card) { card.ok = !!data.ok; card.summary = data.summary; card.data = data.data; }
        els.toolsInfo.textContent = `${data.name} — ${data.ok ? 'ok' : 'error'}: ${data.summary || ''}`.slice(0, 200);
        break;
      }
      case 'turn_end':
        // The generator has no return channel: the final assistant text also
        // travels on turn_end.content — use it if deltas did not carry it.
        if (!live.text && data.content) live.text = data.content;
        break;
      case 'error':
        live.text += (live.text ? '\n' : '') + '⚠ ' + (data.message || 'stream error');
        break;
      default:
        break;
    }
    renderTranscript();
  }

  function finalizeAssistant(session, reason) {
    const last = session.messages[session.messages.length - 1];
    if (last && last.role === 'assistant') {
      last.live = false;
      last.done = reason;
    }
    saveSessions();
    renderTranscript();
  }

  // ------------------------------------------------------------ cancelling

  els.cancelBtn.addEventListener('click', () => {
    if (state.controller) state.controller.abort();
  });

  // -------------------------------------------------------------- composer

  // The role switch is presentation. The server decides, from the account, and a
  // student flipping it to Teacher used to see the teacher panels and then get every
  // request refused. Ask the server what it will enforce, then show only that.
  async function loadServerRole() {
    try {
      const info = await api('/api/v1/role');
      state.serverRole = info.role || 'student';
    } catch {
      // No usable session: the server would refuse both teacher and student writes,
      // so present the student pane and let the composer explain itself.
      state.serverRole = 'student';
    }
    applyRoleGate();
  }

  function applyRoleGate() {
    const teacherBtn = els.roleToggle.querySelector('.role-btn[data-role="teacher"]');
    const allowed = state.serverRole === 'teacher';
    if (teacherBtn) {
      teacherBtn.disabled = !allowed;
      teacherBtn.setAttribute('aria-disabled', String(!allowed));
      teacherBtn.title = allowed
        ? 'Teacher tools are enabled for this account'
        : 'Teacher tools need a teacher account — the server decides this, not this switch.';
    }
    if (!allowed && state.role === 'teacher') setRole('student');
  }

  // ------------------------------------------------- interaction telemetry
  //
  // The web surface had no click channel at all, so `/api/v1/attention/window`
  // could only ever see the macOS app. This sends the same `interaction` events
  // the native client sends, under the same closed grammar (web/telemetry.js),
  // and only when the account has said yes. `/events` answers 403 without
  // consent, so arming reads `telemetry_consent` from `/me` - the checkbox is a
  // request to change that, not the permission itself.
  const telemetry = window.LuminfestTelemetry || null;
  let telemetryQueue = null;
  let telemetryTimer = null;

  function telemetrySend(batch) {
    api('/api/v1/events', { method: 'POST', body: JSON.stringify({ events: batch }) })
      .catch((error) => {
        // 403 means consent was withdrawn (another tab, or the account itself);
        // retrying a request the server keeps refusing only adds noise.
        if (error && error.status === 403) armTelemetry(false);
      });
  }

  function armTelemetry(on) {
    if (!telemetry) return;
    if (on && !telemetryQueue) {
      telemetryQueue = telemetry.createQueue({ send: telemetrySend, max: 40 });
      telemetryTimer = setInterval(() => telemetryQueue.flush(), 5000);
      document.addEventListener('pointerdown', onTelemetryPointer, true);
      document.addEventListener('keydown', onTelemetryKey, true);
      window.addEventListener('blur', onTelemetryBlur);
      window.addEventListener('focus', onTelemetryFocus);
    } else if (!on && telemetryQueue) {
      telemetryQueue.flush();
      clearInterval(telemetryTimer);
      telemetryTimer = null;
      telemetryQueue = null;
      document.removeEventListener('pointerdown', onTelemetryPointer, true);
      document.removeEventListener('keydown', onTelemetryKey, true);
      window.removeEventListener('blur', onTelemetryBlur);
      window.removeEventListener('focus', onTelemetryFocus);
    }
  }

  function onTelemetryPointer(event) {
    if (!telemetryQueue || telemetry.isSensitive(event.target)) return;
    telemetryQueue.record('click', telemetry.targetFor(event.target));
  }

  function onTelemetryKey(event) {
    // No key, no character: the channel records that a key was pressed and
    // where. Typing into a password or email field is not even that.
    if (!telemetryQueue || telemetry.isSensitive(event.target)) return;
    telemetryQueue.record('key', telemetry.targetFor(event.target));
  }

  function onTelemetryBlur() { if (telemetryQueue) telemetryQueue.record('blur'); }
  function onTelemetryFocus() { if (telemetryQueue) telemetryQueue.record('focus'); }

  async function loadTelemetryConsent() {
    if (!els.telemetryRow || !els.telemetryToggle) return;
    if (!state.token) {
      els.telemetryRow.classList.add('hidden');
      armTelemetry(false);
      return;
    }
    try {
      const me = await api('/api/v1/me');
      const on = me.telemetry_consent === true;
      els.telemetryRow.classList.remove('hidden');
      els.telemetryToggle.checked = on;
      armTelemetry(on);
    } catch {
      els.telemetryRow.classList.add('hidden');
      armTelemetry(false);
    }
  }

  function setRole(role) {
    if (role === 'teacher' && state.serverRole && state.serverRole !== 'teacher') {
      toast('Teacher tools are not available for this account.');
      role = 'student';
    }
    state.role = role;
    sessionStorage.setItem(STORAGE.role, role);
    for (const btn of els.roleToggle.querySelectorAll('.role-btn')) {
      btn.setAttribute('aria-selected', String(btn.dataset.role === role));
    }
    const student = role === 'student';
    els.studentComposer.classList.toggle('hidden', !student);
    els.teacherComposer.classList.toggle('hidden', student);
    els.courseStudio.classList.toggle('hidden', student);
    els.taStudio.classList.toggle('hidden', student);
    if (!student) { loadTaConcepts(); taPoll(); }
    els.boundaryNote.textContent = student
      ? 'Students file change requests; creating or rewriting a simulation belongs to your teacher.'
      : 'Teacher mode: you can create and modify simulations freely.';
    els.detailRole.textContent = role;
  }

  els.roleToggle.addEventListener('click', (event) => {
    const btn = event.target.closest('.role-btn');
    if (btn) setRole(btn.dataset.role);
  });

  els.categoryRow.addEventListener('click', (event) => {
    const btn = event.target.closest('.cat-btn');
    if (!btn) return;
    state.pendingCategory = btn.dataset.category;
    for (const el of els.categoryRow.querySelectorAll('.cat-btn')) {
      el.classList.toggle('active', el === btn);
    }
    els.studentHint.className = 'student-hint';
    els.studentHint.textContent = '';
  });

  function studentBlock(category) {
    // Hard boundary: students may only file the four review categories.
    // Creation/restructuring belongs to the teacher — say why, then offer the
    // correct path instead of failing silently.
    els.studentHint.className = 'student-hint error';
    els.studentHint.textContent = category === 'create' || category === 'restructure'
      ? 'Creating or restructuring simulations belongs to your teacher. File a Bug, Wrong info, Ugly or Hard-to-use request instead.'
      : 'Pick a category first (Bug / Wrong info / Ugly / Hard to use).';
  }

  async function sendStudentRequest() {
    const category = state.pendingCategory;
    if (!category || !(category === 'bug' || category === 'wrong_info' || category === 'ugly' || category === 'ux')) {
      studentBlock(category || null);
      return;
    }
    if (state.status === 'running') { toast('Wait for the current turn to finish'); return; }
    const note = els.studentNote.value.trim();
    if (!note && !state.lastSelection) {
      studentBlock(null);
      return;
    }
    const simId = state.activeSimId;
    if (!simId) { toast('Select a simulation first'); return; }

    const payload = { category, note, role: state.role, selection: state.lastSelection || null };
    els.studentSend.disabled = true;
    try {
      if (state.apiOnline) {
        const record = await api(`/api/v1/sims/${simId}/requests`, { method: 'POST', body: JSON.stringify(payload) });
        pushMessage({ role: 'user', text: `[${category}] ${note || '(selection only)'}`, selection: payload.selection });
        pushMessage({ role: 'system', text: `Change request filed: ${record.id} (sim v${record.sim_version})` });
        els.requestsInfo.textContent = 'request filed just now';
      } else {
        pushMessage({ role: 'user', text: `[${category}] ${note || '(selection only)'}`, selection: payload.selection });
        pushMessage({ role: 'system', text: 'API offline — request kept locally, will need to be re-sent.' });
      }
      els.studentNote.value = '';
      state.pendingCategory = null;
      els.studentHint.className = 'student-hint';
      els.studentHint.textContent = '';
      for (const el of els.categoryRow.querySelectorAll('.cat-btn')) el.classList.remove('active');
    } catch (err) {
      if (err.status === 403) {
        studentBlock(category);
      } else {
        els.studentHint.className = 'student-hint error';
        els.studentHint.textContent = 'Could not file request: ' + err.message;
      }
    } finally {
      els.studentSend.disabled = state.status === 'running';
    }
  }

  function sendTeacherMessage() {
    const text = els.teacherInput.value.trim();
    if (!text || state.status === 'running') return;
    pushMessage({ role: 'user', text, selection: state.lastSelection || null });
    els.teacherInput.value = '';
    runAgentTurn({ message: text, selection: state.lastSelection });
  }

  // ------------------------------------------------------- course studio

  // The plan the server built from the teacher's own file. Held so the save
  // button sends the same bytes again rather than trusting a client-side copy
  // of what the server read.
  let studioPlan = null;

  function studioStatus(text, cls = '') {
    els.studioStatus.textContent = text;
    els.studioStatus.className = 'studio-status' + (cls ? ' ' + cls : '');
  }

  function renderPlan(plan) {
    const concepts = (plan.concepts || []).map((concept) => `
      <li>${escapeHtml(concept.title || concept.id || '')}
        <span class="kind">${escapeHtml(concept.kind || '')}</span></li>`).join('');
    const stats = plan.graph_stats || {};
    els.studioPlan.innerHTML = `
      <div class="plan-stats">${concepts.length ? '' : 'No concepts — '}
        ${stats.concepts || 0} concepts ·
        ${Object.keys(plan.questions || {}).length} questions ·
        ${stats.sequence_edges || 0} teaching-order steps</div>
      <ul>${concepts}</ul>`;
    els.studioPlan.classList.remove('hidden');
  }

  function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, (c) => (
      { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  // The link path. The server has supported https sources all along
  // (`course_builder.intake_url`, `/create/preview`, `/create/course`); this panel
  // advertised a link but only ever read a file, so the copy was untrue in the UI.
  // It now goes through the same preview → save shape as an upload, and the server
  // refuses non-https, oversized, login-walled and non-public addresses.
  async function studioImportUrl(url, save) {
    if (state.status === 'running') return;
    const body = { url };
    if (els.studioTitle.value.trim()) body.title = els.studioTitle.value.trim();
    if (els.studioSubject.value.trim()) body.subject = els.studioSubject.value.trim();
    els.studioPreview.disabled = true;
    els.studioSave.disabled = true;
    studioStatus('Fetching the page…');
    try {
      const plan = await api('/api/v1/create/preview', {
        method: 'POST', body: JSON.stringify(body),
      });
      studioPlan = plan;
      renderPlan(plan);
      if (!save) {
        els.studioSave.classList.remove('hidden');
        studioStatus('Plan ready — review it, then save.', 'ok');
        return;
      }
      studioStatus('Saving the course…');
      const created = await api('/api/v1/create/course', {
        method: 'POST', body: JSON.stringify(body),
      });
      const course = created.course || {};
      if (course.id) {
        await api('/api/v1/my-courses/' + encodeURIComponent(course.id) + '/enrol', { method: 'POST' });
      }
      els.studioSave.classList.add('hidden');
      studioStatus(`Saved — “${escapeHtml(course.title || url)}” is your active course.`, 'ok');
      toast('Course saved and made active.');
      refreshSimMeta();
    } catch (err) {
      studioStatus(err.message, 'error');
    } finally {
      els.studioPreview.disabled = false;
      els.studioSave.disabled = state.status === 'running';
    }
  }

  async function studioUpload(save) {
    const link = (els.studioUrl && els.studioUrl.value.trim()) || '';
    if (link) return studioImportUrl(link, save);
    const file = els.studioFile.files && els.studioFile.files[0];
    if (!file) {
      studioStatus('Choose a file first (PDF, DOCX, TXT, MD) or paste an https link.', 'error');
      return;
    }
    if (state.status === 'running') return;
    const body = new FormData();
    body.append('file', file, file.name);
    if (els.studioTitle.value.trim()) body.append('title', els.studioTitle.value.trim());
    if (els.studioSubject.value.trim()) body.append('subject', els.studioSubject.value.trim());
    els.studioPreview.disabled = true;
    els.studioSave.disabled = true;
    studioStatus(save ? 'Building and saving…' : 'Reading the source…');
    try {
      // No Content-Type here: the browser sets it, with the multipart boundary
      // the body needs. Sending the JSON default instead silently turns every
      // upload into an unparseable envelope.
      const headers = {};
      if (state.token) headers.Authorization = 'Bearer ' + state.token;
      const response = await fetch('/api/v1/create/upload' + (save ? '?save=1' : ''), {
        method: 'POST', headers, body,
      });
      const payload = await response.json().catch(() => ({}));
      if (response.status === 401) {
        els.authRow.classList.remove('hidden');
        throw new Error('Unauthorized — paste a valid access token in the sidebar');
      }
      if (!response.ok) {
        // A refusal is a structured answer with the reason and what to do next.
        const detail = payload.detail || payload;
        throw new Error(detail.reason || detail.message || response.statusText);
      }
      studioPlan = payload;
      renderPlan(payload);
      if (save) {
        els.studioSave.classList.add('hidden');
        studioStatus(`Saved — “${escapeHtml(payload.course && payload.course.title || payload.title || '')}”
          is your active course.`, 'ok');
        toast('Course saved and made active.');
        refreshSimMeta();
      } else {
        els.studioSave.classList.remove('hidden');
        studioStatus('Plan ready — review it, then save.', 'ok');
      }
    } catch (err) {
      studioStatus(err.message, 'error');
    } finally {
      els.studioPreview.disabled = false;
      els.studioSave.disabled = state.status === 'running';
    }
  }

  els.studioPreview.addEventListener('click', () => studioUpload(false));
  els.studioSave.addEventListener('click', () => studioUpload(true));
  els.studioFile.addEventListener('change', () => {
    // One source at a time: picking a file drops a pasted link, so the panel can
    // never send a request that silently ignores half of what it shows.
    if (els.studioUrl && els.studioFile.files && els.studioFile.files[0]) els.studioUrl.value = '';
    studioPlan = null;
    els.studioSave.classList.add('hidden');
    els.studioPlan.classList.add('hidden');
    studioStatus('');
  });

  if (els.studioUrl) {
    els.studioUrl.addEventListener('input', () => {
      if (els.studioUrl.value.trim()) els.studioFile.value = '';
      studioPlan = null;
      els.studioSave.classList.add('hidden');
      els.studioPlan.classList.add('hidden');
      studioStatus('');
    });
  }

  els.studentSend.addEventListener('click', sendStudentRequest);
  els.teacherSend.addEventListener('click', sendTeacherMessage);

  // ------------------------------------------------------------- TA studio

  // The TA is a background subagent: dispatch is fire-and-forget and this panel
  // is where its work becomes visible. Polling is driven by the job list — a
  // running job keeps a 2.5 s cadence, an idle queue stops, so a teacher who
  // never dispatches costs no requests. Results are deduplicated by job id
  // rather than trusted from the cursor alone, because a poll that overlaps a
  // slow response would otherwise render the same asset twice.
  const taState = { jobs: [], results: [], seen: new Set(), timer: null, concepts: [] };

  function taStatus(text, cls = '') {
    els.taStatus.textContent = text;
    els.taStatus.className = 'studio-status' + (cls ? ' ' + cls : '');
  }

  async function loadTaConcepts() {
    try {
      const data = await api('/api/v1/curriculum');
      taState.concepts = (data.concepts || []).map((c) => ({ id: c.id, title: c.title || c.id }));
    } catch { taState.concepts = []; }
    els.taConcept.textContent = '';
    const whole = document.createElement('option');
    whole.value = '';
    whole.textContent = taState.concepts.length
      ? 'Whole course (no single concept)'
      : 'No active course — upload one above first';
    els.taConcept.appendChild(whole);
    for (const concept of taState.concepts) {
      const option = document.createElement('option');
      option.value = concept.id;
      option.textContent = concept.title;
      els.taConcept.appendChild(option);
    }
  }

  function taHasRunning() {
    return taState.jobs.some((job) => job.status === 'running');
  }

  function taEnsureTimer() {
    if (taState.timer || !taHasRunning()) return;
    taState.timer = setInterval(taPoll, 2500);
  }

  function taStopTimer() {
    clearInterval(taState.timer);
    taState.timer = null;
  }

  function renderTaJobs() {
    if (!taState.jobs.length) { els.taJobs.textContent = ''; return; }
    els.taJobs.textContent = '';
    for (const job of taState.jobs) {
      const row = document.createElement('div');
      row.className = 'ta-job';
      const dot = document.createElement('span');
      dot.className = 'ta-dot ' + (job.status === 'running' ? 'run' : 'done');
      const label = document.createElement('span');
      label.className = 'ta-job-label';
      label.textContent = (job.concept_id || 'whole course') + ' · ' + job.status;
      const when = document.createElement('span');
      when.className = 'ta-job-when';
      when.textContent = new Date((job.created_at || 0) * 1000).toLocaleTimeString();
      row.append(dot, label, when);
      els.taJobs.appendChild(row);
    }
  }

  async function taPoll() {
    try {
      const status = await api('/api/v1/ta/status');
      taState.jobs = status.jobs || [];
      renderTaJobs();
      const data = await api('/api/v1/ta/results?since=' + taState.cursor);
      for (const result of data.results || []) {
        if (taState.seen.has(result.id)) continue;
        taState.seen.add(result.id);
        taState.results.unshift(result);
        if ((result.created_at || 0) > taState.cursor) taState.cursor = result.created_at;
      }
      if (taState.results.length) renderTaResults();
    } catch { /* the feed is a convenience; a failed poll keeps the last view */ }
    taHasRunning() ? taEnsureTimer() : taStopTimer();
  }

  async function taDispatch() {
    const message = els.taMessage.value.trim();
    if (!message) { taStatus('Tell the TA what to build first.', 'error'); return; }
    els.taSend.disabled = true;
    taStatus('Dispatched — the TA is working on its own turn…');
    try {
      await api('/api/v1/ta/dispatch', {
        method: 'POST',
        body: JSON.stringify({ message, concept_id: els.taConcept.value || '' }),
      });
      els.taMessage.value = '';
      taStatus('TA is running — assets will appear below as they are produced.', 'ok');
      await taPoll();
      taEnsureTimer();
    } catch (err) {
      taStatus(err.message, 'error');
    } finally {
      els.taSend.disabled = false;
    }
  }

  // Local image bytes ride the authenticated media route; the provider's own
  // URL is the fallback for embed-posture results (searched, never downloaded).
  // A thumbnail that cannot be rendered is dropped rather than shown broken.
  //
  // Cards and the media list name the same picture differently — a card carries
  // `url`, a media row carries `thumb_url` — so both are read here. Reading only
  // `thumb_url` silently rendered every searched image as text.
  async function taImageSrc(item) {
    if (item.sha) {
      try {
        const response = await fetch('/api/v1/media/images/' + item.sha + '/bytes',
          { headers: authHeaders() });
        if (response.ok) return URL.createObjectURL(await response.blob());
      } catch { /* fall through to the remote URL */ }
    }
    return item.thumb_url || item.url || '';
  }

  function taDeckPptxName(meta) {
    const versions = (meta && meta.versions) || [];
    const latest = versions[versions.length - 1] || {};
    const files = latest.files || {};
    return files.pptx || '';
  }

  async function renderTaResults() {
    els.taResults.textContent = '';
    for (const result of taState.results.slice(0, 8)) {
      const payload = result.result || {};
      const card = document.createElement('div');
      card.className = 'ta-result';
      const head = document.createElement('div');
      head.className = 'ta-result-head';
      const title = document.createElement('span');
      title.className = 'ta-result-title';
      title.textContent = payload.summary
        ? 'TA report'
        : 'TA run (no written report)';
      const when = document.createElement('span');
      when.className = 'ta-result-when';
      when.textContent = new Date((result.created_at || 0) * 1000).toLocaleString();
      head.append(title, when);
      card.appendChild(head);
      if (payload.summary) {
        const summary = document.createElement('p');
        summary.className = 'ta-summary';
        summary.textContent = payload.summary;
        card.appendChild(summary);
      }
      const row = document.createElement('div');
      row.className = 'ta-cards';
      // Cards name what was produced; the media list carries the cache sha the
      // authenticated bytes route needs. The merge is a pure function in cards.js
      // so it can be tested without a DOM — it used to reassign the loop's `const`
      // and throw `Assignment to constant variable` on the first cached image.
      const cards = window.LuminfestCards
        ? window.LuminfestCards.mergeCachedSha(
            payload.cards, window.LuminfestCards.shaMapFromMedia(payload.media))
        : (payload.cards || []);
      for (const item of cards) {
        row.appendChild(await taCard(item));
      }
      if (row.children.length) card.appendChild(row);
      els.taResults.appendChild(card);
    }
  }

  async function taCard(item) {
    const card = document.createElement('div');
    card.className = 'ta-card';
    if (item.kind === 'artifact') {
      const name = document.createElement('div');
      name.className = 'ta-card-title';
      name.textContent = item.title || 'Deck';
      const tools = document.createElement('div');
      tools.className = 'ta-card-tools';
      const open = document.createElement('button');
      open.className = 'btn btn-small';
      open.textContent = 'Open deck';
      open.addEventListener('click', () => selectSim(item.artifact_id));
      tools.appendChild(open);
      const pptx = document.createElement('a');
      pptx.className = 'btn btn-small';
      pptx.textContent = '.pptx';
      pptx.href = '#';
      pptx.addEventListener('click', async (event) => {
        event.preventDefault();
        try {
          const meta = await api('/api/v1/sims/' + item.artifact_id);
          const name_ = taDeckPptxName(meta);
          if (!name_) { toast('This deck has no .pptx twin.'); return; }
          const response = await fetch(
            '/api/v1/sims/' + item.artifact_id + '/download/' + name_,
            { headers: authHeaders() });
          if (!response.ok) throw new Error(response.statusText);
          const blob = await response.blob();
          const url = URL.createObjectURL(blob);
          const link = document.createElement('a');
          link.href = url;
          link.download = (item.title || 'deck') + '.pptx';
          link.click();
          URL.revokeObjectURL(url);
        } catch (err) { toast('Download failed: ' + err.message); }
      });
      tools.appendChild(pptx);
      card.append(name, tools);
      return card;
    }
    // An image card shows the picture, its title, its licence and its source
    // page. Relevance is not checked anywhere in this pipeline — a full-text
    // search for an abstract concept can return a clean, credited, wrong
    // picture — so the title is what tells the teacher whether to keep it.
    const src = await taImageSrc(item);
    if (src) {
      const img = document.createElement('img');
      img.className = 'ta-img';
      img.src = src;
      img.alt = item.title || 'fetched image';
      img.loading = 'lazy';
      card.appendChild(img);
    }
    const meta = document.createElement('div');
    meta.className = 'ta-card-meta';
    meta.textContent = [item.title, item.licence].filter(Boolean).join(' — ');
    card.appendChild(meta);
    if (item.source) {
      const link = document.createElement('a');
      link.className = 'ta-card-src';
      link.href = item.source;
      link.target = '_blank';
      link.rel = 'noreferrer';
      link.textContent = 'source';
      card.appendChild(link);
    }
    return card;
  }

  els.taSend.addEventListener('click', taDispatch);
  els.taMessage.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); taDispatch(); }
  });

  function autoGrow(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
  }

  els.studentNote.addEventListener('input', () => autoGrow(els.studentNote));
  els.teacherInput.addEventListener('input', () => autoGrow(els.teacherInput));

  for (const [textarea, send] of [[els.studentNote, sendStudentRequest], [els.teacherInput, sendTeacherMessage]]) {
    textarea.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        send();
      }
    });
  }

  // ---------------------------------------------------------------- details

  els.devToggle.addEventListener('click', () => {
    els.devPanel.classList.toggle('hidden');
  });
  els.devMode.addEventListener('change', () => {
    state.devMode = els.devMode.checked;
    renderTranscript();
  });
  els.simRefresh.addEventListener('click', () => {
    state.activeSimVersion = null; // force reload even if the version is unchanged
    refreshSimMeta(true);
  });
  els.sidebarToggle.addEventListener('click', () => {
    els.sidebar.classList.toggle('open');
  });

  // --------------------------------------------------------------- sessions

  function renderSessions() {
    els.sessionList.textContent = '';
    for (const session of state.sessions.slice(0, 20)) {
      const li = document.createElement('li');
      if (session.id === state.activeSessionId) li.classList.add('active');
      const title = document.createElement('span');
      title.className = 'session-title';
      title.textContent = session.title || 'Session';
      const meta = document.createElement('span');
      meta.className = 'session-meta';
      meta.textContent = new Date(session.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      li.append(title, meta);
      li.addEventListener('click', () => {
        state.activeSessionId = session.id;
        if (session.simId) selectSim(session.simId);
        renderSessions();
        renderTranscript();
      });
      els.sessionList.appendChild(li);
    }
  }

  els.newSession.addEventListener('click', () => {
    newSession();
    toast('New session started — history is preserved per session');
  });

  // ------------------------------------------------------------------- auth

  els.tokenSave.addEventListener('click', () => {
    state.token = els.tokenInput.value.trim();
    if (state.token) sessionStorage.setItem(STORAGE.token, state.token);
    else sessionStorage.removeItem(STORAGE.token);
    els.authRow.classList.add('hidden');
    toast('Token saved for this tab (sessionStorage)');
    loadSimList();
    loadServerRole();
    loadTelemetryConsent();
  });

  if (els.telemetryToggle) {
    els.telemetryToggle.addEventListener('change', async () => {
      const on = els.telemetryToggle.checked;
      try {
        const me = await api('/api/v1/me', {
          method: 'PATCH', body: JSON.stringify({ telemetry_consent: on }),
        });
        const saved = me.telemetry_consent === true;
        els.telemetryToggle.checked = saved;
        armTelemetry(saved);
        toast(saved
          ? 'Interaction telemetry is on for this account'
          : 'Interaction telemetry is off; nothing is being sent');
      } catch (error) {
        els.telemetryToggle.checked = !on;
        armTelemetry(!on);
        toast('Could not change telemetry consent: ' + (error.message || 'unknown error'));
      }
    });
  }

  // ------------------------------------------------------------------ start

  function restore() {
    try {
      const raw = localStorage.getItem(STORAGE.sessions);
      if (raw) {
        state.sessions = JSON.parse(raw) || [];
        for (const s of state.sessions) for (const m of s.messages) m.live = false;
      }
    } catch { state.sessions = []; }
    if (state.sessions.length) state.activeSessionId = state.sessions[0].id;
    else newSession();
    els.tokenInput.value = state.token;
  }

  restore();
  setRole(state.role);
  setStatus('idle');
  renderSessions();
  renderTranscript();
  loadSimList();
  loadServerRole();
  loadTelemetryConsent();
})();
