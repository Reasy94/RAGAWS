import { useState, useRef, useEffect } from "react";

const API_URL = import.meta.env.VITE_API_URL;
const UPLOAD_LAMBDA_URL = import.meta.env.VITE_UPLOAD_URL;
const FEEDBACK_URL = import.meta.env.VITE_API_URL?.replace("/query", "/feedback");

const styles = `
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&family=Playfair+Display:wght@600&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:          #0a0e1a;
    --bg-surface:  #0f1422;
    --bg-elevated: #151b2e;
    --bg-card:     #1a2038;
    --border:      rgba(255,255,255,0.07);
    --border-mid:  rgba(255,255,255,0.12);
    --amber:       #c8a255;
    --amber-dim:   rgba(200,162,85,0.12);
    --amber-text:  #e8c87a;
    --slate:       #8b98b8;
    --text-primary:   #e8ecf4;
    --text-secondary: #8b98b8;
    --text-dim:       rgba(139,152,184,0.45);
    --success:     #3d9970;
    --error:       #c0392b;
    --font-sans:   'Inter', system-ui, sans-serif;
    --font-mono:   'JetBrains Mono', monospace;
    --font-serif:  'Playfair Display', Georgia, serif;
  }

  html, body, #root { height: 100%; background: var(--bg); color: var(--text-primary); font-family: var(--font-sans); overflow: hidden; }

  .app { display: flex; height: 100vh; }

  .sidebar {
    width: 64px;
    background: var(--bg-surface);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 20px 0;
    gap: 6px;
    flex-shrink: 0;
  }

  .sidebar-mark {
    width: 32px;
    height: 32px;
    border: 1.5px solid var(--amber);
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 20px;
    font-family: var(--font-serif);
    font-size: 14px;
    color: var(--amber);
    letter-spacing: 0.05em;
  }

  .sidebar-divider { width: 28px; height: 1px; background: var(--border); margin: 6px 0; }

  .nav-btn {
    width: 40px; height: 40px;
    border: 1px solid transparent;
    background: transparent;
    cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    color: var(--text-dim);
    transition: all 0.15s ease;
  }

  .nav-btn:hover { color: var(--text-secondary); border-color: var(--border-mid); }
  .nav-btn.active { color: var(--amber); border-color: rgba(200,162,85,0.3); background: var(--amber-dim); }
  .nav-btn svg { width: 16px; height: 16px; }

  .main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

  .topbar {
    padding: 0 28px;
    height: 52px;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: var(--bg-surface);
    flex-shrink: 0;
  }

  .topbar-left { display: flex; align-items: center; gap: 12px; }
  .topbar-label { font-size: 11px; font-weight: 600; letter-spacing: 0.14em; text-transform: uppercase; color: var(--text-dim); font-family: var(--font-mono); }
  .topbar-sep { width: 1px; height: 16px; background: var(--border-mid); }
  .topbar-title { font-size: 13px; font-weight: 500; color: var(--text-secondary); }

  .status-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--amber); }
  @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.3} }
  .status-dot.loading { animation: blink 1s ease-in-out infinite; }

  .chat-page { display: flex; flex-direction: column; height: 100%; }

  .messages { flex: 1; overflow-y: auto; padding: 28px; display: flex; flex-direction: column; gap: 20px; scrollbar-width: thin; scrollbar-color: var(--border) transparent; }
  .messages::-webkit-scrollbar { width: 3px; }
  .messages::-webkit-scrollbar-thumb { background: var(--border-mid); }

  .empty {
    flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: 12px; color: var(--text-dim);
  }
  .empty-mark { font-family: var(--font-serif); font-size: 32px; color: var(--amber); opacity: 0.4; margin-bottom: 8px; }
  .empty-title { font-size: 16px; font-weight: 500; color: var(--text-secondary); letter-spacing: -0.01em; }
  .empty-sub { font-size: 12px; font-family: var(--font-mono); color: var(--text-dim); }

  @keyframes fadein { from{opacity:0;transform:translateY(6px)} to{opacity:1;transform:translateY(0)} }

  .msg { display: flex; gap: 10px; animation: fadein 0.25s ease; max-width: 820px; }
  .msg.user { flex-direction: row-reverse; align-self: flex-end; }

  .msg-avatar {
    width: 28px; height: 28px;
    display: flex; align-items: center; justify-content: center;
    font-size: 10px; font-weight: 600; font-family: var(--font-mono);
    flex-shrink: 0; margin-top: 2px;
    border: 1px solid var(--border-mid);
    color: var(--text-dim);
  }
  .msg.user .msg-avatar { border-color: rgba(200,162,85,0.3); color: var(--amber); }

  .msg-body { max-width: calc(100% - 38px); }

  .msg-bubble {
    padding: 12px 16px;
    font-size: 14px; line-height: 1.75;
  }
  .msg.user .msg-bubble {
    background: var(--bg-card);
    border: 1px solid rgba(200,162,85,0.2);
    color: var(--text-primary);
  }
  .msg.assistant .msg-bubble {
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    color: var(--text-primary);
    border-left: 2px solid var(--amber);
  }

  .msg-sources {
    margin-top: 10px; padding-top: 10px;
    border-top: 1px solid var(--border);
    display: flex; flex-wrap: wrap; gap: 5px;
  }
  .source-pill {
    padding: 2px 8px;
    background: var(--amber-dim);
    border: 1px solid rgba(200,162,85,0.2);
    font-size: 10px; font-family: var(--font-mono);
    color: var(--amber-text);
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 240px;
  }

  .feedback-row { display: flex; align-items: center; gap: 6px; margin-top: 8px; }
  .feedback-hint { font-size: 10px; font-family: var(--font-mono); color: var(--text-dim); margin-right: 2px; }
  .fb-btn {
    width: 24px; height: 24px;
    border: 1px solid var(--border-mid); background: transparent; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    color: var(--text-dim); transition: all 0.15s ease;
  }
  .fb-btn:hover:not(:disabled) { border-color: var(--amber); color: var(--amber); background: var(--amber-dim); }
  .fb-btn.voted { border-color: var(--amber); color: var(--amber); background: var(--amber-dim); cursor: default; }
  .fb-btn svg { width: 11px; height: 11px; }
  .fb-thanks { font-size: 10px; font-family: var(--font-mono); color: var(--amber); }

  .typing-wrap { display: flex; gap: 10px; align-items: flex-start; }
  .typing {
    padding: 12px 16px;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-left: 2px solid var(--amber);
    display: flex; gap: 5px; align-items: center;
  }
  .dot { width: 5px; height: 5px; border-radius: 50%; background: var(--amber); opacity: 0.4; animation: dotpulse 1.2s ease-in-out infinite; }
  .dot:nth-child(2){animation-delay:0.2s} .dot:nth-child(3){animation-delay:0.4s}
  @keyframes dotpulse { 0%,60%,100%{transform:translateY(0);opacity:0.4} 30%{transform:translateY(-4px);opacity:1} }

  .input-area {
    padding: 16px 28px 20px;
    border-top: 1px solid var(--border);
    background: var(--bg-surface);
  }
  .input-row {
    display: flex; gap: 10px; align-items: flex-end;
    background: var(--bg-elevated);
    border: 1px solid var(--border-mid);
    padding: 10px 10px 10px 16px;
    transition: border-color 0.15s;
  }
  .input-row:focus-within { border-color: rgba(200,162,85,0.4); }
  .chat-input {
    flex: 1; background: transparent; border: none; outline: none;
    color: var(--text-primary); font-family: var(--font-sans); font-size: 14px;
    resize: none; min-height: 22px; max-height: 100px; line-height: 1.6;
    scrollbar-width: none;
  }
  .chat-input::placeholder { color: var(--text-dim); }
  .send-btn {
    width: 32px; height: 32px;
    background: var(--amber); border: none; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    color: #0a0e1a; transition: opacity 0.15s; flex-shrink: 0;
  }
  .send-btn:hover:not(:disabled) { opacity: 0.85; }
  .send-btn:disabled { opacity: 0.3; cursor: not-allowed; }
  .send-btn svg { width: 14px; height: 14px; }

  .upload-page { flex: 1; padding: 36px 44px; overflow-y: auto; scrollbar-width: thin; scrollbar-color: var(--border) transparent; }
  .page-header { margin-bottom: 32px; }
  .page-label { font-size: 10px; font-family: var(--font-mono); color: var(--amber); letter-spacing: 0.12em; text-transform: uppercase; margin-bottom: 8px; }
  .page-title { font-family: var(--font-serif); font-size: 24px; font-weight: 600; color: var(--text-primary); letter-spacing: -0.01em; }

  .drop-zone {
    border: 1px dashed var(--border-mid); padding: 52px 36px;
    text-align: center; cursor: pointer;
    transition: all 0.2s ease; background: var(--bg-surface);
  }
  .drop-zone:hover, .drop-zone.drag { border-color: rgba(200,162,85,0.4); background: var(--bg-elevated); }
  .drop-icon { font-size: 28px; margin-bottom: 14px; color: var(--amber); opacity: 0.5; }
  .drop-title { font-size: 15px; font-weight: 500; margin-bottom: 6px; color: var(--text-secondary); }
  .drop-sub { font-size: 12px; font-family: var(--font-mono); color: var(--text-dim); }
  .drop-sub span { color: var(--amber-text); text-decoration: underline; }
  input[type=file] { display: none; }

  .file-list { margin-top: 24px; display: flex; flex-direction: column; gap: 8px; }
  .file-list-label { font-size: 10px; font-family: var(--font-mono); letter-spacing: 0.1em; text-transform: uppercase; color: var(--text-dim); margin-bottom: 4px; }
  .file-item {
    display: flex; align-items: center; gap: 12px;
    padding: 14px 16px; background: var(--bg-elevated);
    border: 1px solid var(--border); animation: fadein 0.2s ease;
    transition: border-color 0.2s;
  }
  .file-item.uploading { border-color: rgba(200,162,85,0.3); }
  .file-item.done { border-color: rgba(61,153,112,0.3); }
  .file-item.error { border-color: rgba(192,57,43,0.3); }

  .file-icon { width: 32px; height: 32px; background: var(--amber-dim); border: 1px solid rgba(200,162,85,0.2); display: flex; align-items: center; justify-content: center; font-size: 14px; flex-shrink: 0; color: var(--amber); }
  .file-info { flex: 1; min-width: 0; }
  .file-name { font-size: 13px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; margin-bottom: 3px; }
  .file-meta { font-size: 11px; font-family: var(--font-mono); color: var(--text-dim); }
  .file-status { font-size: 11px; font-family: var(--font-mono); flex-shrink: 0; }
  .file-status.uploading { color: var(--amber-text); }
  .file-status.done { color: var(--success); }
  .file-status.error { color: var(--error); }

  .progress-wrap { width: 100%; height: 1px; background: var(--border); margin-top: 6px; }
  .progress-bar { height: 100%; background: var(--amber); transition: width 0.3s ease; }

  .action-row { margin-top: 20px; display: flex; gap: 10px; align-items: center; }
  .upload-btn {
    padding: 10px 24px;
    background: var(--amber); border: none;
    color: #0a0e1a; font-family: var(--font-sans); font-size: 13px; font-weight: 600;
    cursor: pointer; transition: opacity 0.15s; letter-spacing: 0.02em;
  }
  .upload-btn:hover:not(:disabled) { opacity: 0.85; }
  .upload-btn:disabled { opacity: 0.3; cursor: not-allowed; }
  .remove-btn {
    width: 24px; height: 24px; border: 1px solid var(--border); background: transparent;
    cursor: pointer; display: flex; align-items: center; justify-content: center;
    color: var(--text-dim); transition: all 0.15s; flex-shrink: 0;
  }
  .remove-btn:hover { border-color: var(--error); color: var(--error); }
  .remove-btn svg { width: 10px; height: 10px; }

  .cached-badge {
    display: inline-flex; align-items: center; gap: 4px;
    padding: 2px 7px; font-size: 10px; font-family: var(--font-mono);
    color: var(--amber-text); background: var(--amber-dim);
    border: 1px solid rgba(200,162,85,0.2); margin-left: 8px;
  }
`;

const ChatIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
  </svg>
);
const UploadIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
    <polyline points="17 8 12 3 7 8"/>
    <line x1="12" y1="3" x2="12" y2="15"/>
  </svg>
);
const SendIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="22" y1="2" x2="11" y2="13"/>
    <polygon points="22 2 15 22 11 13 2 9 22 2"/>
  </svg>
);
const XIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
  </svg>
);
const ThumbUp = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3H14z"/>
    <path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3"/>
  </svg>
);
const ThumbDown = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3H10z"/>
    <path d="M17 2h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17"/>
  </svg>
);
const DocIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" width="16" height="16">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
    <polyline points="14 2 14 8 20 8"/>
  </svg>
);

function formatBytes(b) {
  if (b < 1024) return b + " B";
  if (b < 1048576) return (b / 1024).toFixed(1) + " KB";
  return (b / 1048576).toFixed(1) + " MB";
}

function FeedbackButtons({ queryId }) {
  const [vote, setVote] = useState(null);

  const handleVote = async (type) => {
    if (vote || !queryId) return;
    setVote(type);
    try {
      await fetch(FEEDBACK_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query_id: queryId, feedback: type === "up" }),
      });
    } catch (e) {
      console.error("Feedback error:", e);
    }
  };

  return (
    <div className="feedback-row">
      <span className="feedback-hint">useful?</span>
      <button className={`fb-btn ${vote === "up" ? "voted" : ""}`} onClick={() => handleVote("up")} disabled={!!vote} title="Helpful">
        <ThumbUp />
      </button>
      <button className={`fb-btn ${vote === "down" ? "voted" : ""}`} onClick={() => handleVote("down")} disabled={!!vote} title="Not helpful">
        <ThumbDown />
      </button>
      {vote && <span className="fb-thanks">recorded</span>}
    </div>
  );
}

function ChatPage() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const sessionId = useRef(crypto.randomUUID());
  const endRef = useRef(null);
  const taRef = useRef(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, loading]);

  const resize = () => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 100) + "px";
  };

  const send = async () => {
    if (!input.trim() || loading) return;
    const q = input.trim();
    setMessages(p => [...p, { role: "user", content: q }]);
    setInput("");
    if (taRef.current) taRef.current.style.height = "auto";
    setLoading(true);

    try {
      const res = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: q, session_id: sessionId.current }),
      });
      const data = await res.json();
      setMessages(p => [...p, {
        role: "assistant",
        id: Date.now().toString(),
        query_id: data.query_id || null,
        content: data.response || data.message || JSON.stringify(data),
        sources: data.sources || [],
        cached: data.cached || false,
      }]);
    } catch {
      setMessages(p => [...p, {
        role: "assistant",
        id: Date.now().toString(),
        content: "Connection error. Please check your API configuration.",
        error: true,
      }]);
    }
    setLoading(false);
  };

  return (
    <div className="chat-page">
      <div className="topbar">
        <div className="topbar-left">
          <div className={`status-dot ${loading ? "loading" : ""}`} />
          <div className="topbar-sep" />
          <span className="topbar-label">document intelligence</span>
          <div className="topbar-sep" />
          <span className="topbar-title" style={{ fontFamily: "var(--font-mono)", fontSize: "11px" }}>
            {sessionId.current.slice(0, 8)}
          </span>
        </div>
        <span className="topbar-label" style={{ color: "var(--amber)", fontSize: "10px" }}>RAG · v3</span>
      </div>

      <div className="messages">
        {messages.length === 0 ? (
          <div className="empty">
            <div className="empty-mark">⊗</div>
            <div className="empty-title">Ready for queries</div>
            <div className="empty-sub">World Bank · IMF · Economic Research</div>
          </div>
        ) : (
          messages.map((msg, i) => (
            <div key={i} className={`msg ${msg.role}`}>
              <div className="msg-avatar">{msg.role === "user" ? "U" : "AI"}</div>
              <div className="msg-body">
                <div className="msg-bubble">
                  {msg.content}
                  {msg.cached && <span className="cached-badge">↺ cached</span>}
                  {msg.sources?.length > 0 && (
                    <div className="msg-sources">
                      {msg.sources.map((s, j) => (
                        <span key={j} className="source-pill">
                          {s.file_name} · p.{s.page_number}
                        </span>
                      ))}
                    </div>
                  )}
                  {msg.role === "assistant" && !msg.error && (
                    <FeedbackButtons queryId={msg.query_id} />
                  )}
                </div>
              </div>
            </div>
          ))
        )}
        {loading && (
          <div className="msg assistant">
            <div className="msg-avatar">AI</div>
            <div className="typing"><div className="dot"/><div className="dot"/><div className="dot"/></div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="input-area">
        <div className="input-row">
          <textarea
            ref={taRef}
            className="chat-input"
            placeholder="Query your financial documents..."
            value={input}
            onChange={e => { setInput(e.target.value); resize(); }}
            onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
            rows={1}
          />
          <button className="send-btn" onClick={send} disabled={!input.trim() || loading}>
            <SendIcon />
          </button>
        </div>
      </div>
    </div>
  );
}

function UploadPage() {
  const [files, setFiles] = useState([]);
  const [drag, setDrag] = useState(false);
  const inputRef = useRef(null);

  const addFiles = (raw) => {
    const pdfs = Array.from(raw).filter(f => f.type === "application/pdf");
    setFiles(p => [...p, ...pdfs.map(f => ({ file: f, id: crypto.randomUUID(), status: "pending", progress: 0 }))]);
  };

  const remove = (id) => setFiles(p => p.filter(f => f.id !== id));

  const uploadAll = async () => {
    for (const item of files.filter(f => f.status === "pending")) {
      setFiles(p => p.map(f => f.id === item.id ? { ...f, status: "uploading" } : f));
      try {
        const res = await fetch(UPLOAD_LAMBDA_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ filename: item.file.name, content_type: "application/pdf" }),
        });
        const { upload_url } = await res.json();
        await fetch(upload_url, { method: "PUT", body: item.file, headers: { "Content-Type": "application/pdf" } });
        setFiles(p => p.map(f => f.id === item.id ? { ...f, status: "done", progress: 100 } : f));
      } catch {
        setFiles(p => p.map(f => f.id === item.id ? { ...f, status: "error" } : f));
      }
    }
  };

  const pendingCount = files.filter(f => f.status === "pending").length;

  return (
    <div className="upload-page">
      <div className="topbar" style={{ margin: "-36px -44px 32px", padding: "0 44px" }}>
        <div className="topbar-left">
          <div className="status-dot" />
          <div className="topbar-sep" />
          <span className="topbar-label">document ingestion</span>
        </div>
      </div>

      <div className="page-header">
        <div className="page-label">// corpus management</div>
        <div className="page-title">Upload Documents</div>
      </div>

      <div
        className={`drop-zone ${drag ? "drag" : ""}`}
        onDragOver={e => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={e => { e.preventDefault(); setDrag(false); addFiles(e.dataTransfer.files); }}
        onClick={() => inputRef.current?.click()}
      >
        <div className="drop-icon">⊕</div>
        <div className="drop-title">Drop PDF files here</div>
        <div className="drop-sub">or <span>browse files</span> from your machine</div>
        <input ref={inputRef} type="file" accept=".pdf" multiple onChange={e => addFiles(e.target.files)} />
      </div>

      {files.length > 0 && (
        <div className="file-list">
          <div className="file-list-label">{files.length} file{files.length !== 1 ? "s" : ""} queued</div>
          {files.map(item => (
            <div key={item.id} className={`file-item ${item.status}`}>
              <div className="file-icon"><DocIcon /></div>
              <div className="file-info">
                <div className="file-name">{item.file.name}</div>
                <div className="file-meta">{formatBytes(item.file.size)}</div>
                {item.status === "uploading" && (
                  <div className="progress-wrap"><div className="progress-bar" style={{ width: item.progress + "%" }} /></div>
                )}
              </div>
              <div className={`file-status ${item.status}`}>
                {item.status === "pending" && "—"}
                {item.status === "uploading" && "uploading"}
                {item.status === "done" && "✓ done"}
                {item.status === "error" && "✕ failed"}
              </div>
              {item.status === "pending" && (
                <button className="remove-btn" onClick={() => remove(item.id)}><XIcon /></button>
              )}
            </div>
          ))}
          <div className="action-row">
            <button className="upload-btn" onClick={uploadAll} disabled={pendingCount === 0}>
              Ingest {pendingCount > 0 ? pendingCount : ""} {pendingCount === 1 ? "file" : "files"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [page, setPage] = useState("chat");
  return (
    <>
      <style>{styles}</style>
      <div className="app">
        <nav className="sidebar">
          <div className="sidebar-mark">Σ</div>
          <div className="sidebar-divider" />
          <button className={`nav-btn ${page === "chat" ? "active" : ""}`} onClick={() => setPage("chat")} title="Query">
            <ChatIcon />
          </button>
          <button className={`nav-btn ${page === "upload" ? "active" : ""}`} onClick={() => setPage("upload")} title="Ingest">
            <UploadIcon />
          </button>
        </nav>
        <main className="main">
          {page === "chat" ? <ChatPage /> : <UploadPage />}
        </main>
      </div>
    </>
  );
}
