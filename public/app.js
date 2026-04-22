// ── State ─────────────────────────────────────────────────────
let abortController = null;
let _msgQueue   = [];
let _queueTimer = null;
let _typingId   = null;
const QUEUE_DELAY = 3500; // ms to wait before sending buffered messages

// ── Init ──────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  verificarEstado();
  configurarInput();
});

// ── Check agent status ────────────────────────────────────────
async function verificarEstado() {
  const dot  = document.getElementById('status-dot');
  const text = document.getElementById('status-text');

  try {
    const res  = await fetch('/api/estado');
    const data = await res.json();

    if (data.ollama_disponible) {
      dot.className    = 'status-dot status-ok';
      text.textContent = 'En línea';
    } else {
      dot.className    = 'status-dot status-error';
      text.textContent = 'No disponible';
      mostrarErrorSistema(data.mensaje);
    }
  } catch {
    dot.className    = 'status-dot status-error';
    text.textContent = 'Error de conexión';
  }
}

function mostrarErrorSistema(mensaje) {
  const chat = document.getElementById('chat-messages');
  const div  = document.createElement('div');
  div.className = 'msg msg-agent';
  div.innerHTML = `
    <div class="msg-body">
      <div class="msg-bubble" style="border-color:var(--brand);">
        <strong>Aviso del sistema:</strong><br>${mensaje}
      </div>
    </div>`;
  chat.appendChild(div);
  scrollAbajo();
}

// ── Input setup ───────────────────────────────────────────────
function configurarInput() {
  const input = document.getElementById('user-input');

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      enviarMensaje();
    }
  });

  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
  });
}

// ── Send quick suggestion ─────────────────────────────────────
function enviarSugerencia(texto) {
  const input = document.getElementById('user-input');
  input.value = texto;
  enviarMensaje();
}

// ── Send message — adds to queue, debounced ───────────────────
function enviarMensaje() {
  const input   = document.getElementById('user-input');
  const mensaje = input.value.trim();
  if (!mensaje) return;

  document.getElementById('suggestions').style.display = 'none';
  agregarMensaje(mensaje, 'user');
  input.value = '';
  input.style.height = 'auto';

  // Abort any ongoing SSE stream so the new batch takes over
  if (abortController) {
    abortController.abort();
    abortController = null;
  }

  _msgQueue.push(mensaje);

  // Show typing indicator while waiting for the queue to flush
  if (!_typingId) _typingId = mostrarTyping();

  // Reset debounce timer
  clearTimeout(_queueTimer);
  _queueTimer = setTimeout(_flushQueue, QUEUE_DELAY);
}

// ── Flush queue — send all buffered messages as one request ───
async function _flushQueue() {
  const mensajes = _msgQueue.splice(0);
  _queueTimer = null;
  if (!mensajes.length) return;

  const mensajeCombinado = mensajes.join('\n');

  abortController = new AbortController();

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mensaje: mensajeCombinado }),
      signal: abortController.signal,
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
    let   buffer  = '';
    let   currentTypingId = _typingId;
    _typingId = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lineas = buffer.split('\n');
      buffer = lineas.pop();

      for (const linea of lineas) {
        if (!linea.startsWith('data: ')) continue;
        const jsonStr = linea.slice(6).trim();
        if (!jsonStr) continue;

        let evento;
        try { evento = JSON.parse(jsonStr); } catch { continue; }

        if (evento.tipo === 'texto') {
          quitarTyping(currentTypingId);
          currentTypingId = null;
          agregarMensaje(evento.contenido, 'bot');
        } else if (evento.tipo === 'typing') {
          if (currentTypingId) quitarTyping(currentTypingId);
          currentTypingId = mostrarTyping();
        } else if (evento.tipo === 'fin') {
          if (currentTypingId) quitarTyping(currentTypingId);
          abortController = null;
        }
      }
    }

  } catch (err) {
    if (err.name === 'AbortError') return;
    if (_typingId) { quitarTyping(_typingId); _typingId = null; }
    document.querySelectorAll('[id^="typing-"]').forEach(el => el.remove());
    agregarMensaje("Disculpá, se cortó la conexión un momento. ¿Me repetís lo que necesitabas?", 'bot');
    abortController = null;
  }
}

// ── Message helpers ───────────────────────────────────────────
function agregarMensaje(texto, rol) {
  const chat  = document.getElementById('chat-messages');
  const esBot = rol === 'bot';
  const div   = document.createElement('div');
  div.className = `msg ${esBot ? 'msg-agent' : 'msg-user'}`;

  const hora = new Date().toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' });

  div.innerHTML = `
    <div class="msg-body">
      <div class="msg-bubble">${formatearTexto(texto)}</div>
      <span class="msg-time">${hora}</span>
    </div>`;

  chat.appendChild(div);
  scrollAbajo();
  return div;
}

function mostrarTyping() {
  const chat = document.getElementById('chat-messages');
  const id   = 'typing-' + Date.now();
  const div  = document.createElement('div');
  div.id        = id;
  div.className = 'msg msg-agent';
  div.innerHTML = `
    <div class="msg-body">
      <div class="msg-bubble">
        <div class="typing-dots"><span></span><span></span><span></span></div>
      </div>
    </div>`;
  chat.appendChild(div);
  scrollAbajo();
  return id;
}

function quitarTyping(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

function formatearTexto(texto) {
  if (!texto) return '';
  return texto
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    .replace(/^\d+\. (.+)$/gm, '<li>$1</li>')
    .replace(/\n/g, '<br>')
    .replace(/(<li>.*?<\/li>(\s*<br>)*)+/gs, (m) => `<ul>${m.replace(/<br>/g, '')}</ul>`);
}

function scrollAbajo() {
  const chat = document.getElementById('chat-messages');
  chat.scrollTop = chat.scrollHeight;
}

// ── Download conversation ─────────────────────────────────────
function descargarConversacion() {
  const mensajes = document.querySelectorAll('#chat-messages .message');
  if (mensajes.length === 0) return;

  const fecha = new Date().toLocaleString('en-US', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit'
  }).replace(/[/:,\s]/g, '-').replace(/-+/g, '-');

  let texto = `Conversación – Neumáticos Martinez\n${new Date().toLocaleString('es-AR')}\n${'─'.repeat(40)}\n\n`;

  mensajes.forEach(msg => {
    const esBot  = msg.classList.contains('message-bot');
    const bubble = msg.querySelector('.message-bubble');
    const hora   = msg.querySelector('.message-time');
    if (!bubble) return;
    if (bubble.querySelector('.typing-dots')) return;

    const remitente = esBot ? 'Agente' : 'Vos';
    const horaStr   = hora ? hora.textContent : '';
    const contenido = bubble.innerText.trim();

    texto += `[${horaStr}] ${remitente}:\n${contenido}\n\n`;
  });

  const blob = new Blob([texto], { type: 'text/plain;charset=utf-8' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = `neumaticos-martinez-${fecha}.txt`;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Clear chat ────────────────────────────────────────────────
async function limpiarChat() {
  if (!confirm('¿Iniciar una nueva conversación?')) return;

  // Cancel any pending queue
  clearTimeout(_queueTimer);
  _queueTimer = null;
  _msgQueue   = [];
  if (abortController) { abortController.abort(); abortController = null; }
  if (_typingId) { quitarTyping(_typingId); _typingId = null; }

  try { await fetch('/api/limpiar', { method: 'POST' }); } catch {}

  const chat = document.getElementById('chat-messages');
  chat.innerHTML = `
    <div class="msg msg-agent">
      <div class="msg-body">
        <div class="msg-bubble"><p>¡Hola! ¿En qué te puedo ayudar hoy?</p></div>
        <span class="msg-time">Ahora</span>
      </div>
    </div>`;

  document.getElementById('suggestions').style.display = 'flex';
}
