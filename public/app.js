/* ══════════════════════════════════════════════════════════════
   Neumáticos Martinez – Frontend JavaScript
   ══════════════════════════════════════════════════════════════ */

// ── Estado ────────────────────────────────────────────────────
let enviando = false;
let abortController = null;

// ── Inicialización ────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  verificarEstado();
  configurarInput();
});

// ── Verificar estado de Ollama ────────────────────────────────
async function verificarEstado() {
  const dot  = document.getElementById('status-dot');
  const text = document.getElementById('status-text');

  try {
    const res  = await fetch('/api/estado');
    const data = await res.json();

    if (data.ollama_disponible) {
      dot.className  = 'status-dot status-ok';
      text.textContent = 'En línea';
    } else {
      dot.className  = 'status-dot status-error';
      text.textContent = 'No disponible';
      mostrarErrorSistema(data.mensaje);
    }
  } catch {
    dot.className  = 'status-dot status-error';
    text.textContent = 'Error de conexión';
  }
}

function mostrarErrorSistema(mensaje) {
  const chat = document.getElementById('chat-messages');
  const div  = document.createElement('div');
  div.className = 'message message-bot';
  div.innerHTML = `
    <div class="message-avatar">⚠️</div>
    <div class="message-body">
      <div class="message-bubble" style="border-color:#ff6b6b;background:#fff5f5;">
        <strong>Advertencia del sistema:</strong><br>${mensaje}
      </div>
    </div>`;
  chat.appendChild(div);
  scrollAbajo();
}

// ── Configurar input ──────────────────────────────────────────
function configurarInput() {
  const input = document.getElementById('user-input');

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!enviando) enviarMensaje();
    }
  });

  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
  });
}

// ── Enviar sugerencia rápida ──────────────────────────────────
function enviarSugerencia(texto) {
  const input = document.getElementById('user-input');
  input.value = texto;
  enviarMensaje();
}

// ── Enviar mensaje principal ──────────────────────────────────
async function enviarMensaje() {
  const input   = document.getElementById('user-input');
  const mensaje = input.value.trim();

  if (!mensaje) return;

  // Si hay un stream activo, cancelarlo
  if (abortController) {
    abortController.abort();
    abortController = null;
    document.querySelectorAll('[id^="typing-"]').forEach(el => el.remove());
  }

  // Ocultar sugerencias después del primer mensaje
  document.getElementById('suggestions').style.display = 'none';

  // Agregar mensaje del usuario
  agregarMensaje(mensaje, 'user');
  input.value = '';
  input.style.height = 'auto';

  setEnviando(true);

  // Pausa natural antes de mostrar los puntitos (como si el vendedor viera el mensaje primero)
  const pausaLectura = 2000 + Math.random() * 2000; // 2–4 segundos
  await new Promise(r => setTimeout(r, pausaLectura));

  // Mostrar indicador de escritura
  const idTyping = mostrarTyping();

  abortController = new AbortController();

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mensaje }),
      signal: abortController.signal,
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
    let   buffer  = '';
    let   currentTypingId = idTyping;

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
        }

        else if (evento.tipo === 'typing') {
          // Nuevo indicador entre mensajes
          currentTypingId = mostrarTyping();
        }

        else if (evento.tipo === 'fin') {
          if (currentTypingId) quitarTyping(currentTypingId);
          abortController = null;
          setEnviando(false);
        }
      }
    }

  } catch (err) {
    if (err.name === 'AbortError') {
      // Cancelado por nuevo mensaje del usuario — no mostrar error
      setEnviando(false);
      return;
    }
    quitarTyping(idTyping);
    agregarMensaje('Perdoná, se me fue la conexión un momento 😅 ¿Me repetís lo que necesitabas?', 'bot');
    abortController = null;
    setEnviando(false);
  }
}

// ── Helpers de mensajes ───────────────────────────────────────
function agregarMensaje(texto, rol) {
  const chat   = document.getElementById('chat-messages');
  const esBot  = rol === 'bot';
  const div    = document.createElement('div');
  div.className = `message message-${esBot ? 'bot' : 'user'}`;

  const hora = new Date().toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' });

  div.innerHTML = `
    <div class="message-avatar">${esBot ? '🤖' : '👤'}</div>
    <div class="message-body">
      <div class="message-bubble">${formatearTexto(texto)}</div>
      <span class="message-time">${hora}</span>
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
  div.className = 'message message-bot';
  div.innerHTML = `
    <div class="message-avatar">🤖</div>
    <div class="message-body">
      <div class="message-bubble">
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
    // Negrita: **texto**
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    // Cursiva: *texto*
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    // Listas con guión
    .replace(/^- (.+)$/gm, '<li>$1</li>')
    // Listas numéricas
    .replace(/^\d+\. (.+)$/gm, '<li>$1</li>')
    // Saltos de línea
    .replace(/\n/g, '<br>')
    // Envolver listas
    .replace(/(<li>.*?<\/li>(\s*<br>)*)+/gs, (m) => `<ul>${m.replace(/<br>/g, '')}</ul>`);
}

function scrollAbajo() {
  const chat = document.getElementById('chat-messages');
  chat.scrollTop = chat.scrollHeight;
}

function setEnviando(estado) {
  enviando = estado;
  document.getElementById('send-icon').textContent = estado ? '⏳' : '➤';
}

// ── Descargar conversación ────────────────────────────────────
function descargarConversacion() {
  const mensajes = document.querySelectorAll('#chat-messages .message');
  if (mensajes.length === 0) return;

  const fecha = new Date().toLocaleString('es-AR', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit'
  }).replace(/[/:,\s]/g, '-').replace(/-+/g, '-');

  let texto = `Conversación – Neumáticos Martinez\n${new Date().toLocaleString('es-AR')}\n${'─'.repeat(40)}\n\n`;

  mensajes.forEach(msg => {
    const esBot  = msg.classList.contains('message-bot');
    const bubble = msg.querySelector('.message-bubble');
    const hora   = msg.querySelector('.message-time');
    if (!bubble) return;

    // Saltar typing indicators
    if (bubble.querySelector('.typing-dots')) return;

    const remitente = esBot ? 'Rodrigo' : 'Vos';
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

// ── Limpiar chat ──────────────────────────────────────────────
async function limpiarChat() {
  if (!confirm('¿Desea iniciar una nueva conversación?')) return;

  try { await fetch('/api/limpiar', { method: 'POST' }); } catch {}

  const chat = document.getElementById('chat-messages');
  chat.innerHTML = `
    <div class="message message-bot">
      <div class="message-avatar">🤖</div>
      <div class="message-body">
        <div class="message-bubble">
          <p>¡Hola! Soy Rodrigo de Neumáticos Martinez. ¿Qué estás buscando?</p>
        </div>
        <span class="message-time">Ahora</span>
      </div>
    </div>`;

  document.getElementById('suggestions').style.display = 'flex';
  actualizarCarrito();
}
