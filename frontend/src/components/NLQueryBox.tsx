"use client";

import { useEffect, useRef, useState } from "react";
import { agentChat, resetChatSession, AgentTraceEntry, AgentUnreachableError } from "@/src/lib/api";

interface AssistantTurn {
  role: "assistant";
  content: string;
  trace: AgentTraceEntry[];
}
interface UserTurn {
  role: "user";
  content: string;
}
type ChatMessage = AssistantTurn | UserTurn;

const SAMPLE_QUESTIONS = [
  "Bu ay en çok satan ürünüm ne?",
  "Hangi siparişlerde manuel inceleme gerek?",
  "Trendyol payout farkı nereden geliyor?",
];

const TOOL_LABEL: Record<string, string> = {
  get_metrics:                   "📊 metrikler",
  list_orders:                   "📋 siparişler",
  get_top_products:              "🏆 top ürünler",
  check_reconciliation:          "💸 mutabakat",
  find_uncertain_classifications:"⚠️ belirsizler",
  get_invoice_by_number:         "📄 fatura",
  compute_kdv_breakdown:         "🧮 KDV dağılımı",
  get_returns_summary:           "↩️ iadeler",
};

function ToolChip({ name, args, result }: { name: string; args?: Record<string, unknown>; result?: unknown }) {
  const label = TOOL_LABEL[name] ?? `🛠 ${name}`;
  const hasArgs = args && Object.keys(args).length > 0;
  const argStr = hasArgs
    ? Object.entries(args!).map(([k, v]) => `${k}=${typeof v === "string" ? `"${v}"` : v}`).join(", ")
    : "";
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-indigo-50 border border-indigo-100 text-[10px] text-indigo-700 font-mono">
      <span>{label}</span>
      {argStr && <span className="text-indigo-500">({argStr})</span>}
      {result !== undefined && <span className="text-emerald-600">✓</span>}
    </span>
  );
}

function TraceStrip({ trace }: { trace: AgentTraceEntry[] }) {
  // Group tool_call + tool_result pairs by name for compact display
  const calls: { name: string; args?: Record<string, unknown>; hasResult: boolean }[] = [];
  for (const e of trace) {
    if (e.type === "tool_call") {
      calls.push({ name: e.name, args: e.args, hasResult: false });
    } else if (e.type === "tool_result") {
      const last = calls[calls.length - 1];
      if (last && last.name === e.name) last.hasResult = true;
    }
  }
  if (calls.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-1 mt-1">
      <span className="text-[10px] text-gray-400 mr-1">Gemini şu tool'ları çağırdı:</span>
      {calls.map((c, i) => (
        <ToolChip key={i} name={c.name} args={c.args} result={c.hasResult ? "ok" : undefined} />
      ))}
    </div>
  );
}

export default function NLQueryBox() {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ message: string; upstream?: string } | null>(null);
  const threadRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (threadRef.current) {
      threadRef.current.scrollTop = threadRef.current.scrollHeight;
    }
  }, [messages, loading]);

  async function ask(text: string) {
    const trimmed = text.trim();
    if (!trimmed) return;
    setLoading(true);
    setError(null);
    setMessages((prev) => [...prev, { role: "user", content: trimmed }]);
    setQuestion("");
    try {
      const data = await agentChat(trimmed, sessionId ?? undefined);
      setSessionId(data.session_id);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.answer, trace: data.trace },
      ]);
    } catch (e) {
      if (e instanceof AgentUnreachableError) {
        setError({ message: e.message, upstream: e.upstream });
      } else {
        setError({ message: (e as Error).message });
      }
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await ask(question);
  }

  async function handleReset() {
    if (sessionId) {
      try { await resetChatSession(sessionId); } catch { /* ignore */ }
    }
    setSessionId(null);
    setMessages([]);
    setError(null);
  }

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
      <div className="flex items-center justify-between mb-3">
        <div>
          <h2 className="text-base font-semibold text-gray-700 flex items-center gap-2">
            <span className="text-indigo-500">✦</span> Gemini Akıllı Asistan
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Tool kullanan agent — sadece ihtiyacı olan veriyi çekiyor, sonra cevap üretiyor.
          </p>
        </div>
        {messages.length > 0 && (
          <button
            onClick={handleReset}
            className="text-xs text-gray-500 hover:text-gray-700 underline underline-offset-2"
          >
            Yeni konuşma
          </button>
        )}
      </div>

      {messages.length === 0 ? (
        <div className="mb-3 grid sm:grid-cols-3 gap-2">
          {SAMPLE_QUESTIONS.map((q) => (
            <button
              key={q}
              onClick={() => ask(q)}
              className="text-left text-xs px-3 py-2 rounded-lg bg-gray-50 hover:bg-indigo-50 hover:text-indigo-700 text-gray-600 border border-gray-100 transition-colors"
            >
              {q}
            </button>
          ))}
        </div>
      ) : (
        <div ref={threadRef} className="mb-3 max-h-96 overflow-y-auto space-y-3 pr-1">
          {messages.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className="flex justify-end">
                <div className="max-w-[85%] bg-indigo-600 text-white text-sm rounded-2xl rounded-br-md px-4 py-2">
                  {m.content}
                </div>
              </div>
            ) : (
              <div key={i} className="flex justify-start">
                <div className="max-w-[88%] bg-indigo-50 border border-indigo-100 text-gray-700 text-sm rounded-2xl rounded-bl-md px-4 py-2">
                  <div className="whitespace-pre-wrap">{m.content}</div>
                  <TraceStrip trace={m.trace} />
                </div>
              </div>
            )
          )}
          {loading && (
            <div className="flex justify-start">
              <div className="bg-indigo-50 border border-indigo-100 rounded-2xl rounded-bl-md px-4 py-2 text-sm text-gray-500 flex items-center gap-2">
                <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                </svg>
                Gemini araçları kullanıyor…
              </div>
            </div>
          )}
        </div>
      )}

      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={messages.length === 0 ? "Bir soru yaz veya örneklerden birine tıkla…" : "Devam et…"}
          className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-700 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent"
          disabled={loading}
        />
        <button
          type="submit"
          disabled={loading || !question.trim()}
          className="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? "…" : "Gönder"}
        </button>
      </form>

      {error && (
        <div className="mt-3 bg-red-50 border border-red-100 rounded-lg p-3 text-sm">
          <div className="font-medium text-red-700">⚠ {error.message}</div>
          {error.upstream && (
            <pre className="mt-2 text-[11px] bg-white border border-red-100 rounded p-2 overflow-x-auto text-red-800 whitespace-pre-wrap break-words">
              {error.upstream}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
