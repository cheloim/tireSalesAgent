const fmt = new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 0 });

// ── Auth token ────────────────────────────────────────────────
function _getToken() {
  return sessionStorage.getItem('dashboard_token') || '';
}

function _setToken(t) {
  sessionStorage.setItem('dashboard_token', t);
}

function toggleTokenVis() {
  const inp = document.getElementById('token-input');
  inp.type = inp.type === 'password' ? 'text' : 'password';
}

function _mostrarModalToken(error = false) {
  document.getElementById('token-overlay').style.display = 'flex';
  document.getElementById('token-error').style.display = error ? 'block' : 'none';
  document.getElementById('token-input').value = '';
  setTimeout(() => document.getElementById('token-input').focus(), 50);
}

function _ocultarModalToken() {
  document.getElementById('token-overlay').style.display = 'none';
}

async function apiFetch(url, opts = {}) {
  const token = _getToken();
  const headers = { ...(opts.headers || {}), ...(token ? { 'X-Dashboard-Token': token } : {}) };
  const res = await fetch(url, { ...opts, headers });
  if (res.status === 401) {
    sessionStorage.removeItem('dashboard_token');
    await _pedirToken(true);
    return apiFetch(url, opts);
  }
  return res;
}

function _pedirToken(error = false) {
  return new Promise(resolve => {
    _mostrarModalToken(error);
    document.getElementById('token-form').onsubmit = (e) => {
      e.preventDefault();
      const t = document.getElementById('token-input').value.trim();
      if (!t) return;
      _setToken(t);
      _ocultarModalToken();
      resolve(t);
    };
  });
}

function _sseUrl(path) {
  const token = _getToken();
  return token ? `${path}?token=${encodeURIComponent(token)}` : path;
}

// ── Menu ──────────────────────────────────────────────────────
function toggleMenu() {
  document.getElementById('nav-menu').classList.toggle('open');
}

// ── Helpers ───────────────────────────────────────────────────
function tiempoAtras(fechaStr) {
  if (!fechaStr) return '—';
  const utc = fechaStr.includes('Z') || fechaStr.includes('+') ? fechaStr : fechaStr.replace(' ', 'T') + 'Z';
  const diff = Math.floor((Date.now() - new Date(utc).getTime()) / 1000);
  if (diff < 60)    return `${diff}s`;
  if (diff < 3600)  return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  return new Date(utc).toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit' });
}

function canalBadge(canal) {
  const c     = (canal || 'web').toLowerCase();
  const cls   = c.includes('telegram') ? 'canal-tg' : c.includes('whatsapp') ? 'canal-wa' : c.includes('twilio') ? 'canal-twilio' : 'canal-web';
  const label = c.includes('telegram') ? 'Telegram'  : c.includes('whatsapp') ? 'WhatsApp'  : c.includes('twilio') ? 'Twilio'  : 'Web';
  return `<span class="${cls}">${label}</span>`;
}

// ── Render metrics ────────────────────────────────────────────
function renderMetricas(d) {
  document.getElementById('chats-activos').textContent = d.chats_activos ?? '—';
  document.getElementById('presup-hoy').textContent    = d.presupuestos_hoy ?? '0';
  document.getElementById('total-hoy').textContent     = fmt.format(d.total_hoy ?? 0);
  document.getElementById('presup-semana').textContent = d.presupuestos_semana ?? '0';
  document.getElementById('total-semana').textContent  = fmt.format(d.total_semana ?? 0);
  document.getElementById('presup-mes').textContent    = d.presupuestos_mes ?? '0';
  document.getElementById('total-mes').textContent     = fmt.format(d.total_mes ?? 0);
  const lista = document.getElementById('agentes-lista');
  if (d.por_agente?.length) {
    lista.innerHTML = d.por_agente.map(a =>
      `<div class="agente-row"><span class="agente-name">${a.agente}</span><span class="agente-count">${a.chats} chat${a.chats !== 1 ? 's' : ''}</span></div>`
    ).join('');
  } else {
    lista.textContent = 'None';
  }
}

// ── Render active chats ───────────────────────────────────────
function renderChats(chats) {
  const tbody = document.getElementById('tbody-chats');
  document.getElementById('badge-chats').textContent = chats?.length ?? 0;
  if (!chats?.length) {
    tbody.innerHTML = '<tr><td colspan="5" class="empty">No active chats</td></tr>';
    return;
  }
  tbody.innerHTML = chats.map(c => `
    <tr>
      <td>${canalBadge(c.canal)}</td>
      <td>${c.agente}${c.debug ? ' <span class="badge-debug">debug</span>' : ''}</td>
      <td>${c.mensajes}</td>
      <td>${tiempoAtras(c.actualizado)}</td>
      <td><button class="btn-row" onclick="abrirChat('${c.session_id}','${c.agente}','${c.canal}')">👁</button></td>
    </tr>`).join('');
}

// ── SSE dashboard ─────────────────────────────────────────────
let _es = null;

function conectarStream() {
  const dot = document.getElementById('live-dot');
  const upd = document.getElementById('last-update');
  if (_es) _es.close();
  _es = new EventSource(_sseUrl('/api/dashboard/stream'));
  _es.onopen    = () => { dot.classList.add('live'); upd.textContent = 'Live'; };
  _es.onmessage = (e) => {
    try {
      const p = JSON.parse(e.data);
      renderMetricas(p.metricas);
      renderChats(p.chats);
      upd.textContent = 'Updated: ' + new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch (err) { console.error('SSE', err); }
  };
  _es.onerror = () => { dot.classList.remove('live'); upd.textContent = 'Reconnecting…'; };
}

// ── Chat drawer ───────────────────────────────────────────────
let _drawerSession      = null;
let _drawerInterval     = null;
let _drawerConvId       = null;

function _abrirDrawer(agente, canal, convId) {
  document.getElementById('drawer-agente').textContent = agente;
  document.getElementById('drawer-canal').innerHTML    = canalBadge(canal);
  document.getElementById('chat-drawer').classList.add('open');
  document.getElementById('drawer-overlay').classList.add('open');
  const dlBtn = document.getElementById('drawer-download');
  dlBtn.style.display = convId ? '' : 'none';
  _drawerConvId = convId || null;
}

function abrirChat(session_id, agente, canal) {
  if (_drawerInterval) clearInterval(_drawerInterval);
  _drawerSession = session_id;
  _abrirDrawer(agente, canal, null);
  actualizarDrawer();
  _drawerInterval = setInterval(actualizarDrawer, 3000);
}

function abrirLog(conversation_id, agente, canal) {
  if (_drawerInterval) { clearInterval(_drawerInterval); _drawerInterval = null; }
  _drawerSession = null;
  _abrirDrawer(agente, canal, conversation_id);
  _cargarConversacion(conversation_id);
}

function descargarLogActual() {
  if (!_drawerConvId) return;
  const token = _getToken();
  const qs = token ? `?conversation=${encodeURIComponent(_drawerConvId)}&token=${encodeURIComponent(token)}` : `?conversation=${encodeURIComponent(_drawerConvId)}`;
  const a = document.createElement('a');
  a.href = `/api/dashboard/descargar-logs${qs}`;
  a.download = '';
  a.click();
}

function cerrarDrawer() {
  document.getElementById('chat-drawer').classList.remove('open');
  document.getElementById('drawer-overlay').classList.remove('open');
  clearInterval(_drawerInterval);
  _drawerInterval = null;
  _drawerSession  = null;
  _drawerConvId   = null;
}

async function actualizarDrawer() {
  if (!_drawerSession) return;
  try {
    const data = await apiFetch(`/api/dashboard/chat/${encodeURIComponent(_drawerSession)}`).then(r => r.json());
    _renderDrawerMsgs(data.mensajes, true);
    document.getElementById('drawer-updated').textContent =
      'Updated ' + new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch(e) { console.error('drawer', e); }
}

async function _cargarConversacion(conversation_id) {
  try {
    const data = await apiFetch(`/api/dashboard/conversation/${encodeURIComponent(conversation_id)}`).then(r => r.json());
    _renderDrawerMsgs(data.mensajes, false);
    document.getElementById('drawer-updated').textContent =
      data.actualizado ? tiempoAtras(data.actualizado) : '';
  } catch(e) { console.error('log drawer', e); }
}

function _renderDrawerMsgs(mensajes, autoScroll) {
  const msgs = document.getElementById('drawer-messages');
  const wasAtBottom = msgs.scrollHeight - msgs.scrollTop <= msgs.clientHeight + 40;
  msgs.innerHTML = mensajes.length
    ? mensajes.map(m => {
        const isUser = m.role === 'user';
        return `<div class="drawer-msg ${isUser ? 'drawer-msg-user' : 'drawer-msg-agent'}">
          <div class="drawer-bubble">${(m.content || '').replace(/\n/g, '<br>')}</div>
        </div>`;
      }).join('')
    : '<div class="empty" style="padding:2rem">No messages</div>';
  if (autoScroll && wasAtBottom) msgs.scrollTop = msgs.scrollHeight;
  else if (!autoScroll) msgs.scrollTop = msgs.scrollHeight;
}

// ── Logs 7 days ───────────────────────────────────────────────
async function cargarLogs() {
  try {
    const data  = await apiFetch('/api/dashboard/logs').then(r => r.json());
    const tbody = document.getElementById('tbody-logs');
    document.getElementById('badge-logs').textContent = data.logs?.length ?? 0;
    if (!data.logs?.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty">No records</td></tr>';
      return;
    }
    tbody.innerHTML = data.logs.map(l => `
      <tr>
        <td>${tiempoAtras(l.actualizado)}</td>
        <td>${canalBadge(l.canal)}</td>
        <td>${l.agente}${l.debug ? ' <span class="badge-debug">debug</span>' : ''}</td>
        <td>${l.mensajes}</td>
        <td><button class="btn-row" onclick="abrirLog('${l.conversation_id}','${l.agente}','${l.canal}')">👁</button></td>
      </tr>`).join('');
  } catch (e) { console.error('logs', e); }
}

// ── Sales ─────────────────────────────────────────────────────
let _ventasMap = {};
let _ventaActualId = null;

function descargarVentaActual() {
  if (!_ventaActualId) return;
  const token = _getToken();
  const qs = token ? `?id=${_ventaActualId}&token=${encodeURIComponent(token)}` : `?id=${_ventaActualId}`;
  const a = document.createElement('a');
  a.href = `/api/dashboard/descargar-ventas${qs}`;
  a.download = '';
  a.click();
}

function verVenta(id) {
  const v = _ventasMap[id];
  if (!v) return;
  _ventaActualId = id;
  document.getElementById('sale-modal-body').innerHTML = `
    <table class="sale-detail-table">
      <tr><th>Date</th><td>${v.fecha || '—'}</td></tr>
      <tr><th>Agent</th><td>${v.agente}</td></tr>
      <tr><th>Product</th><td>${v.marca} ${v.modelo}</td></tr>
      <tr><th>Size</th><td>${v.medida}</td></tr>
      <tr><th>Qty</th><td>${v.cantidad}</td></tr>
      <tr><th>Total</th><td>${fmt.format(v.total)}</td></tr>
      <tr><th>Branch</th><td>${v.sucursal}</td></tr>
      <tr><th>Client</th><td>${v.cliente}</td></tr>
    </table>`;
  document.getElementById('sale-modal').classList.add('open');
  document.getElementById('sale-modal-overlay').classList.add('open');
}

function cerrarVenta() {
  document.getElementById('sale-modal').classList.remove('open');
  document.getElementById('sale-modal-overlay').classList.remove('open');
  _ventaActualId = null;
}

async function cargarVentas() {
  try {
    const data  = await apiFetch('/api/dashboard/ventas').then(r => r.json());
    const tbody = document.getElementById('tbody-ventas');
    document.getElementById('badge-ventas').textContent = data.ventas?.length ?? 0;
    if (!data.ventas?.length) {
      tbody.innerHTML = '<tr><td colspan="9" class="empty">No confirmed sales</td></tr>';
      return;
    }
    _ventasMap = {};
    data.ventas.forEach(v => { _ventasMap[v.id] = v; });
    tbody.innerHTML = data.ventas.map(v => `
      <tr>
        <td>${tiempoAtras(v.fecha)}</td>
        <td>${v.agente}</td>
        <td>${v.marca} ${v.modelo}</td>
        <td>${v.medida}</td>
        <td>${v.cantidad}</td>
        <td>${fmt.format(v.total)}</td>
        <td>${v.sucursal}</td>
        <td>${v.cliente}</td>
        <td><button class="btn-row" onclick="verVenta(${v.id})">👁</button></td>
      </tr>`).join('');
  } catch (e) { console.error('ventas', e); }
}

// ── Init ──────────────────────────────────────────────────────
async function init() {
  if (!_getToken()) await _pedirToken();
  conectarStream();
  cargarVentas();
  cargarLogs();
  setInterval(cargarLogs, 30_000);
}

init();
