"use client";

import { useState } from "react";
import { nlQuery } from "@/src/lib/api";

export default function NLQueryBox() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim()) return;
    setLoading(true);
    setAnswer(null);
    setError(null);
    try {
      const data = await nlQuery(question.trim());
      setAnswer(data.answer);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="bg-white rounded-xl shadow-sm border border-gray-100 p-5">
      <h2 className="text-base font-semibold text-gray-700 mb-3">Doğal Dil Sorgusu</h2>
      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Örn: Bu ay en çok satan ürün hangisi?"
          className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-700 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:border-transparent"
          disabled={loading}
        />
        <button
          type="submit"
          disabled={loading || !question.trim()}
          className="px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
        >
          {loading ? (
            <>
              <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
              </svg>
              Sorgulanıyor
            </>
          ) : (
            "Sor"
          )}
        </button>
      </form>

      {error && (
        <div className="mt-3 text-red-500 bg-red-50 rounded-lg p-3 text-sm">
          Hata: {error}
        </div>
      )}

      {answer && (
        <div className="mt-3 bg-indigo-50 border border-indigo-100 rounded-lg p-4 text-sm text-gray-700 whitespace-pre-wrap">
          {answer}
        </div>
      )}
    </div>
  );
}
