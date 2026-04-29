// M110 minimal browser client. Talks to /ws via the WebBridgeServer; the
// envelope format is the same line-delimited JSON the TCP control plane
// uses, so the same dispatch path serves both transports.

const log = document.getElementById('log');
const composer = document.getElementById('composer');
const text = document.getElementById('text');
const connectBtn = document.getElementById('connect');
const usernameInput = document.getElementById('username');
const passwordInput = document.getElementById('password');
const deviceInput = document.getElementById('device');
const conversationInput = document.getElementById('conversation');

let ws = null;
let nextSeq = 1;
let session = null;
const inflight = new Map();

function append(kind, msg) {
  const row = document.createElement('div');
  row.className = 'row ' + kind;
  row.textContent = msg;
  log.appendChild(row);
  log.scrollTop = log.scrollHeight;
}

function nextCorrelation() {
  return 'web_' + Math.random().toString(36).slice(2, 10);
}

function send(type, payload) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    append('error', 'Not connected.');
    return null;
  }
  const correlation_id = nextCorrelation();
  const envelope = {
    type,
    correlation_id,
    session_id: session ? session.session_id : '',
    actor_user_id: session ? session.user_id : '',
    sequence: nextSeq++,
    payload: payload || {},
  };
  ws.send(JSON.stringify(envelope));
  return new Promise((resolve) => {
    inflight.set(correlation_id, resolve);
  });
}

function handleResponse(envelope) {
  const cb = inflight.get(envelope.correlation_id);
  if (cb) {
    inflight.delete(envelope.correlation_id);
    cb(envelope);
  }
  if (envelope.type === 'error') {
    append('error', '[' + envelope.payload.code + '] ' + envelope.payload.message);
  } else if (envelope.type === 'message_deliver') {
    const m = envelope.payload;
    append(m.sender_user_id === (session && session.user_id) ? 'me' : 'peer',
           m.sender_user_id + ': ' + m.text);
  } else if (envelope.type === 'presence_update') {
    append('system', 'presence: ' + JSON.stringify(envelope.payload));
  } else if (envelope.type === 'conversation_updated') {
    append('system', 'conversation_updated: ' + envelope.payload.conversation_id);
  }
}

connectBtn.addEventListener('click', async () => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.close();
  }
  const wsUrl = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws';
  ws = new WebSocket(wsUrl);
  ws.onopen = async () => {
    append('system', 'WebSocket open. Logging in...');
    const resp = await send('login_request', {
      username: usernameInput.value,
      password: passwordInput.value,
      device_id: deviceInput.value,
    });
    if (resp && resp.type === 'login_response') {
      session = resp.payload;
      append('system', 'Logged in as ' + session.user_id + ' (session ' + session.session_id + ')');
      // Pull conversation history so the user sees something.
      const sync = await send('conversation_sync', { cursors: [] });
      if (sync && sync.type === 'conversation_sync') {
        for (const conv of sync.payload.conversations || []) {
          append('system', 'conversation ' + conv.conversation_id + ': ' + (conv.messages || []).length + ' messages');
        }
      }
    }
  };
  ws.onmessage = (e) => {
    try {
      handleResponse(JSON.parse(e.data));
    } catch (err) {
      append('error', 'parse error: ' + err);
    }
  };
  ws.onclose = () => append('system', 'WebSocket closed.');
  ws.onerror = (e) => append('error', 'WebSocket error: ' + e);
});

composer.addEventListener('submit', async (e) => {
  e.preventDefault();
  if (!session) {
    append('error', 'Connect first.');
    return;
  }
  const t = text.value.trim();
  if (!t) return;
  text.value = '';
  await send('message_send', {
    conversation_id: conversationInput.value,
    text: t,
  });
});
