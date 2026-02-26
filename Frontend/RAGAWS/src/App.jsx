import { useState, useRef, useEffect } from "react";

const API_URL = import.meta.env.VITE_API_URL || "https://your-api-gateway-url/query";
const UPLOAD_LAMBDA_URL = import.meta.env.VITE_UPLOAD_URL || "https://your-api-gateway-url/upload";

const styles = `
  @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;500;600;700;800&family=DM+Mono:ital,wght@0,300;0,400;0,500;1,300&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg: #050508;
    --bg-surface: #0d0d14;
    --bg-elevated: #13131e;
    --border: rgba(255,255,255,0.06);
    --border-active: rgba(110,80,255,0.4);
    --accent: #6e50ff;
    --accent-bright: #8b6fff;
    --accent-glow: rgba(110,80,255,0.15);
    --accent-2: #3b82f6;
    --text-primary: #f0eeff;
    --text-secondary: rgba(240,238,255,0.5);
    --text-dim: rgba(240,238,255,0.25);
    --success: #22c55e;
    --error: #ef4444;
    --font-display: 'Syne', sans-serif;
    --font-mono: 'DM Mono', monospace;
  }

  html, body, #root {
    height: 100%;
    background: var(--bg);
    color: var(--text-primary);
    font-family: var(--font-display);
    overflow: hidden;
  }

  .app {
    display: flex;
    height: 100vh;
    position: relative;
  }

  /* Ambient background */
  .app::before {
    content: '';
    position: fixed;
    top: -20%;
    left: -10%;
    width: 50vw;
    height: 50vw;
    background: radial-gradient(circle, rgba(110,80,255,0.06) 0%, transparent 70%);
    pointer-events: none;
    z-index: 0;
  }
  .app::after {
    content: '';
    position: fixed;
    bottom: -20%;
    right: -10%;
    width: 40vw;
    height: 40vw;
    background: radial-gradient(circle, rgba(59,130,246,0.05) 0%, transparent 70%);
    pointer-events: none;
    z-index: 0;
  }

  /* Sidebar */
  .sidebar {
    width: 72px;
    background: var(--bg-surface);
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 24px 0;
    gap: 8px;
    position: relative;
    z-index: 10;
    flex-shrink: 0;
  }

  .sidebar-logo {
    width: 36px;
    height: 36px;
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-bottom: 24px;
    font-size: 16px;
    box-shadow: 0 0 20px var(--accent-glow);
  }

  .sidebar-divider {
    width: 32px;
    height: 1px;
    background: var(--border);
    margin: 8px 0;
  }

  .nav-btn {
    width: 44px;
    height: 44px;
    border-radius: 12px;
    border: 1px solid transparent;
    background: transparent;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-dim);
    transition: all 0.2s ease;
    position: relative;
  }

  .nav-btn:hover {
    background: var(--accent-glow);
    color: var(--text-secondary);
    border-color: var(--border-active);
  }

  .nav-btn.active {
    background: var(--accent-glow);
    color: var(--accent-bright);
    border-color: var(--border-active);
    box-shadow: 0 0 12px var(--accent-glow);
  }

  .nav-btn svg {
    width: 18px;
    height: 18px;
  }

  /* Main content */
  .main {
    flex: 1;
    display: flex;
    flex-direction: column;
    position: relative;
    z-index: 1;
    overflow: hidden;
  }

  /* Header */
  .header {
    padding: 20px 32px;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    gap: 16px;
    background: rgba(5,5,8,0.8);
    backdrop-filter: blur(12px);
  }

  .header-title {
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.15em;
    text-transform: uppercase;
    color: var(--text-secondary);
  }

  .header-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--accent);
    box-shadow: 0 0 8px var(--accent);
    animation: pulse 2s ease-in-out infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.5; transform: scale(0.8); }
  }

  /* ─── CHAT PAGE ─── */
  .chat-page {
    display: flex;
    flex-direction: column;
    height: 100%;
    animation: fadeIn 0.3s ease;
  }

  @keyframes fadeIn {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
  }

  .messages-container {
    flex: 1;
    overflow-y: auto;
    padding: 32px;
    display: flex;
    flex-direction: column;
    gap: 24px;
    scrollbar-width: thin;
    scrollbar-color: var(--border) transparent;
  }

  .messages-container::-webkit-scrollbar { width: 4px; }
  .messages-container::-webkit-scrollbar-track { background: transparent; }
  .messages-container::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

  .empty-state {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 16px;
    color: var(--text-dim);
    animation: fadeIn 0.5s ease;
  }

  .empty-icon {
    width: 56px;
    height: 56px;
    border-radius: 16px;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 24px;
    margin-bottom: 8px;
  }

  .empty-title {
    font-size: 18px;
    font-weight: 700;
    color: var(--text-secondary);
    letter-spacing: -0.02em;
  }

  .empty-sub {
    font-size: 13px;
    font-family: var(--font-mono);
    color: var(--text-dim);
  }

  .message {
    display: flex;
    gap: 12px;
    animation: slideIn 0.3s ease;
    max-width: 800px;
  }

  @keyframes slideIn {
    from { opacity: 0; transform: translateX(-8px); }
    to { opacity: 1; transform: translateX(0); }
  }

  .message.user {
    flex-direction: row-reverse;
    align-self: flex-end;
  }

  .message-avatar {
    width: 32px;
    height: 32px;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 13px;
    flex-shrink: 0;
    font-weight: 700;
  }

  .message.user .message-avatar {
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
    color: white;
  }

  .message.assistant .message-avatar {
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    color: var(--accent-bright);
  }

  .message-bubble {
    padding: 14px 18px;
    border-radius: 16px;
    font-size: 14px;
    line-height: 1.7;
    max-width: calc(100% - 44px);
  }

  .message.user .message-bubble {
    background: linear-gradient(135deg, var(--accent), rgba(110,80,255,0.7));
    color: white;
    border-radius: 16px 4px 16px 16px;
  }

  .message.assistant .message-bubble {
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    color: var(--text-primary);
    border-radius: 4px 16px 16px 16px;
  }

  .message-sources {
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid var(--border);
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
  }

  .source-tag {
    padding: 3px 10px;
    background: var(--accent-glow);
    border: 1px solid var(--border-active);
    border-radius: 20px;
    font-size: 11px;
    font-family: var(--font-mono);
    color: var(--accent-bright);
  }

  /* Typing indicator */
  .typing {
    display: flex;
    gap: 4px;
    padding: 14px 18px;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: 4px 16px 16px 16px;
    width: fit-content;
  }

  .typing-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--accent);
    animation: typingDot 1.2s ease-in-out infinite;
  }

  .typing-dot:nth-child(2) { animation-delay: 0.2s; }
  .typing-dot:nth-child(3) { animation-delay: 0.4s; }

  @keyframes typingDot {
    0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
    30% { transform: translateY(-6px); opacity: 1; }
  }

  /* Input area */
  .input-area {
    padding: 24px 32px;
    border-top: 1px solid var(--border);
    background: rgba(5,5,8,0.8);
    backdrop-filter: blur(12px);
  }

  .input-wrapper {
    display: flex;
    align-items: flex-end;
    gap: 12px;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 12px 12px 12px 20px;
    transition: border-color 0.2s ease, box-shadow 0.2s ease;
  }

  .input-wrapper:focus-within {
    border-color: var(--border-active);
    box-shadow: 0 0 0 3px var(--accent-glow);
  }

  .chat-input {
    flex: 1;
    background: transparent;
    border: none;
    outline: none;
    color: var(--text-primary);
    font-family: var(--font-display);
    font-size: 14px;
    resize: none;
    min-height: 24px;
    max-height: 120px;
    line-height: 1.6;
    scrollbar-width: none;
  }

  .chat-input::placeholder { color: var(--text-dim); }

  .send-btn {
    width: 36px;
    height: 36px;
    border-radius: 10px;
    background: var(--accent);
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    transition: all 0.2s ease;
    flex-shrink: 0;
    color: white;
  }

  .send-btn:hover:not(:disabled) {
    background: var(--accent-bright);
    transform: scale(1.05);
    box-shadow: 0 0 16px var(--accent-glow);
  }

  .send-btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }

  .send-btn svg { width: 16px; height: 16px; }

  /* ─── UPLOAD PAGE ─── */
  .upload-page {
    flex: 1;
    padding: 40px 48px;
    overflow-y: auto;
    animation: fadeIn 0.3s ease;
    scrollbar-width: thin;
    scrollbar-color: var(--border) transparent;
  }

  .upload-page-title {
    font-size: 28px;
    font-weight: 800;
    letter-spacing: -0.03em;
    margin-bottom: 8px;
  }

  .upload-page-sub {
    font-size: 14px;
    font-family: var(--font-mono);
    color: var(--text-dim);
    margin-bottom: 40px;
  }

  .drop-zone {
    border: 1.5px dashed var(--border);
    border-radius: 20px;
    padding: 60px 40px;
    text-align: center;
    cursor: pointer;
    transition: all 0.3s ease;
    background: var(--bg-surface);
    position: relative;
    overflow: hidden;
  }

  .drop-zone::before {
    content: '';
    position: absolute;
    inset: 0;
    background: radial-gradient(circle at center, var(--accent-glow) 0%, transparent 70%);
    opacity: 0;
    transition: opacity 0.3s ease;
  }

  .drop-zone:hover::before,
  .drop-zone.dragging::before { opacity: 1; }

  .drop-zone:hover,
  .drop-zone.dragging {
    border-color: var(--border-active);
    background: var(--bg-elevated);
  }

  .drop-icon {
    font-size: 48px;
    margin-bottom: 16px;
    display: block;
    position: relative;
    z-index: 1;
  }

  .drop-title {
    font-size: 18px;
    font-weight: 700;
    margin-bottom: 8px;
    position: relative;
    z-index: 1;
  }

  .drop-sub {
    font-size: 13px;
    font-family: var(--font-mono);
    color: var(--text-dim);
    position: relative;
    z-index: 1;
  }

  .drop-sub span {
    color: var(--accent-bright);
    text-decoration: underline;
    cursor: pointer;
  }

  .file-input { display: none; }

  /* File list */
  .file-list {
    margin-top: 32px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }

  .file-list-title {
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-dim);
    margin-bottom: 4px;
  }

  .file-item {
    display: flex;
    align-items: center;
    gap: 14px;
    padding: 16px 20px;
    background: var(--bg-elevated);
    border: 1px solid var(--border);
    border-radius: 14px;
    transition: border-color 0.2s ease;
    animation: slideIn 0.3s ease;
  }

  .file-item.uploading { border-color: var(--border-active); }
  .file-item.done { border-color: rgba(34,197,94,0.3); }
  .file-item.error { border-color: rgba(239,68,68,0.3); }

  .file-icon {
    width: 40px;
    height: 40px;
    border-radius: 10px;
    background: var(--accent-glow);
    border: 1px solid var(--border-active);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 18px;
    flex-shrink: 0;
  }

  .file-info { flex: 1; min-width: 0; }

  .file-name {
    font-size: 14px;
    font-weight: 600;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    margin-bottom: 4px;
  }

  .file-meta {
    font-size: 12px;
    font-family: var(--font-mono);
    color: var(--text-dim);
  }

  .file-status {
    font-size: 12px;
    font-family: var(--font-mono);
    display: flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
  }

  .file-status.uploading { color: var(--accent-bright); }
  .file-status.done { color: var(--success); }
  .file-status.error { color: var(--error); }

  .progress-bar-wrap {
    width: 100%;
    height: 2px;
    background: var(--border);
    border-radius: 1px;
    margin-top: 8px;
    overflow: hidden;
  }

  .progress-bar {
    height: 100%;
    background: linear-gradient(90deg, var(--accent), var(--accent-2));
    border-radius: 1px;
    transition: width 0.3s ease;
  }

  .upload-btn {
    margin-top: 24px;
    padding: 14px 32px;
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
    border: none;
    border-radius: 12px;
    color: white;
    font-family: var(--font-display);
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s ease;
    letter-spacing: 0.02em;
  }

  .upload-btn:hover:not(:disabled) {
    transform: translateY(-1px);
    box-shadow: 0 8px 24px var(--accent-glow);
  }

  .upload-btn:disabled { opacity: 0.4; cursor: not-allowed; }

  .remove-btn {
    width: 28px;
    height: 28px;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: transparent;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-dim);
    transition: all 0.2s ease;
    flex-shrink: 0;
  }

  .remove-btn:hover { border-color: var(--error); color: var(--error); }
  .remove-btn svg { width: 12px; height: 12px; }
`;

// Icons
const ChatIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
  </svg>
);

const UploadIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
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
    <line x1="18" y1="6" x2="6" y2="18"/>
    <line x1="6" y1="6" x2="18" y2="18"/>
  </svg>
);

function formatBytes(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

// ─── CHAT PAGE ───
function ChatPage() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const autoResize = () => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = Math.min(ta.scrollHeight, 120) + 'px';
  };

  const sendMessage = async () => {
    if (!input.trim() || loading) return;
    const userMsg = { role: "user", content: input.trim() };
    setMessages(prev => [...prev, userMsg]);
    setInput("");
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
    setLoading(true);
    try {
      const res = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: userMsg.content }),
      });
      const data = await res.json();
      setMessages(prev => [...prev, {
        role: "assistant",
        content: data.answer || data.response || data.message || JSON.stringify(data),
        sources: data.sources || [],
      }]);
    } catch {
      setMessages(prev => [...prev, {
        role: "assistant",
        content: "Connection error. Please check your API configuration.",
        error: true,
      }]);
    }
    setLoading(false);
  };

  return (
    <div className="chat-page">
      <div className="header">
        <div className="header-dot" />
        <span className="header-title">RAG Query Interface</span>
      </div>
      <div className="messages-container">
        {messages.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">◈</div>
            <div className="empty-title">Ready to query</div>
            <div className="empty-sub">Ask anything about your documents</div>
          </div>
        ) : (
          messages.map((msg, i) => (
            <div key={i} className={`message ${msg.role}`}>
              <div className="message-avatar">
                {msg.role === "user" ? "U" : "R"}
              </div>
              <div className="message-bubble">
                {msg.content}
                {msg.sources?.length > 0 && (
                  <div className="message-sources">
                    {msg.sources.map((s, j) => (
                      <span key={j} className="source-tag">{s}</span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))
        )}
        {loading && (
          <div className="message assistant">
            <div className="message-avatar">R</div>
            <div className="typing">
              <div className="typing-dot" />
              <div className="typing-dot" />
              <div className="typing-dot" />
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>
      <div className="input-area">
        <div className="input-wrapper">
          <textarea
            ref={textareaRef}
            className="chat-input"
            placeholder="Ask a question about your documents..."
            value={input}
            onChange={e => { setInput(e.target.value); autoResize(); }}
            onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); } }}
            rows={1}
          />
          <button className="send-btn" onClick={sendMessage} disabled={!input.trim() || loading}>
            <SendIcon />
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── UPLOAD PAGE ───
function UploadPage() {
  const [files, setFiles] = useState([]);
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef(null);

  const addFiles = (newFiles) => {
    const pdfs = Array.from(newFiles).filter(f => f.type === "application/pdf");
    setFiles(prev => [
      ...prev,
      ...pdfs.map(f => ({ file: f, id: Math.random().toString(36).slice(2), status: "pending", progress: 0 }))
    ]);
  };

  const removeFile = (id) => setFiles(prev => prev.filter(f => f.id !== id));

  const uploadAll = async () => {
    const pending = files.filter(f => f.status === "pending");
    for (const item of pending) {
      setFiles(prev => prev.map(f => f.id === item.id ? { ...f, status: "uploading", progress: 0 } : f));
      try {
        // Get presigned URL
        const res = await fetch(UPLOAD_LAMBDA_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ filename: item.file.name, content_type: "application/pdf" }),
        });
        const { upload_url } = await res.json();

        // Upload to S3
        await fetch(upload_url, {
          method: "PUT",
          body: item.file,
          headers: { "Content-Type": "application/pdf" },
        });

        setFiles(prev => prev.map(f => f.id === item.id ? { ...f, status: "done", progress: 100 } : f));
      } catch {
        setFiles(prev => prev.map(f => f.id === item.id ? { ...f, status: "error" } : f));
      }
    }
  };

  return (
    <div className="upload-page">
      <div className="header" style={{ margin: "-40px -48px 40px", padding: "20px 48px" }}>
        <div className="header-dot" />
        <span className="header-title">Document Ingestion</span>
      </div>
      <div className="upload-page-title">Upload Documents</div>
      <div className="upload-page-sub">// PDF files are processed and indexed automatically</div>

      <div
        className={`drop-zone ${dragging ? "dragging" : ""}`}
        onDragOver={e => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={e => { e.preventDefault(); setDragging(false); addFiles(e.dataTransfer.files); }}
        onClick={() => fileInputRef.current?.click()}
      >
        <span className="drop-icon">⬡</span>
        <div className="drop-title">Drop PDF files here</div>
        <div className="drop-sub">or <span>browse files</span> from your computer</div>
        <input ref={fileInputRef} type="file" className="file-input" accept=".pdf" multiple onChange={e => addFiles(e.target.files)} />
      </div>

      {files.length > 0 && (
        <div className="file-list">
          <div className="file-list-title">{files.length} file{files.length > 1 ? "s" : ""} selected</div>
          {files.map(item => (
            <div key={item.id} className={`file-item ${item.status}`}>
              <div className="file-icon">📄</div>
              <div className="file-info">
                <div className="file-name">{item.file.name}</div>
                <div className="file-meta">{formatBytes(item.file.size)}</div>
                {item.status === "uploading" && (
                  <div className="progress-bar-wrap">
                    <div className="progress-bar" style={{ width: item.progress + "%" }} />
                  </div>
                )}
              </div>
              <div className={`file-status ${item.status}`}>
                {item.status === "pending" && "— ready"}
                {item.status === "uploading" && "↑ uploading"}
                {item.status === "done" && "✓ done"}
                {item.status === "error" && "✕ error"}
              </div>
              {item.status === "pending" && (
                <button className="remove-btn" onClick={() => removeFile(item.id)}><XIcon /></button>
              )}
            </div>
          ))}
          <button
            className="upload-btn"
            onClick={uploadAll}
            disabled={!files.some(f => f.status === "pending")}
          >
            Upload {files.filter(f => f.status === "pending").length} file{files.filter(f => f.status === "pending").length !== 1 ? "s" : ""}
          </button>
        </div>
      )}
    </div>
  );
}

// ─── APP ───
export default function App() {
  const [page, setPage] = useState("chat");

  return (
    <>
      <style>{styles}</style>
      <div className="app">
        <nav className="sidebar">
          <div className="sidebar-logo">◈</div>
          <div className="sidebar-divider" />
          <button className={`nav-btn ${page === "chat" ? "active" : ""}`} onClick={() => setPage("chat")} title="Chat">
            <ChatIcon />
          </button>
          <button className={`nav-btn ${page === "upload" ? "active" : ""}`} onClick={() => setPage("upload")} title="Upload">
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
