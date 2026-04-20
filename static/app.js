/* ══════════════════════════════════════════════════════════════
   Neumáticos Martinez – Frontend JavaScript
   ══════════════════════════════════════════════════════════════ */

// ── Estado ────────────────────────────────────────────────────
let enviando = false;

// ── Inicialización ────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  verificarEstado();
  configurarInput();
  configurarModeloSelect();
  actualizarCarrito();
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
      text.textContent = `✓ ${data.modelo}`;
    } else {
      dot.className  = 'status-dot status-error';
      text.textContent = 'Ollama no disponible';
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

// ── Configurar selector de modelo ────────────────────────────
function configurarModeloSelect() {
  const select = document.getElementById('model-select');
  select.addEventListener('change', async () => {
    const modelo = select.value;
    try {
      const res  = await fetch('/api/modelo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ modelo }),
      });
      const data = await res.json();
      const text = document.getElementById('status-text');
      text.textContent = `✓ ${modelo}`;
      verificarEstado();
    } catch {}
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

  if (!mensaje || enviando) return;

  // Ocultar sugerencias después del primer mensaje
  document.getElementById('suggestions').style.display = 'none';

  // Agregar mensaje del usuario
  agregarMensaje(mensaje, 'user');
  input.value = '';
  input.style.height = 'auto';

  // Mostrar indicador de escritura
  const idTyping = mostrarTyping();

  // Deshabilitar envío
  setEnviando(true);

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mensaje }),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
    let   buffer  = '';
    let   bubbleEl = null;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lineas = buffer.split('\n');
      buffer = lineas.pop(); // guardar línea incompleta

      for (const linea of lineas) {
        if (!linea.startsWith('data: ')) continue;
        const jsonStr = linea.slice(6).trim();
        if (!jsonStr) continue;

        let evento;
        try { evento = JSON.parse(jsonStr); } catch { continue; }

        if (evento.tipo === 'texto') {
          // Eliminar typing indicator en primer chunk
          quitarTyping(idTyping);

          if (!bubbleEl) {
            bubbleEl = crearBurbujaBotStreaming();
          }
          agregarTextoStreaming(bubbleEl, evento.contenido);
        }

        else if (evento.tipo === 'carrito') {
          actualizarCarritoUI(evento.contenido);
        }

        else if (evento.tipo === 'error') {
          quitarTyping(idTyping);
          agregarMensaje(`❌ Error: ${evento.contenido}`, 'bot');
        }

        else if (evento.tipo === 'fin') {
          finalizarBurbujaStreaming(bubbleEl);
          setEnviando(false);
        }
      }
    }

  } catch (err) {
    quitarTyping(idTyping);
    agregarMensaje('Lo siento, ocurrió un error al procesar su solicitud. Por favor intente de nuevo.', 'bot');
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

function crearBurbujaBotStreaming() {
  const chat = document.getElementById('chat-messages');
  const hora = new Date().toLocaleTimeString('es', { hour: '2-digit', minute: '2-digit' });
  const div  = document.createElement('div');
  div.className = 'message message-bot';
  div.innerHTML = `
    <div class="message-avatar">🤖</div>
    <div class="message-body">
      <div class="message-bubble streaming-bubble"></div>
      <span class="message-time">${hora}</span>
    </div>`;
  chat.appendChild(div);
  scrollAbajo();
  return div.querySelector('.streaming-bubble');
}

let _textoAcumulado = '';

function agregarTextoStreaming(burbuja, chunk) {
  _textoAcumulado += chunk;
  burbuja.innerHTML = formatearTexto(_textoAcumulado) + '<span class="cursor">▌</span>';
  scrollAbajo();
}

function finalizarBurbujaStreaming(burbuja) {
  if (burbuja) {
    burbuja.innerHTML = formatearTexto(_textoAcumulado);
  }
  _textoAcumulado = '';
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
  const btn   = document.getElementById('btn-send');
  const input = document.getElementById('user-input');
  btn.disabled   = estado;
  input.disabled = estado;
  document.getElementById('send-icon').textContent = estado ? '⏳' : '➤';
}

// ── Carrito ───────────────────────────────────────────────────
async function actualizarCarrito() {
  try {
    const res  = await fetch('/api/carrito');
    const data = await res.json();
    actualizarCarritoUI(data);
  } catch {}
}

function actualizarCarritoUI(data) {
  const content  = document.getElementById('cart-content');
  const footer   = document.getElementById('cart-footer');
  const count    = document.getElementById('cart-count');
  const total    = document.getElementById('cart-total');
  const items    = data.carrito || [];

  // Badge
  const totalItems = items.reduce((s, i) => s + i.cantidad, 0);
  count.textContent  = totalItems;
  count.className    = 'cart-count ' + (totalItems > 0 ? '' : 'badge-empty');

  if (items.length === 0) {
    content.innerHTML = `
      <div class="cart-empty">
        <p>🛞</p>
        <p>Su carrito está vacío</p>
        <p class="cart-empty-hint">Pida al asistente que agregue neumáticos a su carrito</p>
      </div>`;
    footer.style.display = 'none';
    return;
  }

  content.innerHTML = items.map(item => `
    <div class="cart-item">
      <div class="cart-item-header">
        <div>
          <div class="cart-item-name">${item.marca} ${item.modelo}</div>
          <div class="cart-item-size">${item.medida}</div>
        </div>
        <div class="cart-item-price">$${item.total_linea.toFixed(2)}</div>
      </div>
      <div class="cart-item-meta">
        <span>${item.cantidad}x a $${item.precio_unitario.toFixed(2)}</span>
        <span>${item.instalacion_incluida
          ? '<span class="cart-item-install">✓ Instalación</span>'
          : ''
        }</span>
      </div>
    </div>
  `).join('');

  total.textContent    = '$' + (data.subtotal || 0).toFixed(2);
  footer.style.display = 'block';
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
          <p>¡Conversación reiniciada! 🔄</p>
          <p>¿En qué puedo ayudarle hoy?</p>
        </div>
        <span class="message-time">Ahora</span>
      </div>
    </div>`;

  document.getElementById('suggestions').style.display = 'flex';
  _textoAcumulado = '';
  actualizarCarrito();
}
