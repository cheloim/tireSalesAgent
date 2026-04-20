const fmt = new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 0 });

// ── Menu ──────────────────────────────────────────────────────
function toggleMenu() {
  document.getElementById('nav-menu').classList.toggle('open');
}

// ── Helpers ───────────────────────────────────────────────────
function tiempoAtras(fechaStr) {
  if (!fechaStr) return '—';
  const diff = Math.floor((Date.now() - new Date(fechaStr).getTime()) / 1000);
  if (diff < 60)    return `${diff}s`;
  if (diff < 3600)  return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  return new Date(fechaStr).toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit' });
}

function canalBadge(canal) {
  const c     = (canal || 'web').toLowerCase();
  const cls   = c.includes('telegram') ? 'canal-tg' : c.includes('whatsapp') ? 'canal-wa' : c.includes('twilio') ? 'canal-twilio' : 'canal-web';
  const label = c.includes('telegram') ? 'Telegram'  : c.includes('whatsapp') ? 'WhatsApp'  : c.includes('twilio') ? 'Twilio'  : 'Web';
  return `<span class="${cls}">${label}</span>`;
}

// ── Render métricas ───────────────────────────────────────────
function renderMetricas(d) {
  document.getElementById('chats-activos').textContent = d.chats_activos ?? '—';
  document.getElementById('presup-hoy').textContent    = d.presupuestos_hoy ?? '0';
  document.getElementById('total-hoy').textContent     = fmt.format(d.total_hoy ?? 0);
  document.getElementById('presup-semana').textContent = d.presupuestos_semana ?? '0';
  document.getElementById('total-semana').textContent  = fmt.format(d.total_semana ?? 0);
  const lista = document.getElementById('agentes-lista');
  if (d.por_agente?.length) {
    lista.innerHTML = d.por_agente.map(a =>
      `<div class="agente-row"><span class="agente-name">${a.agente}</span><span class="agente-count">${a.chats} chat${a.chats !== 1 ? 's' : ''}</span></div>`
    ).join('');
  } else {
    lista.textContent = 'Ninguno';
  }
}

// ── Render chats activos ──────────────────────────────────────
function renderChats(chats) {
  const tbody = document.getElementById('tbody-chats');
  document.getElementById('badge-chats').textContent = chats?.length ?? 0;
  if (!chats?.length) {
    tbody.innerHTML = '<tr><td colspan="4" class="empty">Sin chats activos</td></tr>';
    return;
  }
  tbody.innerHTML = chats.map(c => `
    <tr>
      <td>${canalBadge(c.canal)}</td>
      <td>${c.agente}</td>
      <td>${c.mensajes}</td>
      <td>${tiempoAtras(c.actualizado)}</td>
    </tr>`).join('');
}

// ── SSE dashboard ─────────────────────────────────────────────
function conectarStream() {
  const dot = document.getElementById('live-dot');
  const upd = document.getElementById('last-update');
  const es  = new EventSource('/api/dashboard/stream');
  es.onopen    = () => { dot.classList.add('live'); upd.textContent = 'En vivo'; };
  es.onmessage = (e) => {
    try {
      const p = JSON.parse(e.data);
      renderMetricas(p.metricas);
      renderChats(p.chats);
      upd.textContent = 'Actualizado: ' + new Date().toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch (err) { console.error('SSE', err); }
  };
  es.onerror = () => { dot.classList.remove('live'); upd.textContent = 'Reconectando…'; };
}

// ── Logs 7 días ───────────────────────────────────────────────
function descargarLog(session_id, btn) {
  btn.disabled = true;
  const a = document.createElement('a');
  a.href = `/api/dashboard/descargar-logs?session=${encodeURIComponent(session_id)}`;
  a.download = '';
  a.click();
  setTimeout(() => { btn.disabled = false; }, 1500);
}

async function cargarLogs() {
  try {
    const data  = await fetch('/api/dashboard/logs').then(r => r.json());
    const tbody = document.getElementById('tbody-logs');
    document.getElementById('badge-logs').textContent = data.logs?.length ?? 0;
    if (!data.logs?.length) {
      tbody.innerHTML = '<tr><td colspan="5" class="empty">Sin registros</td></tr>';
      return;
    }
    tbody.innerHTML = data.logs.map(l => `
      <tr>
        <td>${tiempoAtras(l.actualizado)}</td>
        <td>${canalBadge(l.canal)}</td>
        <td>${l.agente}</td>
        <td>${l.mensajes}</td>
        <td><button class="btn-row" onclick="descargarLog('${l.session_id}',this)">↓</button></td>
      </tr>`).join('');
  } catch (e) { console.error('logs', e); }
}

// ── Ventas ────────────────────────────────────────────────────
function descargarVenta(id, btn) {
  btn.disabled = true;
  const a = document.createElement('a');
  a.href = `/api/dashboard/descargar-ventas?id=${id}`;
  a.download = '';
  a.click();
  setTimeout(() => { btn.disabled = false; }, 1500);
}

async function cargarVentas() {
  try {
    const data  = await fetch('/api/dashboard/ventas').then(r => r.json());
    const tbody = document.getElementById('tbody-ventas');
    document.getElementById('badge-ventas').textContent = data.ventas?.length ?? 0;
    if (!data.ventas?.length) {
      tbody.innerHTML = '<tr><td colspan="9" class="empty">Sin presupuestos confirmados</td></tr>';
      return;
    }
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
        <td><button class="btn-row" onclick="descargarVenta(${v.id},this)">↓</button></td>
      </tr>`).join('');
  } catch (e) { console.error('ventas', e); }
}

// ── Init ──────────────────────────────────────────────────────
conectarStream();
cargarVentas();
cargarLogs();
