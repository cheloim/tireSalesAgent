const LEVEL_CLASS = { ERROR: 'log-error', WARNING: 'log-warn', CRITICAL: 'log-error' };

function toggleMenu() {
  document.getElementById('nav-menu').classList.toggle('open');
}

function limpiarTerminal() {
  document.getElementById('terminal').innerHTML = '';
}

function conectarServerLogs() {
  const term = document.getElementById('terminal');
  const dot  = document.getElementById('live-dot');
  const upd  = document.getElementById('last-update');

  const es = new EventSource('/api/logs/stream');

  es.onopen = () => {
    dot.classList.add('live');
    upd.textContent = 'En vivo';
  };

  es.onmessage = (e) => {
    try {
      const entry = JSON.parse(e.data);
      const cls   = LEVEL_CLASS[entry.level] || 'log-info';
      const line  = document.createElement('div');
      line.className = 'log-line ' + cls;
      line.textContent = entry.msg;
      term.appendChild(line);
      while (term.children.length > 500) term.removeChild(term.firstChild);
      term.scrollTop = term.scrollHeight;
    } catch (err) { console.error('log parse', err); }
  };

  es.onerror = () => {
    dot.classList.remove('live');
    upd.textContent = 'Reconectando…';
  };
}

conectarServerLogs();
