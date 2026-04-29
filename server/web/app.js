// M110-M124 browser client. WebSocket bridge to /ws; same JSON envelope
// shape as the TCP control plane so the same dispatch path serves both.
//
// State model: session, conversations[], selectedConversationId. Push
// envelopes (message_deliver / conversation_updated / call_state) update
// the local store, which then re-renders the list + log.

const $ = (id) => document.getElementById(id);
const els = {
  log: $('log'), composer: $('composer'), text: $('text'),
  connectBtn: $('connect'), usernameInput: $('username'),
  passwordInput: $('password'), deviceInput: $('device'),
  loginBox: $('login'), chatList: $('chatList'),
  chatHeader: $('chatHeader'), emptyChat: $('emptyChat'),
  who: $('whoLabel'), fileInput: $('fileInput'),
  callBtn: $('callBtn'), callDialog: $('callDialog'),
  callStatus: $('callStatus'), calleeUser: $('calleeUser'),
  calleeDevice: $('calleeDevice'), callKind: $('callKind'),
  callInvite: $('callInvite'), callAccept: $('callAccept'),
  callDecline: $('callDecline'), callEnd: $('callEnd'),
  callClose: $('callClose'),
};

let ws = null;
let nextSeq = 1;
let session = null;
const inflight = new Map();
const conversations = new Map();        // conversation_id -> {title, messages, unread, lastSnippet, participants}
let selectedConversationId = null;
let activeCall = null;                  // {callId, state, kind}

function nextCorrelation() { return 'web_' + Math.random().toString(36).slice(2, 10); }

function appendRow(kind, text, attach) {
  const row = document.createElement('div');
  row.className = 'row ' + kind;
  row.textContent = text;
  if (attach) {
    const a = document.createElement('div');
    a.className = 'attach';
    a.textContent = '📎 ' + attach.filename + ' (' + attach.size_bytes + ' B)';
    a.onclick = () => fetchAttachment(attach.attachment_id, attach.filename, attach.mime_type);
    row.appendChild(a);
  }
  els.log.appendChild(row);
  els.log.scrollTop = els.log.scrollHeight;
}

function send(type, payload) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    appendRow('error', 'Not connected.');
    return null;
  }
  const correlation_id = nextCorrelation();
  ws.send(JSON.stringify({
    type, correlation_id,
    session_id: session ? session.session_id : '',
    actor_user_id: session ? session.user_id : '',
    sequence: nextSeq++,
    payload: payload || {},
  }));
  return new Promise((resolve) => { inflight.set(correlation_id, resolve); });
}

function ingestConversation(conv) {
  const existing = conversations.get(conv.conversation_id) || { unread: 0 };
  conversations.set(conv.conversation_id, {
    title: conv.title || conv.conversation_id,
    participants: conv.participant_user_ids || [],
    messages: conv.messages || existing.messages || [],
    unread: existing.unread,
    lastSnippet: (conv.messages && conv.messages.length)
      ? (conv.messages[conv.messages.length - 1].text || '').slice(0, 60)
      : (existing.lastSnippet || ''),
  });
}

function renderChatList() {
  els.chatList.innerHTML = '';
  for (const [id, c] of conversations) {
    const row = document.createElement('div');
    row.className = 'chat-row' + (id === selectedConversationId ? ' active' : '');
    const avatar = document.createElement('div');
    avatar.className = 'chat-avatar';
    avatar.textContent = (c.title[0] || '?').toUpperCase();
    avatar.style.background = colorForId(id);
    row.appendChild(avatar);
    const meta = document.createElement('div');
    meta.className = 'chat-meta';
    const t = document.createElement('div'); t.className = 'chat-title'; t.textContent = c.title; meta.appendChild(t);
    const s = document.createElement('div'); s.className = 'chat-snippet'; s.textContent = c.lastSnippet || '(no messages yet)'; meta.appendChild(s);
    row.appendChild(meta);
    if (c.unread > 0) {
      const u = document.createElement('div'); u.className = 'chat-unread'; u.textContent = c.unread; row.appendChild(u);
    }
    row.onclick = () => selectConversation(id);
    els.chatList.appendChild(row);
  }
}

function colorForId(s) {
  const palette = ["#e17076","#7bc862","#65aadd","#a695e7","#ee7aae","#6ec9cb","#faa774"];
  let h = 0;
  for (let i = 0; i < s.length; ++i) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return palette[h % palette.length];
}

function selectConversation(id) {
  selectedConversationId = id;
  const c = conversations.get(id);
  if (!c) return;
  c.unread = 0;
  els.chatHeader.textContent = c.title + ' · ' + (c.participants.length) + ' members';
  els.emptyChat.style.display = 'none';
  els.log.style.display = 'block';
  els.composer.style.display = 'flex';
  els.log.innerHTML = '';
  for (const m of c.messages) renderMessage(m);
  renderChatList();
}

function renderMessage(m) {
  const isMe = session && m.sender_user_id === session.user_id;
  const text = m.deleted ? '(deleted)' : (m.text || '');
  const attach = m.attachment_id
    ? { attachment_id: m.attachment_id, filename: m.filename || m.attachment_filename || '(file)',
        mime_type: m.mime_type || '', size_bytes: m.size_bytes || 0 }
    : null;
  appendRow(isMe ? 'me' : 'peer', m.sender_user_id + ': ' + text, attach);
}

function ingestPushMessage(env) {
  const m = env.payload;
  const convId = m.conversation_id;
  const c = conversations.get(convId);
  if (!c) return;
  c.messages.push(m);
  c.lastSnippet = (m.text || '').slice(0, 60);
  if (convId !== selectedConversationId) c.unread = (c.unread || 0) + 1;
  if (convId === selectedConversationId) renderMessage(m);
  renderChatList();
}

function handleResponse(env) {
  const cb = inflight.get(env.correlation_id);
  if (cb) { inflight.delete(env.correlation_id); cb(env); }
  switch (env.type) {
    case 'error':
      appendRow('error', '[' + env.payload.code + '] ' + env.payload.message); break;
    case 'message_deliver':
      ingestPushMessage(env); break;
    case 'conversation_updated':
      // Server pushed a fresh conversation snapshot; merge and re-render.
      ingestConversation(env.payload); renderChatList(); break;
    case 'presence_update':
      appendRow('system', 'presence: ' + env.payload.user_id + ' = ' + env.payload.online); break;
    case 'call_state':
      activeCall = { callId: env.payload.call_id, state: env.payload.state, kind: env.payload.kind };
      els.callStatus.textContent = env.payload.call_id + ' · ' + env.payload.state;
      els.callAccept.disabled = env.payload.state !== 'ringing';
      els.callDecline.disabled = env.payload.state !== 'ringing';
      els.callEnd.disabled = ['ended', 'declined', 'canceled'].includes(env.payload.state);
      appendRow('system', 'call ' + env.payload.call_id + ' → ' + env.payload.state);
      break;
  }
}

async function fetchAttachment(attachmentId, filename, mimeType) {
  const resp = await send('attachment_fetch_request', { attachment_id: attachmentId });
  if (!resp || resp.type !== 'attachment_fetch_response') return;
  const p = resp.payload;
  // Server response field is `content_b64` (see protocol.AttachmentFetchResponsePayload).
  const bytes = Uint8Array.from(atob(p.content_b64 || ''), c => c.charCodeAt(0));
  const blob = new Blob([bytes], { type: p.mime_type || mimeType || 'application/octet-stream' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = p.filename || filename || 'attachment';
  document.body.appendChild(a); a.click(); a.remove();
  appendRow('system', 'downloaded ' + (p.filename || filename) + ' (' + p.size_bytes + ' B)');
}

async function uploadAttachment(file) {
  if (!selectedConversationId) { appendRow('error', 'Select a conversation first.'); return; }
  const buf = await file.arrayBuffer();
  // base64-encode in chunks to avoid blowing up the call stack.
  let bin = '';
  const u8 = new Uint8Array(buf);
  for (let i = 0; i < u8.length; i += 0x8000) {
    bin += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000));
  }
  const content_b64 = btoa(bin);
  const resp = await send('message_send_attachment', {
    conversation_id: selectedConversationId,
    filename: file.name,
    mime_type: file.type || 'application/octet-stream',
    size_bytes: file.size,
    content_b64,
  });
  if (!resp || resp.type === 'error') {
    appendRow('error', 'attachment send failed' + (resp ? ': ' + resp.payload.message : ''));
    return;
  }
  appendRow('system', 'sent attachment ' + file.name + ' (' + file.size + ' B)');
}

els.connectBtn.addEventListener('click', async () => {
  if (ws && ws.readyState === WebSocket.OPEN) ws.close();
  const wsUrl = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws';
  ws = new WebSocket(wsUrl);
  ws.onopen = async () => {
    appendRow('system', 'WebSocket open. Logging in...');
    const resp = await send('login_request', {
      username: els.usernameInput.value,
      password: els.passwordInput.value,
      device_id: els.deviceInput.value,
    });
    if (resp && resp.type === 'login_response') {
      session = resp.payload;
      els.who.textContent = session.user_id + ' · ' + session.device_id;
      els.loginBox.classList.add('connected');
      els.callBtn.disabled = false;
      const sync = await send('conversation_sync', { cursors: [] });
      if (sync && sync.type === 'conversation_sync') {
        for (const conv of sync.payload.conversations || []) ingestConversation(conv);
        renderChatList();
        const first = sync.payload.conversations && sync.payload.conversations[0];
        if (first) selectConversation(first.conversation_id);
      }
      // Service worker for PWA push notifications (M124).
      if ('serviceWorker' in navigator) {
        try { await navigator.serviceWorker.register('/sw.js'); } catch (e) { /* dev */ }
      }
    }
  };
  ws.onmessage = (e) => {
    try { handleResponse(JSON.parse(e.data)); }
    catch (err) { appendRow('error', 'parse error: ' + err); }
  };
  ws.onclose = () => appendRow('system', 'WebSocket closed.');
  ws.onerror = (e) => appendRow('error', 'WebSocket error: ' + e);
});

els.composer.addEventListener('submit', async (e) => {
  e.preventDefault();
  if (!session || !selectedConversationId) return;
  const t = els.text.value.trim();
  if (!t) return;
  els.text.value = '';
  await send('message_send', { conversation_id: selectedConversationId, text: t });
});

els.fileInput.addEventListener('change', () => {
  if (els.fileInput.files && els.fileInput.files[0]) {
    uploadAttachment(els.fileInput.files[0]);
    els.fileInput.value = '';
  }
});

// ---- M124: call dialog ----
els.callBtn.addEventListener('click', () => els.callDialog.showModal());
els.callClose.addEventListener('click', () => els.callDialog.close());
els.callInvite.addEventListener('click', () =>
  send('call_invite_request', {
    callee_user_id: els.calleeUser.value.trim(),
    callee_device_id: els.calleeDevice.value.trim(),
    kind: els.callKind.value,
  }));
els.callAccept.addEventListener('click', () =>
  activeCall && send('call_accept_request', { call_id: activeCall.callId }));
els.callDecline.addEventListener('click', () =>
  activeCall && send('call_decline_request', { call_id: activeCall.callId }));
els.callEnd.addEventListener('click', () =>
  activeCall && send('call_end_request', { call_id: activeCall.callId }));
