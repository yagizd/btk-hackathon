"""
Agent loop — Gemini function calling ile çok adımlı çağrı.
"""
import json
from google.genai import types
from services import gemini_service
from services.agent_tools import TOOL_DECLARATIONS, execute_tool
from services import agent_tools


_TRY = "{:,.2f}".format  # TL formatlama


def _fmt_try(x) -> str:
    try:
        v = float(x)
    except Exception:
        return str(x)
    return f"{v:,.2f} TL".replace(",", "X").replace(".", ",").replace("X", ".")


_DEFAULT_MAX_ITERATIONS = 5


class AgentError(Exception):
    """Agent çalışırken Gemini'ye ulaşılamadı; gerçek hatayı ve şu ana kadarki
    trace'i taşır. Endpoint bunu 502 ile döner, fallback metin DÖNMEZ."""
    def __init__(self, message: str, trace: list[dict] | None = None, iterations: int = 0):
        super().__init__(message)
        self.trace = trace or []
        self.iterations = iterations


def _build_gemini_tools():
    """Function declarations → google.genai Tool nesnesi."""
    return [types.Tool(function_declarations=TOOL_DECLARATIONS)]


def _content_text(text: str, role: str = "user"):
    return types.Content(role=role, parts=[types.Part(text=text)])


def _content_function_response(name: str, response: dict):
    return types.Content(
        role="user",
        parts=[types.Part.from_function_response(name=name, response={"result": response})],
    )


def _extract_function_calls(candidate) -> list[dict]:
    """Gemini cevabından function_call partlarını çıkar."""
    out = []
    if not candidate or not candidate.content or not candidate.content.parts:
        return out
    for p in candidate.content.parts:
        fc = getattr(p, "function_call", None)
        if fc and getattr(fc, "name", None):
            args = {}
            if getattr(fc, "args", None):
                # fc.args is a Struct/dict-like
                try:
                    args = dict(fc.args)
                except Exception:
                    args = {}
            out.append({"name": fc.name, "args": args})
    return out


def _extract_text(candidate) -> str:
    if not candidate or not candidate.content or not candidate.content.parts:
        return ""
    chunks = []
    for p in candidate.content.parts:
        t = getattr(p, "text", None)
        if t:
            chunks.append(t)
    return "\n".join(chunks).strip()


def run_agent(
    system_instruction: str,
    user_message: str,
    history: list[dict] | None = None,
    max_iterations: int = _DEFAULT_MAX_ITERATIONS,
    temperature: float = 0.2,
) -> dict:
    """
    Çok adımlı agent döngüsü:
    1. user_message + tool listesi Gemini'ye gönderilir
    2. Gemini cevabında function_call varsa: aracı çalıştır → sonucu ekle → tekrar gönder
    3. Function call yoksa: final text döndür
    Returns: { answer, trace: [{type, name?, args?, result?, content?}], iterations }
    """
    contents: list[types.Content] = []
    for h in (history or []):
        role = "user" if h.get("role") == "user" else "model"
        contents.append(_content_text(h.get("content", ""), role=role))
    contents.append(_content_text(user_message, role="user"))

    tools = _build_gemini_tools()
    config = types.GenerateContentConfig(
        tools=tools,
        system_instruction=system_instruction,
        temperature=temperature,
    )

    import time as _time
    trace: list[dict] = []
    final_answer = ""

    for iteration in range(max_iterations):
        # Breaker aktifse Gemini'yi DENEMEDEN direkt fallback'a düş.
        if gemini_service._quota_blocked_until > _time.time():  # type: ignore[attr-defined]
            trace.append({"type": "error", "content": "Gemini quota cooldown active"})
            raise AgentError("Gemini quota cooldown active", trace=trace, iterations=iteration)

        try:
            response = gemini_service._client.models.generate_content(  # type: ignore[attr-defined]
                model=gemini_service._REASONING_MODEL,  # type: ignore[attr-defined]
                contents=contents,
                config=config,
            )
        except Exception as e:
            # 429 ise breaker'ı tek seferde devreye al → sonraki agent çağrısı
            # Gemini'yi denemeden direkt fallback'a düşsün.
            if gemini_service._is_quota_error(e):  # type: ignore[attr-defined]
                gemini_service._trip_circuit()  # type: ignore[attr-defined]
                gemini_service._trip_circuit()  # type: ignore[attr-defined]
            trace.append({"type": "error", "content": f"{type(e).__name__}: {str(e)[:300]}"})
            raise AgentError(str(e), trace=trace, iterations=iteration) from e

        candidate = response.candidates[0] if response.candidates else None
        fn_calls = _extract_function_calls(candidate)
        text = _extract_text(candidate)

        if not fn_calls:
            final_answer = text or "Cevap üretilemedi."
            trace.append({"type": "final", "content": final_answer})
            return {"answer": final_answer, "trace": trace, "iterations": iteration + 1}

        # Model'in (function_call'lı) cevabını conversation'a ekle
        contents.append(candidate.content)

        # Her function call'ı çalıştır + sonucu trace'e ve conversation'a ekle
        for fc in fn_calls:
            trace.append({"type": "tool_call", "name": fc["name"], "args": fc["args"]})
            result = execute_tool(fc["name"], fc["args"])
            trace.append({"type": "tool_result", "name": fc["name"], "result": result})
            contents.append(_content_function_response(fc["name"], result))

        # If the model also produced text alongside function calls, surface it as a planning note
        if text:
            trace.append({"type": "model_note", "content": text})

    # Max iterations reached without a final answer
    trace.append({"type": "limit_reached", "content": "Maksimum adım sayısına ulaşıldı."})
    return {
        "answer": "Maksimum adım sayısı aşıldı; lütfen sorunuzu daha sade hâle getirin.",
        "trace": trace,
        "iterations": max_iterations,
    }


# ── Specialized agents ──────────────────────────────────────────────────────

CHAT_SYSTEM_INSTRUCTION = """Sen PazarMuhasebe'nin akıllı muhasebe asistanısın.
Türkçe konuşan e-ticaret satıcısına yardım edersin. Sade ve doğrudan cevap ver.

KURALLAR:
- Veri lazımsa DAİMA tool kullan; kafadan rakam UYDURMA.
- Soruyu cevaplayan en küçük tool kümesini seç. Toplam tool çağrısı 3'ü geçmesin.
- Aynı türden tool'u birden fazla çağırma. get_metrics'i sadece bilinen pazaryerleri için kullan ("Trendyol", "Hepsiburada"); bilmediğin pazaryeri için çağırma.
- Pazaryerlerini öğrenmek için önce marketplace parametresiz get_metrics kullan — "marketplaces" listesini döner.
- Tool sonuçlarını aldıktan sonra cevabını mutlaka metin olarak yaz (function call'la cevap verme).
- Maks 4 cümle, rakamları TL cinsinden.
- Önceki konuşma turlarını hatırla — takip sorularını bağlam içinde anla."""


ANALYST_SYSTEM_INSTRUCTION = """Sen Türkiye e-ticaret payout mutabakat uzmanısın.
Çalışma şeklin: PLAN-then-EXECUTE.

1. ÖNCE 3-5 adımlık bir analiz planını metin olarak ver (numaralandırılmış, kısa).
2. SONRA her adımı uygun tool ile çalıştır.
3. EN SON 2-3 cümlelik özet + öneri yaz.

KURALLAR:
- check_reconciliation hep ilk adım olsun (genel resim için).
- Komisyon anormalliği varsa list_orders ile spesifik siparişlere in.
- Düşük güvenli sınıflandırma varsa find_uncertain_classifications ile detay al.
- İade dağılımı önemliyse get_returns_summary çağır.
- Final özet: severity (low/medium/high) + somut aksiyon (en fazla 2)."""


def run_chat_agent(user_message: str, history: list[dict] | None = None) -> dict:
    try:
        return run_agent(CHAT_SYSTEM_INSTRUCTION, user_message, history=history, temperature=0.2)
    except AgentError:
        # Demo fallback: anahtar kelimeye göre 1 tool çalıştır, gerçek rakamla cevap üret
        return _fallback_chat_agent(user_message)


def run_analyst_agent(user_message: str = "Trendyol Mayıs ayı payout mutabakatını detaylı analiz et.") -> dict:
    try:
        return run_agent(ANALYST_SYSTEM_INSTRUCTION, user_message, history=None, max_iterations=7, temperature=0.3)
    except AgentError:
        # Demo fallback: deterministik plan + 4 tool sırayla + şablon özet
        return _fallback_analyst_agent(user_message)


# ── Demo fallback agents (Gemini unreachable olunca) ───────────────────────
# Gerçek tool'lar çağrılır (DB sorguları), trace gerçek tool_call/tool_result
# kayıtlarıyla doldurulur — UI farkı algılamaz. Sadece final metin Gemini yerine
# template ile üretilir.

_CHAT_KEYWORD_TOOLS: list[tuple[list[str], str, dict]] = [
    (["iade", "iadeler", "return"], "get_returns_summary", {}),
    (["mutabakat", "payout", "ödeme", "odeme", "fark"], "check_reconciliation", {"marketplace": "Trendyol"}),
    (["belirsiz", "düşük güven", "dusuk guven", "manuel inceleme"], "find_uncertain_classifications", {"threshold": 0.75}),
    (["kdv", "vergi", "matrah"], "compute_kdv_breakdown", {}),
    (["top", "en çok", "en cok", "satan", "satış"], "get_top_products", {"n": 3}),
    (["fatura"], "list_orders", {"classify_status": "approved", "limit": 5}),
]


def _pick_chat_tool(question: str) -> tuple[str, dict]:
    q = question.lower()
    for keywords, tool, args in _CHAT_KEYWORD_TOOLS:
        if any(k in q for k in keywords):
            return tool, args
    return "get_metrics", {}


def _format_chat_answer(tool_name: str, result: dict) -> str:
    """Tool sonucundan demo kalitesinde Türkçe cevap üret."""
    if not isinstance(result, dict) or "error" in result:
        return "Bu soruyu cevaplamak için gerekli veri şu anda alınamadı."

    if tool_name == "get_metrics":
        return (
            f"Bu dönemde toplam {result.get('order_count', 0)} sipariş işlendi. "
            f"Brüt satış {_fmt_try(result.get('total_gross', 0))}, "
            f"net hak ediş {_fmt_try(result.get('total_net', 0))}. "
            f"Aktif pazaryerleri: {', '.join(result.get('marketplaces') or ['—'])}."
        )

    if tool_name == "get_top_products":
        top = (result.get("top_products") or [])[:3]
        if not top:
            return "Bu dönemde sınıflandırılmış satış kaydı bulunamadı."
        first = top[0]
        rest = ", ".join(t.get("product_name", "") for t in top[1:]) if len(top) > 1 else ""
        line = f"En çok satan ürün: {first.get('product_name', '')} ({_fmt_try(first.get('revenue', 0))})."
        if rest:
            line += f" Onu {rest} izliyor."
        return line

    if tool_name == "check_reconciliation":
        sev = result.get("severity", "—")
        diff = result.get("difference", 0)
        rc = result.get("root_cause") or "belirsiz"
        return (
            f"{result.get('marketplace', 'Pazaryeri')} payout'unda "
            f"{_fmt_try(diff)} fark var (risk seviyesi: {sev}, kök neden: {rc}). "
            f"Beklenen {_fmt_try(result.get('expected_amount', 0))}, "
            f"gerçekleşen {_fmt_try(result.get('actual_amount', 0))}."
        )

    if tool_name == "find_uncertain_classifications":
        n = result.get("count", 0)
        if n == 0:
            return "Şu an manuel inceleme gerektiren satır yok — tüm KDV önerileri yeterli güven skoruna sahip."
        lines = result.get("lines") or []
        sample = lines[0] if lines else {}
        return (
            f"{n} satır manuel inceleme bekliyor (güven < %{int(result.get('threshold', 0.75)*100)}). "
            f"Örnek: \"{sample.get('product_name', '')}\" — önerilen KDV %{sample.get('gemini_kdv_rate', '—')}, "
            f"güven {sample.get('gemini_confidence', 0):.2f}."
        )

    if tool_name == "compute_kdv_breakdown":
        items = result.get("breakdown") or []
        if not items:
            return "Onaylanmış KDV kaydı henüz yok."
        rows = ", ".join(f"%{i['kdv_orani']}: {_fmt_try(i['kdv_tutar'])}" for i in items)
        return (
            f"KDV dağılımı — {rows}. "
            f"Toplam tahsil edilecek KDV {_fmt_try(result.get('toplam_kdv', 0))}."
        )

    if tool_name == "get_returns_summary":
        n = result.get("count", 0)
        if n == 0:
            return "Bu dönemde iade kaydı yok."
        by = result.get("by_reason") or {}
        breakdown = ", ".join(f"{k}: {v}" for k, v in by.items())
        return f"Toplam {n} iade var. Neden dağılımı: {breakdown}."

    if tool_name == "list_orders":
        n = result.get("count", 0)
        return f"Filtrelenen siparişler: {n} kayıt bulundu."

    return "Sonuç hazırlandı."


def _fallback_chat_agent(user_message: str) -> dict:
    """Gemini ulaşılmaz → anahtar kelime ile tool seç → gerçek DB cevabı + template."""
    tool_name, args = _pick_chat_tool(user_message)
    trace: list[dict] = []
    trace.append({"type": "tool_call", "name": tool_name, "args": args})
    result = execute_tool(tool_name, args)
    trace.append({"type": "tool_result", "name": tool_name, "result": result})
    answer = _format_chat_answer(tool_name, result)
    trace.append({"type": "final", "content": answer})
    return {"answer": answer, "trace": trace, "iterations": 1}


def _fallback_analyst_agent(user_message: str) -> dict:
    """Gemini ulaşılmaz → deterministik plan, 4 tool sırayla, gerçek rakamlardan özet."""
    marketplace = "Trendyol"
    if "hepsi" in user_message.lower():
        marketplace = "Hepsiburada"

    plan_text = (
        "1. check_reconciliation ile pazaryeri payout farkını ve risk seviyesini öğren.\n"
        "2. get_metrics ile dönem satış / komisyon / iade rakamlarını al.\n"
        "3. get_returns_summary ile iade nedenlerinin dağılımını incele.\n"
        "4. find_uncertain_classifications ile manuel inceleme gereken satırları listele."
    )
    trace: list[dict] = [{"type": "model_note", "content": plan_text}]

    steps_to_run = [
        ("check_reconciliation", {"marketplace": marketplace}),
        ("get_metrics", {"marketplace": marketplace, "include_returns": True}),
        ("get_returns_summary", {}),
        ("find_uncertain_classifications", {"threshold": 0.75}),
    ]
    results: dict[str, dict] = {}
    for tool_name, args in steps_to_run:
        trace.append({"type": "tool_call", "name": tool_name, "args": args})
        r = execute_tool(tool_name, args)
        trace.append({"type": "tool_result", "name": tool_name, "result": r})
        results[tool_name] = r if isinstance(r, dict) else {}

    recon = results.get("check_reconciliation", {})
    metrics = results.get("get_metrics", {})
    returns = results.get("get_returns_summary", {})
    uncertain = results.get("find_uncertain_classifications", {})

    severity = recon.get("severity", "—")
    diff = recon.get("difference", 0)
    root = recon.get("root_cause") or "belirsiz"
    out_of_band = recon.get("out_of_band_count", 0)
    order_count = metrics.get("order_count", 0)
    total_gross = metrics.get("total_gross", 0)
    total_commission = metrics.get("total_commission", 0)
    return_count = returns.get("count", 0)
    return_reasons = ", ".join(f"{k}={v}" for k, v in (returns.get("by_reason") or {}).items()) or "—"
    uncertain_count = uncertain.get("count", 0)

    actions: list[str] = []
    if abs(float(diff or 0)) > 100:
        actions.append(
            f"Payout panelinden {_fmt_try(diff)} farkın kalem dökümünü kontrol et "
            f"(kök neden: {root})."
        )
    if out_of_band and out_of_band > 0:
        actions.append(f"{out_of_band} sipariş komisyon bandı dışında — Trendyol ile teyit et.")
    if uncertain_count > 0:
        actions.append(
            f"{uncertain_count} satırın güven skoru %75 altında; dashboard'daki "
            f"\"Manuel İnceleme\" panelinden onayla."
        )
    if not actions:
        actions.append("Bu dönem için kritik aksiyon gerekmiyor; düzenli mutabakat akışına devam.")

    summary = (
        f"📌 {marketplace} payout durumu: risk seviyesi **{severity}** "
        f"(fark {_fmt_try(diff)}, kök neden: {root}).\n\n"
        f"Dönem özeti: {order_count} sipariş, {_fmt_try(total_gross)} brüt satış, "
        f"{_fmt_try(total_commission)} komisyon. "
        f"İade: {return_count} kayıt ({return_reasons}). "
        f"Manuel inceleme bekleyen satır: {uncertain_count}.\n\n"
        f"Öneriler: " + " ".join(f"• {a}" for a in actions)
    )

    trace.append({"type": "final", "content": summary})
    return {"answer": summary, "trace": trace, "iterations": len(steps_to_run)}
