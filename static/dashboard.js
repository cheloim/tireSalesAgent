const fmt = new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'ARS', maximumFractionDigits: 0 });

function tiempoAtras(fechaStr) {
  if (!fechaStr) return '—';
  const diff = Math.floor((Date.now() - new Date(fechaStr).getTime()) / 1000);
  if (diff < 60)   return `${diff}s`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  return new Date(fechaStr).toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit' });
}

function canalBadge(canal) {
  const c = (canal || 'web').toLowerCase();
  const cls = c.includes('telegram') ? 'canal-tg'
            : c.includes('whatsapp') ? 'canal-wa'
            : c.includes('twilio')   ? 'canal-twilio'
            : 'canal-web';
  const label = c.includes('telegram') ? 'Telegram'
              : c.includes('whatsapp') ? 'WhatsApp'
              : c.includes('twilio')   ? 'Twilio'
              : 'Web';
  return `<span class="${cls}">${label}</span>`;
}

async function cargarMetricas() {
  try {
    const data = await fetch('/api/dashboard/metricas').then(r => r.json());
    document.getElementById('chats-activos').textContent   = data.chats_activos ?? '—';
    document.getElementById('presup-hoy').textContent      = data.presupuestos_hoy ?? '0';
    document.getElementById('total-hoy').textContent       = fmt.format(data.total_hoy ?? 0);
    document.getElementById('presup-semana').textContent   = data.presupuestos_semana ?? '0';
    document.getElementById('total-semana').textContent    = fmt.format(data.total_semana ?? 0);

    const lista = document.getElementById('agentes-lista');
    if (data.por_agente && data.por_agente.length) {
      lista.innerHTML = data.por_agente.map(a =>
        `<div class="agente-row"><span class="agente-name">${a.agente}</span><span class="agente-count">${a.cantidad}</span></div>`
      ).join('');
    } else {
      lista.textContent = 'Sin datos';
    }
  } catch (e) { console.error('metricas', e); }
}

async function cargarChats() {
  try {
    const data = await fetch('/api/dashboard/chats').then(r => r.json());
    const tbody = document.getElementById('tbody-chats');
    document.getElementById('badge-chats').textContent = data.chats?.length ?? 0;
    if (!data.chats?.length) {
      tbody.innerHTML = '<tr><td colspan="4" class="empty">Sin chats activos</td></tr>';
      return;
    }
    tbody.innerHTML = data.chats.map(c => `
      <tr>
        <td>${canalBadge(c.canal)}</td>
        <td>${c.agente}</td>
        <td>${c.mensajes}</td>
        <td>${tiempoAtras(c.actualizado)}</td>
      </tr>`).join('');
  } catch (e) { console.error('chats', e); }
}

async function cargarLogs() {
  try {
    const data = await fetch('/api/dashboard/logs').then(r => r.json());
    const tbody = document.getElementById('tbody-logs');
    document.getElementById('badge-logs').textContent = data.logs?.length ?? 0;
    if (!data.logs?.length) {
      tbody.innerHTML = '<tr><td colspan="4" class="empty">Sin registros</td></tr>';
      return;
    }
    tbody.innerHTML = data.logs.map(l => `
      <tr>
        <td>${tiempoAtras(l.actualizado)}</td>
        <td>${canalBadge(l.canal)}</td>
        <td>${l.agente}</td>
        <td>${l.mensajes}</td>
      </tr>`).join('');
  } catch (e) { console.error('logs', e); }
}

async function cargarTodo() {
  await Promise.all([cargarMetricas(), cargarChats(), cargarLogs()]);
  document.getElementById('last-update').textContent =
    'Actualizado: ' + new Date().toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

cargarTodo();
setInterval(cargarTodo, 30000);
