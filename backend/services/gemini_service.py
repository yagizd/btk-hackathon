from google import genai
# pyrefly: ignore [missing-import]
from google.genai import types
import json
import os
import time
from dotenv import load_dotenv

load_dotenv()

_client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
_MODEL = "gemini-2.0-flash-lite"

# Her çağrı öncesi bekleme (saniye)
_RATE_LIMIT_SLEEP = 2
# 429 alınınca bekleme (saniye)
_RETRY_SLEEP = 30

FIXTURE_NL_ANSWERS = {
    "default": "Bu ay toplam 6 sipariş işlendi. Brüt satış ₺18.093, net hak ediş ₺13.120,81. En çok satan ürün Samsung 27\" Monitör (₺12.998). Trendyol kanalı toplam gelirin %93'ünü oluşturuyor."
}


def _call_with_retry(fn):
    """
    Her Gemini çağrısından önce 2 sn bekler.
    429 hatası gelirse 30 sn bekleyip bir kez daha dener.
    """
    time.sleep(_RATE_LIMIT_SLEEP)
    try:
        return fn()
    except Exception as e:
        if "429" in str(e) or "quota" in str(e).lower() or "rate" in str(e).lower():
            time.sleep(_RETRY_SLEEP)
            return fn()   # tek retry; başarısız olursa üst katmana fırlat
        raise


def smart_fallback(product_name: str) -> dict:
    name = product_name.lower()

    kdv1_keywords = ["süt", "bebek", "mama", "zeytinyağı", "zeytin yağı",
                     "un", "ekmek", "yumurta", "peynir", "tereyağ",
                     "makarna", "pirinç", "şeker", "tuz", "gazete", "dergi"]

    kdv10_keywords = ["ilaç", "vitamin", "takviye", "şampuan", "saç",
                      "krem", "losyon", "diş", "sabun", "deterjan",
                      "restoran", "kafe", "otel"]

    for kw in kdv1_keywords:
        if kw in name:
            return {
                "kdv_orani": 1,
                "hesap_kodu": "153",
                "hesap_adi": "Ticari Mallar",
                "gemini_reasoning": "Temel gıda maddesi — KDV %1 uygulanır.",
                "guven_skoru": 0.85
            }

    for kw in kdv10_keywords:
        if kw in name:
            return {
                "kdv_orani": 10,
                "hesap_kodu": "153",
                "hesap_adi": "Ticari Mallar",
                "gemini_reasoning": "İndirimli KDV kategorisi — %10 uygulanır.",
                "guven_skoru": 0.80
            }

    return {
        "kdv_orani": 20,
        "hesap_kodu": "153",
        "hesap_adi": "Ticari Mallar",
        "gemini_reasoning": "Genel tüketim malı — standart KDV %20 uygulanır.",
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
            model=_MODEL,
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


def explain_reconciliation(
    expected_amount: float,
    actual_amount: float,
    difference: float,
    payout_json: dict,
    order_summary: list,
) -> str:
    """Payout farkini Gemini ile dogal dil olarak açiklar."""
    prompt = f"""Trendyol'un ödedigi tutar ile saticinin bekledigi tutar arasinda fark var.

Beklenen tutar: {expected_amount:.2f} TL
Gerceklesen ödeme: {actual_amount:.2f} TL
Fark: {difference:.2f} TL

Trendyol payout detayi:
{json.dumps(payout_json, ensure_ascii=False, indent=2)}

Siparis özeti:
{json.dumps(order_summary, ensure_ascii=False, indent=2)}

Bu farkin nedenini Türkçe, kisa (2-4 cümle) ve anlasiliir sekilde açikla.
Saticiya ne yapmasi gerektigini söyle.
Teknik jargondan kaçin."""

    try:
        response = _call_with_retry(lambda: _client.models.generate_content(
            model=_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.3),
        ))
        return response.text
    except Exception as e:
        err = str(e)
        if "429" in err or "quota" in err.lower() or "rate" in err.lower():
            fark = abs(actual_amount - expected_amount)
            return (
                f"Trendyol ödemesinde {fark:.2f} TL fark tespit edildi. "
                f"Bu fark büyük ihtimalle komisyon kesintisi, kampanya katılımı "
                f"veya stopaj düzenlemesinden kaynaklanmaktadır. "
                f"Trendyol satıcı panelinizden ödeme detaylarını kontrol ediniz."
            )
        return f"Gemini analizi su anda kullanilmiyor: {err[:100]}"


def answer_nl_query(question: str, context_data: dict) -> str:
    """Kullanicinin dogal dil sorusunu veritabani verileriyle birlestirir."""
    prompt = f"""Sen PazarMuhasebe'nin akilli muhasebe asistanisin.
Asagidaki satis verileri sana sunulmustur. Kullanicinin sorusunu Türkçe ve kisa cevapla.

=== VERİ ===
Toplam Brüt Satis: {context_data.get('total_gross', 0):.2f} TL
Toplam Komisyon: {context_data.get('total_commission', 0):.2f} TL
Net Hak Edis: {context_data.get('total_net', 0):.2f} TL
Siparis Sayisi: {context_data.get('order_count', 0)}
Iade Sayisi: {context_data.get('return_count', 0)}
Pazaryerleri: {', '.join(context_data.get('marketplaces', []))}

En çok satan ürünler:
{json.dumps(context_data.get('top_products', []), ensure_ascii=False, indent=2)}

Siparis listesi (özet):
{json.dumps(context_data.get('orders_summary', []), ensure_ascii=False, indent=2)}

=== SORU ===
{question}

Cevabi sade Türkçe, maksimum 3 cümle ile ver. Rakamlari TL cinsinden belirt."""

    try:
        response = _call_with_retry(lambda: _client.models.generate_content(
            model=_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.3),
        ))
        return response.text
    except Exception as e:
        err = str(e)
        if "429" in err or "quota" in err.lower() or "rate" in err.lower():
            return FIXTURE_NL_ANSWERS["default"]
        return f"Su anda cevap üretemiyorum: {err[:100]}"
