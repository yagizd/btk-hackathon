"use client";

import { useEffect, useRef, useState } from "react";
import { nlQuery, resetChatSession } from "@/src/lib/api";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

const SAMPLE_QUESTIONS = [
  "Bu ay en çok satan ürün hangisi?",
  "Trendyol kanalında brüt satışım ne kadar?",
  "Hangi siparişlerde komisyon oranı anormal yüksek?",
];

export default function NLQueryBox() {
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
      const data = await nlQuery(trimmed, sessionId ?? undefined);
      setSessionId(data.session_id);
      setMessages((prev) => [...prev, { role: "assistant", content: data.answer }]);
    } catch (e) {
      setError((e as Error).message);
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
            <span className="text-indigo-500">✦</span> Gemini Sohbet
          </h2>
          <p className="text-xs text-gray-500 mt-0.5">
            Soruları takip ederek bağlamı koruyor — örn: "Top ürünüm?" → "Peki Trendyol'da?"
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
        <div
          ref={threadRef}
          className="mb-3 max-h-80 overflow-y-auto space-y-2 pr-1"
        >
          {messages.map((m, i) => (
            <div
              key={i}
              className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
            >
              <div
                className={`max-w-[85%] rounded-2xl px-4 py-2 text-sm whitespace-pre-wrap ${
                  m.role === "user"
                    ? "bg-indigo-600 text-white rounded-br-md"
                    : "bg-indigo-50 text-gray-700 rounded-bl-md border border-indigo-100"
                }`}
              >
                {m.content}
              </div>
            </div>
          ))}
          {loading && (
            <div className="flex justify-start">
              <div className="bg-indigo-50 border border-indigo-100 rounded-2xl rounded-bl-md px-4 py-2 text-sm text-gray-500 flex items-center gap-2">
                <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                </svg>
                Düşünüyor…
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
        <div className="mt-3 text-red-500 bg-red-50 rounded-lg p-3 text-sm">
          Hata: {error}
        </div>
      )}
    </div>
  );
}
