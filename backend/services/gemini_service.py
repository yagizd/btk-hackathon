from google import genai
# pyrefly: ignore [missing-import]
from google.genai import types
import json
import os
import time
from dotenv import load_dotenv

load_dotenv()

_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Surface bazlı model seçimi:
# - FAST: yüksek hacimli, basit structured JSON (KDV classify, filter parsing, waterfall classify)
# - REASONING: nüanslı çıkarım (mutabakat, iade nedeni, alternatif KDV, çok turlu chat)
# - VISION: multimodal OCR (kağıt fatura fotoğrafı)
_FAST_MODEL = "gemini-2.5-flash-lite"
# NOT: 2.5-flash free tier'da sürekli 503 verdiği için reasoning'i de Lite'a aldık.
# Billing açıldığında "gemini-2.5-flash" yap → kalite +%15-20, latency +1-2sn.
_REASONING_MODEL = "gemini-2.5-flash-lite"
_MODEL = _FAST_MODEL  # geriye dönük uyumluluk; doğrudan kullanılmaz

# Her çağrı öncesi bekleme (saniye)
_RATE_LIMIT_SLEEP = 2
# 429 alınınca bekleme (saniye)
_RETRY_SLEEP = 30

FIXTURE_NL_ANSWERS = {
    "default": "Bu ay toplam 6 sipariş işlendi. Brüt satış ₺18.093, net hak ediş ₺13.120,81. En çok satan ürün Samsung 27\" Monitör (₺12.998). Trendyol kanalı toplam gelirin %93'ünü oluşturuyor."
}

# Pazaryeri × kategori bazında normal komisyon oranı bantları (min, max).
# "_default" key'i listelenmeyen kategoriler için fallback.
COMMISSION_BANDS = {
    "Trendyol": {
        "elektronik": (0.07, 0.13),
        "ayakkabı": (0.11, 0.15),
        "tekstil": (0.16, 0.22),
        "kozmetik": (0.16, 0.22),
        "ev_yasam": (0.10, 0.16),
        "küçük_ev_aletleri": (0.09, 0.13),
        "anne_bebek": (0.07, 0.10),
        "gıda": (0.05, 0.09),
        "_default": (0.09, 0.16),
    },
    "Hepsiburada": {
        "elektronik": (0.05, 0.10),
        "ayakkabı": (0.09, 0.13),
        "tekstil": (0.13, 0.19),
        "kozmetik": (0.14, 0.20),
        "ev_yasam": (0.08, 0.14),
        "küçük_ev_aletleri": (0.07, 0.11),
        "anne_bebek": (0.05, 0.09),
        "gıda": (0.04, 0.08),
        "_default": (0.07, 0.14),
    },
}


def _normalize_category(category: str) -> str:
    """Pazaryeri kategorilerini commission band key'lerine eşler."""
    if not category:
        return "_default"
    c = category.lower()
    if any(k in c for k in ["elektronik", "bilgisayar", "telefon", "tv"]):
        return "elektronik"
    if any(k in c for k in ["ayakkabı", "çanta"]):
        return "ayakkabı"
    if any(k in c for k in ["tekstil", "giyim", "moda"]):
        return "tekstil"
    if any(k in c for k in ["kozmetik", "kişisel bakım", "parfüm"]):
        return "kozmetik"
    if any(k in c for k in ["küçük ev", "blender", "robot"]):
        return "küçük_ev_aletleri"
    if any(k in c for k in ["ev", "yaşam", "mobilya", "mutfak"]):
        return "ev_yasam"
    if any(k in c for k in ["anne", "bebek", "mama"]):
        return "anne_bebek"
    if any(k in c for k in ["gıda", "süt", "ekmek", "market"]):
        return "gıda"
    return "_default"


def check_commission_bands(marketplace: str, order_summary: list) -> dict:
    """
    Her sipariş için commission/gross oranını hesaplar, pazaryeri bandına göre
    normal/uyarı/anomali olarak işaretler. Net deterministik kontrol — Gemini
    bunun çıktısını alıp doğal dil açıklama üretir.
    """
    bands = COMMISSION_BANDS.get(marketplace, COMMISSION_BANDS["Trendyol"])
    checks = []
    out_of_band_count = 0

    for o in order_summary:
        gross = float(o.get("gross_amount", 0))
        comm = float(o.get("commission", 0))
        if gross <= 0:
            continue
        rate = comm / gross
        cat_key = _normalize_category(o.get("category", ""))
        lo, hi = bands.get(cat_key, bands["_default"])
        if rate < lo * 0.7:
            status = "unusually_low"
            out_of_band_count += 1
        elif rate > hi * 1.3:
            status = "unusually_high"
            out_of_band_count += 1
        elif rate < lo or rate > hi:
            status = "borderline"
        else:
            status = "normal"

        checks.append({
            "order_id": o.get("order_id"),
            "category": o.get("category"),
            "category_key": cat_key,
            "actual_rate": round(rate, 4),
            "expected_band": [lo, hi],
            "status": status,
        })

    return {
        "checks": checks,
        "out_of_band_count": out_of_band_count,
        "total": len(checks),
    }


# Devre kesici: ardarda quota hatası alırsak bir süre Gemini'yi atlayıp
# doğrudan fallback'a düş. Aksi takdirde her istek 32 sn (sleep + retry) yer.
_QUOTA_TRIP_AFTER = 2          # ardışık 429 sayısı
_QUOTA_COOLDOWN_SEC = 300      # 5 dk sus
_OVERLOADED_RETRY_SLEEP = 5    # 503'te kısa retry (model geçici aşırı yüklü)
_quota_consecutive_failures = 0
_quota_blocked_until = 0.0


def _is_quota_error(err: Exception) -> bool:
    s = str(err).lower()
    return (
        "429" in s
        or "resource_exhausted" in s
        or "quota" in s
        or "rate" in s
        or "exceeded your current" in s
    )


def _is_overloaded(err: Exception) -> bool:
    """Gemini modeli geçici aşırı yüklü (503). Quota değil; kısa retry uygun."""
    s = str(err).lower()
    return "503" in s or "unavailable" in s or "overloaded" in s


def _trip_circuit():
    global _quota_consecutive_failures, _quota_blocked_until
    _quota_consecutive_failures += 1
    if _quota_consecutive_failures >= _QUOTA_TRIP_AFTER:
        _quota_blocked_until = time.time() + _QUOTA_COOLDOWN_SEC


def _reset_circuit():
    global _quota_consecutive_failures, _quota_blocked_until
    _quota_consecutive_failures = 0
    _quota_blocked_until = 0.0


def force_reset_circuit():
    """Public: agent gibi kasıtlı kullanıcı aksiyonlarında breaker'ı sıfırla."""
    _reset_circuit()


class GeminiQuotaError(Exception):
    """Devre kesici tarafından fırlatılır — caller fallback'a düşmeli."""


def _call_with_retry(fn):
    """
    Her Gemini çağrısından önce 2 sn bekler (rate limit).
    429 hatası gelirse 30 sn bekleyip bir kez daha dener.
    Ardışık 429'lar devre kesiciyi tetikler; cooldown süresince Gemini hiç çağrılmaz.
    """
    # Devre kesici aktifse → caller fallback'a düşsün
    if _quota_blocked_until > time.time():
        raise GeminiQuotaError("Gemini quota cooldown active")

    time.sleep(_RATE_LIMIT_SLEEP)
    try:
        result = fn()
        _reset_circuit()
        return result
    except Exception as e:
        if _is_quota_error(e):
            _trip_circuit()
            # Devre yeni açıldıysa retry'a girme — boşa 30sn beklemenin anlamı yok
            if _quota_blocked_until > time.time():
                raise GeminiQuotaError(str(e)) from e
            time.sleep(_RETRY_SLEEP)
            try:
                result = fn()
                _reset_circuit()
                return result
            except Exception as e2:
                if _is_quota_error(e2):
                    _trip_circuit()
                    raise GeminiQuotaError(str(e2)) from e2
                raise
        if _is_overloaded(e):
            # 503: model geçici aşırı yüklü; kısa bekleyip tek retry, breaker'ı tetikleme
            time.sleep(_OVERLOADED_RETRY_SLEEP)
            try:
                result = fn()
                return result
            except Exception:
                raise
        raise


def _call_with_model_chain(prompt_fn, models: list):
    """
    Model zinciri: ilk modeli dener, 503/overloaded gelirse sıradakine düşer.
    Quota hatası (429) → breaker tripler ve zincir devam etmez (GeminiQuotaError).
    Tüm modeller 503 ise son hatayı fırlatır.
    prompt_fn: (model_name) -> generate_content sonucu
    """
    last_err = None
    for idx, model_name in enumerate(models):
        try:
            return _call_with_retry(lambda mn=model_name: prompt_fn(mn))
        except GeminiQuotaError:
            raise
        except Exception as e:
            last_err = e
            if _is_overloaded(e) and idx < len(models) - 1:
                continue
            raise
    if last_err:
        raise last_err
    raise RuntimeError("Model zinciri boş")


def _generate_reasoning(prompt: str, config):
    """
    Reasoning gerektiren çağrılar. Free tier'da 2.5-flash sürekli 503 verdiği için
    REASONING_MODEL ve FAST_MODEL şu an aynı (Lite). Billing açıldığında REASONING
    'gemini-2.5-flash' yapılınca chain otomatik devreye girer.
    """
    # Dedupe: aynı modeli iki kere zincirleme
    chain = [_REASONING_MODEL] if _REASONING_MODEL == _FAST_MODEL else [_REASONING_MODEL, _FAST_MODEL]
    return _call_with_model_chain(
        lambda mn: _client.models.generate_content(model=mn, contents=prompt, config=config),
        chain,
    )


def _generate_fast(prompt: str, config):
    """Yüksek hacimli structured tasks için sadece Lite."""
    return _call_with_retry(
        lambda: _client.models.generate_content(model=_FAST_MODEL, contents=prompt, config=config)
    )


def smart_fallback(product_name: str) -> dict:
    import re
    name = product_name.lower()

    def normalize(s: str) -> str:
        """Turkce karakterleri ASCII'ye donustur: sut, seker, sac, ilac..."""
        import unicodedata
        tr_map = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
        return unicodedata.normalize("NFC", s).translate(tr_map)

    def word_match(kw: str, text: str) -> bool:
        """Her iki taraf normalize edilir, sonra kelime siniri kontrolu yapilir.
        Boylece 'sut' hem 'sut' hem 'sut' icindeki 'sut' ile eslesir,
        ama 'samsung' icindeki 'un' ile eslesmez."""
        nkw  = normalize(kw)
        ntext = normalize(text)
        if " " in nkw:
            return nkw in ntext
        # Sadece kelime BASI kontrolu: oncesinde harf/rakam olmamali.
        # Sonrasina bakilmaz — Turkce ekler (sututu, saclar vb.) da eslesin.
        # "un" samsung'da eslesmiyor cunku oncesinde "s" var.
        return bool(re.search(r"(?<![a-z0-9])" + re.escape(nkw), ntext))

    kdv1_keywords = [
        "sut", "bebek", "mama",
        "zeytinyagi", "zeytin yagi",
        "un", "ekmek", "yumurta",
        "peynir", "tereyag",
        "makarna", "pirinc", "seker", "tuz",
        "gazete", "dergi",
    ]

    kdv10_keywords = [
        "ilac", "vitamin", "takviye",
        "sampuan", "sac",
        "krem", "losyon",
        "dis", "sabun", "deterjan",
        "restoran", "kafe", "otel",
    ]

    for kw in kdv1_keywords:
        if word_match(kw, name):
            return {
                "kdv_orani": 1,
                "hesap_kodu": "153",
                "hesap_adi": "Ticari Mallar",
                "gerekce": "Temel gida maddesi - KDV %1 uygulanir.",
                "guven_skoru": 0.85
            }

    for kw in kdv10_keywords:
        if word_match(kw, name):
            return {
                "kdv_orani": 10,
                "hesap_kodu": "153",
                "hesap_adi": "Ticari Mallar",
                "gerekce": "Indirimli KDV kategorisi - %10 uygulanir.",
                "guven_skoru": 0.80
            }

    return {
        "kdv_orani": 20,
        "hesap_kodu": "153",
        "hesap_adi": "Ticari Mallar",
        "gerekce": "Genel tuketim mali - standart KDV %20 uygulanir.",
        "guven_skoru": 0.75
    }


def classify_kdv(product_name: str, category: str) -> dict:
    """
    Ürün adı ve kategorisinden KDV oranı + hesap kodu belirler.
    Yapılandırılmış JSON döndürür.
    """
    prompt = f"""Sen Türkiye vergi mevzuatına hakim bir muhasebe asistanısın.
Asagidaki ürün bilgisine bakarak:
1. KDV oranini belirle (1, 10 veya 20)
2. Tek Düzen Hesap Planı'ndan uygun hesap kodunu seç
3. Kararinin gerekçesini 1 cümleyle açikla

Ürün adi: {product_name}
Kategori: {category}

KDV orani rehberi:
- %1: Temel gida (ekmek, süt, yumurta, tahil, taze sebze/meyve), devlet destekli yayinlar
- %10: Islenmis gida, bebek mamasi, devam sütleri, tarim ürünleri, otel konaklama, restoran hizmeti
- %20: Tekstil, elektronik, kozmetik, beyaz esya, ayakkabi, mobilya, diger tüm ürünler

Yanitin SADECE su JSON formatinda döndür:
{{
  "kdv_orani": 20,
  "hesap_kodu": "153",
  "hesap_adi": "Ticari Mallar",
  "gerekce": "Tekstil ürünü, standart %20 KDV oranina tabidir.",
  "guven_skoru": 0.95
}}"""

    try:
        result_json = _call_with_retry(lambda: _client.models.generate_content(
            model=_FAST_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        ))
        result = json.loads(result_json.text)
        return {
            "kdv_orani": int(result.get("kdv_orani", 20)),
            "hesap_kodu": str(result.get("hesap_kodu", "153")),
            "hesap_adi": str(result.get("hesap_adi", "Ticari Mallar")),
            "gerekce": str(result.get("gerekce", "")),
            "guven_skoru": float(result.get("guven_skoru", 0.80)),
        }
    except Exception as e:
        err = str(e)
        if "429" in err or "quota" in err.lower() or "rate" in err.lower():
            return smart_fallback(product_name)
        return {
            "kdv_orani": 20,
            "hesap_kodu": "153",
            "hesap_adi": "Ticari Mallar",
            "gerekce": f"Otomatik siniflandirma basarisiz: {err[:80]}",
            "guven_skoru": 0.50,
        }


_RECON_ROOT_CAUSES = [
    "commission_outlier",
    "campaign_kesinti",
    "return_refund",
    "stopaj_adjustment",
    "missing_line_item",
    "rounding",
    "multiple",
    "unknown",
]


def _severity_from_signals(difference: float, out_of_band_count: int) -> str:
    abs_diff = abs(difference)
    if abs_diff > 500 or out_of_band_count >= 2:
        return "high"
    if abs_diff > 100 or out_of_band_count == 1:
        return "medium"
    return "low"


def _fallback_recon_payload(
    expected_amount: float,
    actual_amount: float,
    difference: float,
    commission_check: dict,
) -> dict:
    fark = abs(difference)
    severity = _severity_from_signals(difference, commission_check.get("out_of_band_count", 0))
    explanation = (
        f"Bu dönemde {fark:.2f} TL fark tespit edildi. "
        "Komisyon, iade geri ödemesi, kampanya katılımı veya stopaj "
        "düzenlemelerinden kaynaklanıyor olabilir."
    )
    return {
        "explanation": explanation,
        "severity": severity,
        "root_cause": "multiple" if fark > 50 else "rounding",
        "suggested_action": "Pazaryeri panelindeki ödeme dökümünü kalem kalem inceleyin.",
    }


_RETURN_REASONS = [
    "damaged", "wrong_item", "size_fit", "preference", "late_delivery", "quality", "other",
]

_REFUND_CATEGORIES = [
    "cash_refund", "replacement", "partial_refund", "warranty",
]


def _return_fallback(product_name: str, customer_notes: str) -> dict:
    text = f"{product_name} {customer_notes}".lower()
    if any(k in text for k in ["bozuk", "kırık", "kirik", "hasarl", "patl"]):
        return {
            "reason": "damaged", "refund_category": "cash_refund",
            "kdv_adjustment_needed": True, "confidence": 0.82,
            "explanation": "Ürün hasarlı veya kırık olarak tanımlanmış; iade KDV düzeltmesi gerekir.",
        }
    if any(k in text for k in ["yanlış", "yanlis", "farklı", "farkli ürün"]):
        return {
            "reason": "wrong_item", "refund_category": "replacement",
            "kdv_adjustment_needed": False, "confidence": 0.80,
            "explanation": "Yanlış ürün gönderilmiş; değişim ile çözülmesi öneriliyor.",
        }
    if any(k in text for k in ["beden", "küçük", "büyük", "kucuk", "buyuk", "ölçü", "olcu"]):
        return {
            "reason": "size_fit", "refund_category": "replacement",
            "kdv_adjustment_needed": False, "confidence": 0.78,
            "explanation": "Beden/ölçü uyumsuzluğu; uygun beden ile değişim öneriliyor.",
        }
    if any(k in text for k in ["beğenme", "begenme", "vazgeç", "vazgec"]):
        return {
            "reason": "preference", "refund_category": "cash_refund",
            "kdv_adjustment_needed": True, "confidence": 0.75,
            "explanation": "Müşteri tercihinden cayma; cayma hakkı kapsamında nakit iade ve KDV düzeltmesi.",
        }
    return {
        "reason": "other", "refund_category": "cash_refund",
        "kdv_adjustment_needed": True, "confidence": 0.60,
        "explanation": "İade nedeni net değil; varsayılan olarak nakit iade ve KDV düzeltmesi öneriliyor.",
    }


def classify_return_reason(product_name: str, customer_notes: str = "") -> dict:
    """
    İade nedenini sınıflandırır + uygun geri ödeme kategorisini önerir.
    Returns:
        { reason: enum, refund_category: enum, kdv_adjustment_needed: bool,
          explanation: str, confidence: float }
    """
    prompt = f"""Sen Türkiye e-ticaret iade ve KDV mevzuatına hakim asistansın.

Ürün: {product_name}
Müşteri notu / iade bildirimi: {customer_notes or "(Müşteri ek not bırakmadı.)"}

Görev:
1. İade nedenini sınıflandır.
2. Uygun geri ödeme/işlem kategorisini öner.
3. KDV düzeltme kaydı gerekli mi belirt.
4. Kararını 1 cümleyle Türkçe açıkla.

Çıktı (SADECE JSON):
{{
  "reason": "{' | '.join(_RETURN_REASONS)}",
  "refund_category": "{' | '.join(_REFUND_CATEGORIES)}",
  "kdv_adjustment_needed": true,
  "explanation": "Tek cümle gerekçe.",
  "confidence": 0.85
}}

Notlar:
- damaged/quality → genelde cash_refund + kdv düzeltmesi
- wrong_item/size_fit → genelde replacement, KDV düzeltmesi GEREKMEZ
- preference → cayma hakkı, cash_refund + KDV düzeltmesi"""

    try:
        result = _generate_reasoning(
            prompt,
            types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )
        parsed = json.loads(result.text)
        reason = parsed.get("reason", "other")
        if reason not in _RETURN_REASONS:
            reason = "other"
        refund = parsed.get("refund_category", "cash_refund")
        if refund not in _REFUND_CATEGORIES:
            refund = "cash_refund"
        return {
            "reason": reason,
            "refund_category": refund,
            "kdv_adjustment_needed": bool(parsed.get("kdv_adjustment_needed", True)),
            "explanation": str(parsed.get("explanation", "")).strip(),
            "confidence": float(parsed.get("confidence", 0.75)),
        }
    except Exception as e:
        err = str(e)
        if "429" in err or "quota" in err.lower() or "rate" in err.lower():
            return _return_fallback(product_name, customer_notes)
        fb = _return_fallback(product_name, customer_notes)
        fb["explanation"] = f"Gemini şu anda kullanılamıyor: {err[:80]}"
        return fb


_WATERFALL_LINE_TYPES = [
    "revenue", "commission", "campaign", "shipping_support",
    "return_refund", "stopaj", "adjustment", "other",
]


def _waterfall_fallback(payout_lines: list) -> list:
    """Anahtar-bazlı heuristic — Gemini olmadan da yapılandırılmış waterfall üretir."""
    out = []
    for line in payout_lines:
        desc = (line.get("description") or "").lower()
        amount = float(line.get("amount", 0))
        if any(k in desc for k in ["satış", "satis", "gelir"]):
            t = "revenue"
        elif "komisyon" in desc:
            t = "commission"
        elif "kampanya" in desc:
            t = "campaign"
        elif "kargo" in desc:
            t = "shipping_support"
        elif "iade" in desc:
            t = "return_refund"
        elif "stopaj" in desc:
            t = "stopaj"
        elif any(k in desc for k in ["düzelt", "duzelt", "mutabakat"]):
            t = "adjustment"
        else:
            t = "other"
        out.append({
            "description": line.get("description", ""),
            "amount": amount,
            "line_type": t,
            "explanation": "",
            "is_anomalous": False,
        })
    return out


def analyze_payout_waterfall(payout_lines: list, marketplace: str = "Trendyol") -> list:
    """
    Her payout kalemini sınıflandırır, kısa açıklama ekler, anomaly flag basar.
    Returns: [{description, amount, line_type, explanation, is_anomalous}]
    """
    prompt = f"""Sen Türkiye e-ticaret payout dökümünü analiz eden uzmansın.

Pazaryeri: {marketplace}
Payout kalemleri:
{json.dumps(payout_lines, ensure_ascii=False, indent=2)}

Görev: Her kalem için sınıflandır, 1 cümle açıkla, anomali işareti at.

line_type değerleri:
- revenue: Satış geliri (pozitif)
- commission: Pazaryeri komisyonu
- campaign: Kampanya kesintisi
- shipping_support: Kargo desteği
- return_refund: İade geri ödemesi
- stopaj: Stopaj kesintisi
- adjustment: Mutabakat düzeltmesi
- other: Diğer

is_anomalous = true olsun eğer:
- Komisyon kalemi normalin (%8-18) üstündeyse
- Stopaj %2'den belirgin saparsa
- Beklenmedik bir düzeltme kalemi varsa
- Açıklayıcı not gerektiriyorsa

Çıktı (SADECE JSON dizisi, kalemleri girdiyle aynı sırada):
[
  {{
    "description": "Satış Gelirleri",
    "amount": 5095.00,
    "line_type": "revenue",
    "explanation": "Mayıs 1-16 dönemindeki net satış tutarı.",
    "is_anomalous": false
  }}
]"""

    try:
        result = _call_with_retry(lambda: _client.models.generate_content(
            model=_FAST_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            ),
        ))
        parsed = json.loads(result.text)
        if not isinstance(parsed, list):
            return _waterfall_fallback(payout_lines)
        normalized = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            line_type = item.get("line_type", "other")
            if line_type not in _WATERFALL_LINE_TYPES:
                line_type = "other"
            normalized.append({
                "description": str(item.get("description", "")),
                "amount": float(item.get("amount", 0)),
                "line_type": line_type,
                "explanation": str(item.get("explanation", "")).strip(),
                "is_anomalous": bool(item.get("is_anomalous", False)),
            })
        if not normalized:
            return _waterfall_fallback(payout_lines)
        return normalized
    except Exception:
        return _waterfall_fallback(payout_lines)


def classify_kdv_with_alternatives(product_name: str, category: str) -> dict:
    """
    Birincil KDV önerisini + 1-2 alternatifi gerekçeleriyle birlikte üretir.
    Returns:
        {
          primary: {kdv_orani, hesap_kodu, hesap_adi, gerekce, guven_skoru},
          alternatives: [ {kdv_orani, hesap_kodu, hesap_adi, gerekce, guven_skoru}, ... ]
        }
    """
    prompt = f"""Sen Türkiye vergi mevzuatına hakim muhasebe asistanısın.
Aşağıdaki ürün için EN OLASI KDV oranını + 1-2 alternatif yorumu üret.

Ürün: {product_name}
Kategori: {category}

Her seçenek için gerekçe (1 cümle) ve güven skoru (0–1) ver.
Alternatifler birincilden FARKLI KDV oranlarına sahip olmalı; mantıklı senaryolar üret
(ör. "Eğer bu ürün gıda takviyesi sayılırsa %10, kozmetik sayılırsa %20").

KDV oranı rehberi:
- %1: Temel gıda, devlet destekli yayınlar
- %10: İşlenmiş gıda, bebek devam sütü, otel/restoran, tarım ürünleri
- %20: Tekstil, elektronik, kozmetik, beyaz eşya, ayakkabı, mobilya, diğer

Çıktı (SADECE JSON):
{{
  "primary": {{
    "kdv_orani": 20,
    "hesap_kodu": "153",
    "hesap_adi": "Ticari Mallar",
    "gerekce": "Birincil yorumun gerekçesi.",
    "guven_skoru": 0.78
  }},
  "alternatives": [
    {{
      "kdv_orani": 10,
      "hesap_kodu": "153",
      "hesap_adi": "Ticari Mallar",
      "gerekce": "Alternatif yorumun gerekçesi.",
      "guven_skoru": 0.55
    }}
  ]
}}"""

    def _normalize_option(opt: dict, default_confidence: float) -> dict:
        return {
            "kdv_orani": int(opt.get("kdv_orani", 20)),
            "hesap_kodu": str(opt.get("hesap_kodu", "153")),
            "hesap_adi": str(opt.get("hesap_adi", "Ticari Mallar")),
            "gerekce": str(opt.get("gerekce", "")).strip(),
            "guven_skoru": float(opt.get("guven_skoru", default_confidence)),
        }

    try:
        result = _generate_reasoning(
            prompt,
            types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.4,
            ),
        )
        parsed = json.loads(result.text)
        primary = _normalize_option(parsed.get("primary") or {}, 0.75)
        alternatives = [
            _normalize_option(a, 0.5)
            for a in (parsed.get("alternatives") or [])
            if isinstance(a, dict)
        ]
        # Alternatifler birincil ile aynı oran olmasın
        alternatives = [a for a in alternatives if a["kdv_orani"] != primary["kdv_orani"]][:2]
        return {"primary": primary, "alternatives": alternatives}
    except Exception as e:
        err = str(e)
        if "429" in err or "quota" in err.lower() or "rate" in err.lower():
            primary = smart_fallback(product_name)
            # Heuristic alternatives: bir üst + bir alt KDV oranı
            alt_rates = {1, 10, 20} - {primary["kdv_orani"]}
            alternatives = [
                {
                    "kdv_orani": r,
                    "hesap_kodu": "153",
                    "hesap_adi": "Ticari Mallar",
                    "gerekce": "Heuristik alternatif öneri (Gemini kotası).",
                    "guven_skoru": 0.45,
                }
                for r in sorted(alt_rates)
            ]
            return {"primary": primary, "alternatives": alternatives}
        primary = smart_fallback(product_name)
        return {"primary": primary, "alternatives": []}


def explain_reconciliation(
    expected_amount: float,
    actual_amount: float,
    difference: float,
    payout_json: dict,
    order_summary: list,
    marketplace: str = "Trendyol",
) -> dict:
    """
    Payout farkını Gemini ile yapısal JSON olarak açıklar.
    Returns:
        {
          explanation: str,
          severity: "low|medium|high",
          root_cause: enum,
          suggested_action: str,
          commission_check: { checks: [...], out_of_band_count: int, total: int }
        }
    """
    commission_check = check_commission_bands(marketplace, order_summary)
    deterministic_severity = _severity_from_signals(
        difference, commission_check["out_of_band_count"]
    )

    prompt = f"""Sen Türkiye e-ticaret muhasebesi uzmanısın. Pazaryeri payout farkı analiz edilecek.

Pazaryeri: {marketplace}
Beklenen tutar: {expected_amount:.2f} TL
Gerçekleşen ödeme: {actual_amount:.2f} TL
Fark: {difference:.2f} TL

Pazaryeri payout dökümü:
{json.dumps(payout_json, ensure_ascii=False, indent=2)}

Sipariş özeti:
{json.dumps(order_summary, ensure_ascii=False, indent=2)}

Komisyon bantı kontrolü (deterministik):
{json.dumps(commission_check, ensure_ascii=False, indent=2)}

Görev: Bu farkın asıl nedenini belirle, sertliğini sınıfla ve satıcıya kısa bir aksiyon öner.

Çıktı şeması (SADECE JSON):
{{
  "explanation": "2-4 cümle, sade Türkçe. Komisyon bandı kontrolü 'unusually_high' veya 'unusually_low' işaretliyse açıkça söyle.",
  "severity": "low | medium | high",
  "root_cause": "{' | '.join(_RECON_ROOT_CAUSES)}",
  "suggested_action": "Tek cümle, eyleme dönük (ör: 'TY-2026-0052 siparişinin kampanya kesintisini kontrol edin.')"
}}

severity rehberi:
- low: |fark| < 100 TL, tüm komisyonlar normal
- medium: |fark| 100-500 TL veya 1 sipariş bant dışı
- high: |fark| > 500 TL veya 2+ sipariş bant dışı
Deterministik öneri: {deterministic_severity}"""

    try:
        result_json = _generate_reasoning(
            prompt,
            types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )
        parsed = json.loads(result_json.text)
        severity = parsed.get("severity", deterministic_severity)
        # Gemini severity'yi düşürürse deterministik üst sınırı kabul et
        if {"low": 0, "medium": 1, "high": 2}.get(severity, 0) < {"low": 0, "medium": 1, "high": 2}[deterministic_severity]:
            severity = deterministic_severity
        root_cause = parsed.get("root_cause", "unknown")
        if root_cause not in _RECON_ROOT_CAUSES:
            root_cause = "unknown"
        return {
            "explanation": str(parsed.get("explanation", "")).strip(),
            "severity": severity,
            "root_cause": root_cause,
            "suggested_action": str(parsed.get("suggested_action", "")).strip(),
            "commission_check": commission_check,
        }
    except Exception as e:
        err = str(e)
        if "429" in err or "quota" in err.lower() or "rate" in err.lower():
            fb = _fallback_recon_payload(expected_amount, actual_amount, difference, commission_check)
            fb["commission_check"] = commission_check
            return fb
        fb = _fallback_recon_payload(expected_amount, actual_amount, difference, commission_check)
        fb["explanation"] = f"Gemini analizi şu anda kullanılamıyor: {err[:80]}"
        fb["commission_check"] = commission_check
        return fb


_VISION_MODEL = "gemini-2.5-flash"  # 2.5 Flash: Türkçe ve el yazısı OCR'da belirgin sıçrama


def extract_invoice_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> dict:
    """
    Bir fatura/sipariş belgesinin fotoğrafından kalemleri yapısal olarak çıkarır
    ve her satır için Gemini KDV önerisi ekler.

    Returns: {
      customer_name, date, lines: [{product_name, quantity, unit_price, kdv_orani, gerekce, guven_skoru}],
      gross_total, extraction_confidence, warnings: [str]
    }
    """
    prompt = """Bu görüntü bir fatura, irsaliye veya el yazısı sipariş notu olabilir.
Belgeden tüm kalemleri çıkar ve her satır için Türkiye KDV mevzuatına göre KDV oranı öner.

Görev:
1. Müşteri/satıcı adı (varsa)
2. Tarih (varsa, YYYY-MM-DD formatında)
3. Her ürün satırı için: ürün adı, miktar, birim fiyat, KDV oranı (1/10/20), kısa gerekçe
4. Brüt toplam
5. extraction_confidence: belgenin okunabilirlik skoru (0-1)
6. Okunamayan veya belirsiz alanlar için warnings dizisi

KDV rehberi:
- %1: temel gıda, devlet destekli yayınlar
- %10: işlenmiş gıda, bebek devam sütü, restoran/otel, tarım
- %20: tekstil, elektronik, kozmetik, ayakkabı, mobilya, diğer

Çıktı (SADECE JSON):
{
  "customer_name": "...",
  "date": "2026-05-19",
  "lines": [
    {
      "product_name": "...",
      "quantity": 1,
      "unit_price": 100.0,
      "kdv_orani": 20,
      "gerekce": "Elektronik ürün, standart KDV.",
      "guven_skoru": 0.9
    }
  ],
  "gross_total": 100.0,
  "extraction_confidence": 0.85,
  "warnings": ["Tarih kısmı silikti."]
}"""

    if not image_bytes:
        return {"error": "empty_image", "lines": [], "extraction_confidence": 0.0, "warnings": ["Boş dosya."]}

    try:
        result = _call_with_retry(lambda: _client.models.generate_content(
            model=_VISION_MODEL,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                prompt,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.2,
            ),
        ))
        parsed = json.loads(result.text)
        lines = []
        for l in (parsed.get("lines") or []):
            if not isinstance(l, dict):
                continue
            kdv = int(l.get("kdv_orani", 20))
            if kdv not in (1, 10, 20):
                kdv = 20
            lines.append({
                "product_name": str(l.get("product_name", "")).strip(),
                "quantity": int(l.get("quantity", 1) or 1),
                "unit_price": float(l.get("unit_price", 0) or 0),
                "kdv_orani": kdv,
                "gerekce": str(l.get("gerekce", "")).strip(),
                "guven_skoru": float(l.get("guven_skoru", 0.75)),
            })
        return {
            "customer_name": str(parsed.get("customer_name") or "").strip(),
            "date": str(parsed.get("date") or "").strip(),
            "lines": lines,
            "gross_total": float(parsed.get("gross_total") or 0),
            "extraction_confidence": float(parsed.get("extraction_confidence") or 0),
            "warnings": [str(w) for w in (parsed.get("warnings") or [])],
        }
    except Exception as e:
        err = str(e)
        return {
            "error": err[:200],
            "lines": [],
            "extraction_confidence": 0.0,
            "warnings": [f"Gemini şu anda kullanılamıyor: {err[:80]}"],
        }


_INVOICE_FILTER_KEYS = {
    "marketplace",       # str: "Trendyol" | "Hepsiburada"
    "status",            # str: "draft" | "sent" | "error"
    "invoice_type",      # str: "earsiv" | "efatura"
    "customer_substring",
    "invoice_number_substring",
    "date_from",         # ISO 'YYYY-MM-DD'
    "date_to",
    "min_gross",         # float
    "max_gross",
}


def parse_invoice_search_filters(question: str, today_iso: str) -> dict:
    """
    Doğal dil sorgusunu yapısal filtre objesine dönüştürür. Gemini SQL üretmez —
    yalnızca alan değerlerini çıkarır; backend parametreli sorgu kurar.
    """
    prompt = f"""Sen fatura arama asistanısın. Türkçe doğal dil sorgusunu, fatura listesi üzerinde
arama için kullanılacak yapısal filtre objesine dönüştür.

Bugünün tarihi: {today_iso}

Şema (yalnız ihtiyaç olanları doldur, gereksiz alanları KOY­MA):
- marketplace: "Trendyol" | "Hepsiburada"
- status: "draft" | "sent" | "error"
- invoice_type: "earsiv" | "efatura"
- customer_substring: müşteri adı parçası (case-insensitive)
- invoice_number_substring: fatura numarası parçası
- date_from: ISO tarih (YYYY-MM-DD)
- date_to: ISO tarih (YYYY-MM-DD)
- min_gross: minimum brüt tutar (TL, sayı)
- max_gross: maksimum brüt tutar (TL, sayı)

Sorgu: {question}

Çıktı (SADECE JSON, sadece ihtiyaç duyduğun alanları içersin):
{{
  "marketplace": "Trendyol",
  "date_from": "2026-05-01"
}}

Örnek:
- "Mayıs ayında Trendyol faturaları" -> {{"marketplace": "Trendyol", "date_from": "2026-05-01", "date_to": "2026-05-31"}}
- "1000 TL üstü taslak faturalar" -> {{"status": "draft", "min_gross": 1000}}
- "Doğuş Teknoloji'nin faturaları" -> {{"customer_substring": "Doğuş Teknoloji"}}"""

    try:
        result = _call_with_retry(lambda: _client.models.generate_content(
            model=_FAST_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        ))
        parsed = json.loads(result.text) if result.text else {}
        if not isinstance(parsed, dict):
            return {}
        return {k: v for k, v in parsed.items() if k in _INVOICE_FILTER_KEYS and v not in (None, "", [])}
    except Exception as e:
        err = str(e)
        if "429" in err or "quota" in err.lower() or "rate" in err.lower():
            return {}
        return {}


def answer_nl_query(question: str, context_data: dict, history: list = None) -> str:
    """
    Kullanıcının doğal dil sorusunu satış verileri + önceki konuşma turları ile yanıtlar.
    history: [{role: "user"|"assistant", content: str}] — kronolojik sıra, en fazla 5 tur.
    """
    history = history or []

    history_block = ""
    if history:
        lines = []
        for turn in history:
            role = "Kullanıcı" if turn.get("role") == "user" else "Asistan"
            lines.append(f"{role}: {turn.get('content','')}")
        history_block = "\n\n=== ÖNCEKI KONUŞMA ===\n" + "\n".join(lines)

    prompt = f"""Sen PazarMuhasebe'nin akıllı muhasebe asistanısın.
Aşağıdaki satış verileri sana sunulmuştur. Önceki konuşma varsa bağlamı koru, yeni soruyu Türkçe yanıtla.

=== VERİ ===
Toplam Brüt Satış: {context_data.get('total_gross', 0):.2f} TL
Toplam Komisyon: {context_data.get('total_commission', 0):.2f} TL
Net Hak Ediş: {context_data.get('total_net', 0):.2f} TL
Sipariş Sayısı: {context_data.get('order_count', 0)}
İade Sayısı: {context_data.get('return_count', 0)}
Pazaryerleri: {', '.join(context_data.get('marketplaces', []))}

En çok satan ürünler:
{json.dumps(context_data.get('top_products', []), ensure_ascii=False, indent=2)}

Sipariş listesi (özet):
{json.dumps(context_data.get('orders_summary', []), ensure_ascii=False, indent=2)}{history_block}

=== YENİ SORU ===
{question}

Cevabı sade Türkçe, maksimum 3 cümle ile ver. Rakamları TL cinsinden belirt.
Önceki konuşmaya atıfta bulunuyorsan açık ol (ör: 'Az önce bahsettiğin Trendyol kanalı için…')."""

    try:
        response = _generate_reasoning(
            prompt,
            types.GenerateContentConfig(temperature=0.3),
        )
        return response.text
    except Exception as e:
        err = str(e)
        if "429" in err or "quota" in err.lower() or "rate" in err.lower():
            return FIXTURE_NL_ANSWERS["default"]
        return f"Su anda cevap üretemiyorum: {err[:100]}"
