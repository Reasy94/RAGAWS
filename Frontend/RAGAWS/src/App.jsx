import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import "./App.css";

const API_URL = import.meta.env.VITE_API_URL;
const UPLOAD_LAMBDA_URL = import.meta.env.VITE_UPLOAD_URL;
const FEEDBACK_URL = import.meta.env.VITE_API_URL?.replace(
  "/query",
  "/feedback",
);
const STATS_URL = import.meta.env.VITE_API_URL?.replace("/query", "/stats");

const ChatIcon = () => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.6"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
  </svg>
);

const UploadIcon = () => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.6"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="17 8 12 3 7 8" />
    <line x1="12" y1="3" x2="12" y2="15" />
  </svg>
);

const SendIcon = () => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <line x1="22" y1="2" x2="11" y2="13" />
    <polygon points="22 2 15 22 11 13 2 9 22 2" />
  </svg>
);

const XIcon = () => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <line x1="18" y1="6" x2="6" y2="18" />
    <line x1="6" y1="6" x2="18" y2="18" />
  </svg>
);

const ThumbUp = () => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3H14z" />
    <path d="M7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3" />
  </svg>
);

const ThumbDown = () => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3H10z" />
    <path d="M17 2h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17" />
  </svg>
);

const DashboardIcon = () => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.6"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <rect x="3" y="3" width="7" height="7" />
    <rect x="14" y="3" width="7" height="7" />
    <rect x="14" y="14" width="7" height="7" />
    <rect x="3" y="14" width="7" height="7" />
  </svg>
);

const DocIcon = () => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.6"
    strokeLinecap="round"
    strokeLinejoin="round"
    width="16"
    height="16"
  >
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
    <polyline points="14 2 14 8 20 8" />
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
      <button
        className={`fb-btn ${vote === "up" ? "voted" : ""}`}
        onClick={() => handleVote("up")}
        disabled={!!vote}
        title="Helpful"
      >
        <ThumbUp />
      </button>
      <button
        className={`fb-btn ${vote === "down" ? "voted" : ""}`}
        onClick={() => handleVote("down")}
        disabled={!!vote}
        title="Not helpful"
      >
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

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  const resize = () => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 100) + "px";
  };

  const send = async () => {
    if (!input.trim() || loading) return;
    const q = input.trim();
    setMessages((p) => [...p, { role: "user", content: q }]);
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
      setMessages((p) => [
        ...p,
        {
          role: "assistant",
          id: Date.now().toString(),
          query_id: data.query_id || null,
          content: data.response || data.message || JSON.stringify(data),
          sources: data.sources || [],
          cached: data.cached || false,
          latency_ms: data.latency_ms || null,
        },
      ]);
    } catch {
      setMessages((p) => [
        ...p,
        {
          role: "assistant",
          id: Date.now().toString(),
          content: "Connection error. Please check your API configuration.",
          error: true,
        },
      ]);
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
          <span
            className="topbar-title"
            style={{ fontFamily: "var(--font-mono)", fontSize: "11px" }}
          >
            {sessionId.current.slice(0, 8)}
          </span>
        </div>
        <span
          className="topbar-label"
          style={{ color: "var(--amber)", fontSize: "10px" }}
        >
          RAG · V3
        </span>
      </div>

      <div className="messages">
        {messages.length === 0 ? (
          <div className="empty">
            <div className="empty-mark">⊗</div>
            <div className="empty-title">Ready for queries</div>
            <div className="empty-sub">World Bank GEP · World Bank CMO</div>
          </div>
        ) : (
          messages.map((msg, i) => (
            <div key={i} className={`msg ${msg.role}`}>
              <div className="msg-avatar">
                {msg.role === "user" ? "U" : "AI"}
              </div>
              <div className="msg-body">
                <div className="msg-bubble">
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
                  {msg.cached && <span className="cached-badge">↺ cached</span>}
                  {msg.latency_ms && (
                    <span className="cached-badge" style={{ marginLeft: 4 }}>
                      {(msg.latency_ms / 1000).toFixed(1)}s
                    </span>
                  )}
                  {msg.sources?.length > 0 && (
                    <div className="msg-sources">
                      {msg.sources.some((s) => s.image_url) && (
                        <div className="source-images-row">
                          {msg.sources
                            .filter((s) => s.image_url)
                            .map((s, j) => (
                              <img
                                key={j}
                                src={s.image_url}
                                alt={`${s.chunk_type} from ${s.file_name} p.${s.page_number}`}
                                className="source-image"
                                onClick={() =>
                                  window.open(s.image_url, "_blank")
                                }
                              />
                            ))}
                        </div>
                      )}
                      <div className="source-pills-row">
                        {msg.sources.map((s, j) => (
                          <span key={j} className="source-pill">
                            {s.file_name} · p.{s.page_number}
                            {s.chunk_type !== "TEXT" && (
                              <span className="source-type">
                                {s.chunk_type}
                              </span>
                            )}
                          </span>
                        ))}
                      </div>
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
            <div className="typing">
              <div className="dot" />
              <div className="dot" />
              <div className="dot" />
            </div>
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
            onChange={(e) => {
              setInput(e.target.value);
              resize();
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            rows={1}
          />
          <button
            className="send-btn"
            onClick={send}
            disabled={!input.trim() || loading}
          >
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
    const pdfs = Array.from(raw).filter((f) => f.type === "application/pdf");
    setFiles((p) => [
      ...p,
      ...pdfs.map((f) => ({
        file: f,
        id: crypto.randomUUID(),
        status: "pending",
        progress: 0,
      })),
    ]);
  };

  const remove = (id) => setFiles((p) => p.filter((f) => f.id !== id));

  const uploadAll = async () => {
    for (const item of files.filter((f) => f.status === "pending")) {
      setFiles((p) =>
        p.map((f) => (f.id === item.id ? { ...f, status: "uploading" } : f)),
      );
      try {
        const res = await fetch(UPLOAD_LAMBDA_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            filename: item.file.name,
            content_type: "application/pdf",
          }),
        });
        const { upload_url } = await res.json();
        await fetch(upload_url, {
          method: "PUT",
          body: item.file,
          headers: { "Content-Type": "application/pdf" },
        });
        setFiles((p) =>
          p.map((f) =>
            f.id === item.id ? { ...f, status: "done", progress: 100 } : f,
          ),
        );
      } catch {
        setFiles((p) =>
          p.map((f) => (f.id === item.id ? { ...f, status: "error" } : f)),
        );
      }
    }
  };

  const pendingCount = files.filter((f) => f.status === "pending").length;

  return (
    <div className="upload-page">
      <div
        className="topbar"
        style={{ margin: "-36px -44px 32px", padding: "0 44px" }}
      >
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
        onDragOver={(e) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          addFiles(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
      >
        <div className="drop-icon">⊕</div>
        <div className="drop-title">Drop PDF files here</div>
        <div className="drop-sub">
          or <span>browse files</span> from your machine
        </div>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf"
          multiple
          onChange={(e) => addFiles(e.target.files)}
        />
      </div>

      {files.length > 0 && (
        <div className="file-list">
          <div className="file-list-label">
            {files.length} file{files.length !== 1 ? "s" : ""} queued
          </div>
          {files.map((item) => (
            <div key={item.id} className={`file-item ${item.status}`}>
              <div className="file-icon">
                <DocIcon />
              </div>
              <div className="file-info">
                <div className="file-name">{item.file.name}</div>
                <div className="file-meta">{formatBytes(item.file.size)}</div>
                {item.status === "uploading" && (
                  <div className="progress-wrap">
                    <div
                      className="progress-bar"
                      style={{ width: item.progress + "%" }}
                    />
                  </div>
                )}
              </div>
              <div className={`file-status ${item.status}`}>
                {item.status === "pending" && "—"}
                {item.status === "uploading" && "uploading"}
                {item.status === "done" && "✓ done"}
                {item.status === "error" && "✕ failed"}
              </div>
              {item.status === "pending" && (
                <button className="remove-btn" onClick={() => remove(item.id)}>
                  <XIcon />
                </button>
              )}
            </div>
          ))}
          <div className="action-row">
            <button
              className="upload-btn"
              onClick={uploadAll}
              disabled={pendingCount === 0}
            >
              Ingest {pendingCount > 0 ? pendingCount : ""}{" "}
              {pendingCount === 1 ? "file" : "files"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ── SVG Sparkline chart component ─────────────────────────────────────────────
// ── Chart.js Bar Chart ─────────────────────────────────────────────────────────
function SparklineChart({ data }) {
  const canvasRef = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    if (!data || data.length === 0) return;

    const script = document.createElement("script");
    script.src =
      "https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js";
    script.onload = () => {
      if (chartRef.current) chartRef.current.destroy();
      const ctx = canvasRef.current?.getContext("2d");
      if (!ctx) return;

      chartRef.current = new window.Chart(ctx, {
        type: "bar",
        data: {
          labels: data.map((d) => d.day?.slice(5) || ""),
          datasets: [
            {
              data: data.map((d) => d.count),
              backgroundColor: "rgba(200,162,85,0.25)",
              borderColor: "#c8a255",
              borderWidth: 1.5,
              borderRadius: 2,
              hoverBackgroundColor: "rgba(200,162,85,0.45)",
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            tooltip: {
              backgroundColor: "#1a2038",
              titleColor: "#c8a255",
              bodyColor: "#8b98b8",
              borderColor: "rgba(200,162,85,0.3)",
              borderWidth: 1,
              titleFont: { family: "JetBrains Mono", size: 11 },
              bodyFont: { family: "JetBrains Mono", size: 11 },
              callbacks: {
                title: (items) => items[0].label,
                label: (item) => `${item.raw} queries`,
              },
            },
          },
          scales: {
            x: {
              grid: { color: "rgba(255,255,255,0.04)", drawBorder: false },
              ticks: {
                color: "rgba(139,152,184,0.5)",
                font: { family: "JetBrains Mono", size: 9 },
                maxRotation: 0,
                autoSkip: true,
                maxTicksLimit: 8,
              },
              border: { display: false },
            },
            y: {
              grid: { color: "rgba(255,255,255,0.04)", drawBorder: false },
              ticks: {
                color: "rgba(139,152,184,0.5)",
                font: { family: "JetBrains Mono", size: 9 },
                maxTicksLimit: 4,
                precision: 0,
              },
              border: { display: false },
            },
          },
        },
      });
    };
    document.head.appendChild(script);
    return () => {
      chartRef.current?.destroy();
    };
  }, [data]);

  if (!data || data.length === 0)
    return (
      <div
        style={{
          height: 120,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <span
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 11,
            color: "var(--text-dim)",
          }}
        >
          no data
        </span>
      </div>
    );

  return (
    <div style={{ position: "relative", width: "100%", height: 120 }}>
      <canvas ref={canvasRef} />
    </div>
  );
}

// ── Dashboard Page component ───────────────────────────────────────────────────
function DashboardPage() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const fetchStats = async () => {
    setLoading(true);
    setError(false);
    try {
      const res = await fetch(STATS_URL);
      if (!res.ok) throw new Error("fetch failed");
      const data = await res.json();
      setStats(data);
    } catch {
      setError(true);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchStats();
  }, []);

  const kpi = stats?.kpi || {};
  const daily = stats?.daily || [];
  const recent = stats?.recent || [];
  const sessions = (stats?.sessions || []).slice(0, 3);

  return (
    <div className="dashboard-page">
      <div className="dash-topbar">
        <div className="topbar-left">
          <div className={`status-dot ${loading ? "loading" : ""}`} />
          <div className="topbar-sep" />
          <span className="topbar-label">system dashboard</span>
        </div>
        <button className="refresh-btn" onClick={fetchStats} disabled={loading}>
          {loading ? "loading..." : "↺ refresh"}
        </button>
      </div>

      {loading && !stats && (
        <div className="dash-loading">
          <div className="dot" style={{ width: 6, height: 6 }} />
          <span className="dash-loading-label">fetching stats...</span>
        </div>
      )}

      {error && !loading && (
        <div className="dash-loading">
          <span className="dash-loading-label">failed to load — check API</span>
        </div>
      )}

      {stats && (
        <div className="dash-body">
          {/* KPI Cards */}
          <div className="kpi-grid">
            <div className="kpi-card">
              <div className="kpi-label">total queries</div>
              <div className="kpi-value">{kpi.total_queries ?? "—"}</div>
              <div className="kpi-sub">all time</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-label">avg latency</div>
              <div className="kpi-value">
                {kpi.avg_latency_ms != null
                  ? (kpi.avg_latency_ms / 1000).toFixed(1)
                  : "—"}
                <span
                  style={{
                    fontSize: 14,
                    color: "var(--text-dim)",
                    marginLeft: 4,
                  }}
                >
                  s
                </span>
              </div>
              <div className="kpi-sub">per query</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-label">cache hit rate</div>
              <div className="kpi-value kpi-accent">
                {kpi.cache_hit_pct != null ? kpi.cache_hit_pct : "—"}
                <span style={{ fontSize: 14, marginLeft: 2 }}>%</span>
              </div>
              <div className="kpi-sub">semantic cache</div>
            </div>
            <div className="kpi-card">
              <div className="kpi-label">positive feedback</div>
              <div className="kpi-value">
                {kpi.positive_feedback_pct != null
                  ? kpi.positive_feedback_pct
                  : "—"}
                <span
                  style={{
                    fontSize: 14,
                    color: "var(--text-dim)",
                    marginLeft: 2,
                  }}
                >
                  %
                </span>
              </div>
              <div className="kpi-sub">thumbs up / total</div>
            </div>
          </div>

          {/* Layout: grafico a sinistra, sessioni + recent a destra */}
          <div className="dash-main-grid">
            {/* Colonna sinistra: solo grafico */}
            <div className="dash-card">
              <div className="dash-card-label">queries · last 30 days</div>
              <div className="chart-wrap">
                <SparklineChart data={daily} />
              </div>
            </div>

            {/* Colonna destra: sessioni + recent queries impilate */}
            <div
              style={{ display: "flex", flexDirection: "column", gap: "16px" }}
            >
              <div className="dash-card">
                <div className="dash-card-label">top sessions</div>
                <div className="sessions-list">
                  {sessions.length === 0 && (
                    <span
                      style={{
                        fontFamily: "var(--font-mono)",
                        fontSize: 11,
                        color: "var(--text-dim)",
                      }}
                    >
                      no sessions
                    </span>
                  )}
                  {sessions.map((s, i) => (
                    <div key={i} className="session-row">
                      <div
                        style={{
                          display: "flex",
                          flexDirection: "column",
                          gap: 2,
                        }}
                      >
                        <span className="session-id">{s.session_id}...</span>
                        <span className="session-date">
                          {s.last_activity?.slice(0, 10)}
                        </span>
                      </div>
                      <span className="session-count">{s.query_count} q</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="dash-card">
                <div className="dash-card-label">recent queries</div>
                <div className="recent-table-wrap">
                  <table className="recent-table">
                    <thead>
                      <tr>
                        <th>query</th>
                        <th>answer</th>
                        <th>latency</th>
                        <th>cache</th>
                        <th>feedback</th>
                        <th>time</th>
                      </tr>
                    </thead>
                    <tbody>
                      {recent.length === 0 && (
                        <tr>
                          <td
                            colSpan={6}
                            style={{
                              textAlign: "center",
                              color: "var(--text-dim)",
                              fontFamily: "var(--font-mono)",
                              fontSize: 11,
                            }}
                          >
                            no queries yet
                          </td>
                        </tr>
                      )}
                      {recent.map((r, i) => (
                        <tr key={i}>
                          <td className="td-query" title={r.query}>
                            {r.query}
                          </td>
                          <td className="td-answer" title={r.answer}>
                            {r.answer}
                          </td>
                          <td
                            style={{
                              fontFamily: "var(--font-mono)",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {r.latency_ms != null
                              ? (r.latency_ms / 1000).toFixed(1) + "s"
                              : "—"}
                          </td>
                          <td>
                            <span
                              className={`badge ${r.cache_hit ? "badge-hit" : "badge-miss"}`}
                            >
                              {r.cache_hit ? "hit" : "miss"}
                            </span>
                          </td>
                          <td>
                            {r.feedback === true && (
                              <span className="badge badge-up">↑ up</span>
                            )}
                            {r.feedback === false && (
                              <span className="badge badge-down">↓ down</span>
                            )}
                            {r.feedback === null && (
                              <span className="badge badge-none">—</span>
                            )}
                          </td>
                          <td
                            style={{
                              fontFamily: "var(--font-mono)",
                              fontSize: 10,
                              whiteSpace: "nowrap",
                              color: "var(--text-dim)",
                            }}
                          >
                            {r.created_at?.slice(0, 16).replace("T", " ")}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default function App() {
  const [page, setPage] = useState("chat");

  return (
    <div className="app">
      <nav className="sidebar">
        <div className="sidebar-mark">Σ</div>
        <div className="sidebar-divider" />
        <button
          className={`nav-btn ${page === "chat" ? "active" : ""}`}
          onClick={() => setPage("chat")}
          title="Query"
        >
          <ChatIcon />
        </button>
        <button
          className={`nav-btn ${page === "dashboard" ? "active" : ""}`}
          onClick={() => setPage("dashboard")}
          title="Dashboard"
        >
          <DashboardIcon />
        </button>
      </nav>
      <main className="main">
        {page === "chat" ? <ChatPage /> : <DashboardPage />}
      </main>
    </div>
  );
}
