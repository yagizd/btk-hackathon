# PazarMuhasebe — BTK Hackathon 2026

E-ticaret pazaryeri satıcıları için **Google Gemini destekli** ön muhasebe otomasyonu.
Trendyol ve Hepsiburada satışlarını çekiyor, KDV oranını Gemini'ye sınıflandırtıyor, payout farkını otomatik analiz ediyor, UBL-TR 1.2 uyumlu e-Arşiv/e-Fatura XML üretiyor ve **tool-using agent** ile doğal dil sorularını yanıtlıyor.

---

## Hızlı Başlangıç

### Backend
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# .env dosyasına GEMINI_API_KEY değerini girin
python -m uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

- Uygulama: http://localhost:3000
- API Docs (Swagger): http://localhost:8000/docs

---

## AI Özellikleri (12 surface)

Gemini sadece sınıflandırıcı değil — projenin reasoning motoru. Her özellik için bir fallback yolu var, Gemini'ye ulaşılamadığında (quota / 503) sistem kullanılamaz duruma düşmüyor.

### Klasik (single-shot) Gemini çağrıları
| # | Özellik | Endpoint |
|---|---|---|
| 1 | KDV sınıflandırma + hesap kodu + güven skoru | `POST /api/orders/{id}/classify` |
| 2 | KDV alternatifleri (primary + 1-2 ranked) | `POST /api/orders/classify-uncertain` |
| 3 | Mutabakat severity + root_cause + suggested_action | `GET /api/reconciliation/` |
| 4 | Komisyon bandı kontrolü (hybrid rules + LLM) | `GET /api/reconciliation/` |
| 5 | Payout waterfall (per-line type + anomaly flag) | `GET /api/reconciliation/` |
| 6 | İade nedeni sınıflandırma + KDV düzeltme | `POST /api/returns/classify-all` |
| 7 | NL → SQL fatura arama (filter extraction) | `POST /api/invoices/search` |
| 8 | Çok turlu sohbet (session memory) | `POST /api/nl-query` |
| 9 | Vision OCR — fatura fotoğrafından kalem çıkarma | `POST /api/orders/from-image` |
| 10 | Güven skoru kapısı (low-conf → onay zorunlu) | `POST /api/invoices/{id}/generate` |

### Agentic (tool-using, multi-step)
| # | Özellik | Endpoint | Davranış |
|---|---|---|---|
| 11 | **Akıllı asistan** — function calling ile araç seçen agent | `POST /api/agent/chat` | Gemini hangi tool'u çağıracağına kendi karar veriyor (8 tool); trace UI'da chip olarak görünüyor. |
| 12 | **Mutabakat uzmanı** — plan-then-execute agent | `POST /api/agent/reconciliation` | Önce 3-5 adımlık analiz planı yazıyor, sonra her adımı tool ile çalıştırıyor, sonunda özet + aksiyon. |

### Agent Tool Registry (8 fonksiyon)
`get_metrics` · `list_orders` · `get_top_products` · `check_reconciliation` · `find_uncertain_classifications` · `get_invoice_by_number` · `compute_kdv_breakdown` · `get_returns_summary`

Hepsi `backend/services/agent_tools.py` içinde. Gemini'ye function declaration olarak veriliyor; backend tool'u çalıştırıp sonucu Gemini'ye geri yolluyor. **LangGraph kullanılmadı** — Gemini'nin native function calling yeteneği yeterli.

---

## Frontend Sayfaları

| Route | İçerik |
|---|---|
| `/` | Dashboard — metrikler, satış grafiği, siparişler, **agent chat (tool chip'leri ile)**, manuel inceleme paneli |
| `/faturalar` | Fatura listesi + **NL search bar** ("Mayıs Trendyol faturaları") |
| `/iadeler` | İade siparişleri + Gemini neden sınıflandırması |
| `/mutabakat` | Severity banner + komisyon bant tablosu + waterfall chart + **plan-then-execute analyst paneli** |
| `/yukle` | **Vision OCR** — kağıt fatura fotoğrafı yükle, kalemler + KDV öneriler çıksın |

---

## Teknoloji

| Katman | Seçim | Not |
|---|---|---|
| Backend | Python 3.11 + **FastAPI** | Sync sync route'lar, multipart upload, structured output |
| Veritabanı | **SQLite** | Fixture data, demo için yeterli; production'da PostgreSQL'e geçilebilir |
| AI | **Gemini 2.5 Flash-Lite** (reasoning + fast) | `google-genai` SDK (yeni); function calling, structured JSON output |
| AI (Vision) | **Gemini 2.5 Flash** | Multimodal OCR (Türkçe karakter + el yazısı) |
| Frontend | **Next.js 16 + React 19 + TypeScript + Tailwind 4 + Recharts** | App Router |

### Gemini model seçim haritası
- `_FAST_MODEL = "gemini-2.5-flash-lite"` — yüksek hacimli structured çağrılar (KDV classify, filter parsing, waterfall classify)
- `_REASONING_MODEL = "gemini-2.5-flash-lite"` — agentic ve nüanslı tasks (free tier'da 2.5-flash 503 sorunu nedeniyle Lite'a alındı; billing açıldığında `gemini-2.5-flash`'a geri çevrilebilir)
- `_VISION_MODEL = "gemini-2.5-flash"` — multimodal OCR

---

## Mimari

```
   Trendyol / Hepsiburada (fixture)
            │
            ▼
   ┌───────────────────────┐
   │  FastAPI Normalizer   │  → SQLite (orders, lines, invoices, returns,
   └───────────────────────┘                 chat_sessions, return_classifications)
            │
   ┌────────┴────────┬──────────────────┬───────────────────┐
   ▼                 ▼                  ▼                   ▼
 KDV Classifier   Reconciliation    Returns Agent      Agent Loop (chat + analyst)
 (Gemini JSON)    (severity + WF)   (reason + KDV)     │
                                                       ▼ function_calling
                                              ┌─────────────────────┐
                                              │  8-tool registry    │
                                              │  → DB queries       │
                                              └─────────────────────┘
            │
            ▼
   ┌─────────────────┐
   │  UBL-TR 1.2 XML │  → e-Arşiv / e-Fatura ayrımı (GİB mükellef listesine göre)
   └─────────────────┘
            │
            ▼
   ┌───────────────────────────────┐
   │  Next.js 16 Dashboard         │
   │  • Akıllı chat (tool chip UI) │
   │  • Plan-then-execute analyst  │
   │  • Vision OCR upload          │
   │  • Waterfall + severity       │
   └───────────────────────────────┘
```

---

## Dayanıklılık (Resilience)

Her Gemini çağrısının deterministik bir yedeği var — anahtar yok / quota dolu / 503 olsa bile uygulama çalışır:

| Gemini çağrısı | Fallback |
|---|---|
| `classify_kdv` | Türkçe anahtar kelime eşlemesi (`smart_fallback`) — gıda/ilaç/tekstil kategorileri |
| `explain_reconciliation` | Severity'yi `abs(difference)` ve `out_of_band_count`'tan deterministik üret |
| `analyze_payout_waterfall` | Anahtar kelime sınıflandırması ("komisyon"→commission, "iade"→return_refund, ...) |
| `classify_return_reason` | Türkçe keyword (`bozuk`→damaged, `beden`→size_fit, ...) |
| `answer_nl_query` (agent) | **Demo-kalite fallback agent** — anahtar kelime → tool seçimi → gerçek DB sonucu + Türkçe şablon cevap |
| `agent_reconciliation` | **Plan-then-execute fallback** — sabit 4-adım plan + gerçek tool çağrıları + şablon özet |

### Quota Circuit Breaker
`backend/services/gemini_service.py` içindeki `_call_with_retry` quota hataları için **devre kesici**:
- 2 ardışık 429 → 5 dakika boyunca Gemini hiç çağrılmıyor
- 503 (overloaded) → kısa retry, breaker'ı tetiklemiyor
- Agent path: breaker aktifse SDK'nın 30 saniyelik internal backoff'una girmiyor — direkt fallback (sub-saniye yanıt)

---

## Önemli Endpoint'ler

```
GET    /api/dashboard/metrics          → top-line özet
GET    /api/dashboard/chart            → son 7 gün gross/net
GET    /api/orders/                    → tüm siparişler + lines
POST   /api/orders/{id}/classify       → tek sipariş KDV (Gemini)
POST   /api/orders/classify-all        → tüm bekleyenler için KDV
POST   /api/orders/classify-uncertain  → düşük güvenli satırlara alternatif öneriler
POST   /api/orders/lines/{id}/apply-kdv → seçilen KDV'yi uygula + onayla
POST   /api/orders/from-image          → multipart upload, vision OCR
POST   /api/orders/save-extracted      → OCR sonucunu sipariş olarak kaydet
POST   /api/orders/{id}/approve        → onay (confidence-gated)
GET    /api/invoices/                  → fatura listesi
POST   /api/invoices/{order_id}/generate → UBL-TR XML üret
POST   /api/invoices/search            → NL → filter → SQL arama
GET    /api/invoices/{id}/xml          → XML indir
GET    /api/reconciliation/            → severity + waterfall + commission_check
GET    /api/returns/                   → iadeler + sınıflandırma
POST   /api/returns/classify-all       → iadeleri Gemini ile sınıflandır
POST   /api/nl-query                   → tek-turlu (legacy) NL sorgu
POST   /api/agent/chat                 → tool-using akıllı asistan (önerilen)
POST   /api/agent/reconciliation       → plan-then-execute mutabakat uzmanı
```

---

## Veritabanı Şeması

```
orders                          (siparişler — pazaryeri, müşteri, tutarlar, status)
  ↓
order_lines                     (ürün satırları + Gemini KDV önerisi + alternatifler)
  ↓
invoices                        (UBL-TR XML, draft/sent/error)

return_classifications          (Gemini neden + refund_category + KDV adjustment flag)
chat_sessions                   (multi-turn agent session memory, son 5 tur)
settings                        (key-value store, gelecek için rezerv)
```

`backend/services/xml_service.py` UBL-TR 1.2 şemasına göre imzasız XML üretir (hackathon kapsamında imzalama yok — production'da KamuSM/NES entegrasyonu eklenecek).

---

## BTK Hackathon 2026

Bu proje **BTK Akademi × Google × GİRVAK Hackathon 2026** için geliştirilmiştir.

**Gemini API zorunlu kullanım kriterini karşılayan özellikler:**
- Yüksek hacimli structured classification (KDV, return reason, waterfall)
- Multi-hypothesis reasoning (alternatif KDV önerileri)
- Multi-step agentic workflows (chat + analyst, native function calling)
- Multimodal OCR (kağıt fatura → yapısal sipariş)
- Çok turlu konuşma + session memory

**Geliştirici notu:** Free tier limitleri (günde 20-50 istek) demo sırasında dolabilir; bu durumda fallback yolları devreye girer ve UI yine gerçek DB rakamlarıyla çalışır. Billing açıldığında otomatik olarak Gemini'ye dönülür.

---

## Yol Haritası (Hackathon sonrası)

- Trendyol / Hepsiburada canlı API entegrasyonu (stage credentials sonrası)
- GİB özel entegratör anlaşması (NES veya QNB eFinans)
- Gerçek mali mühür (KamuSM) imzalama
- PostgreSQL'e geçiş + Redis caching
- e-Defter modülü (2026 Ocak zorunluluğu)
- Embeddings-based ürün dedup'ı
- Feedback loop / active learning (kullanıcı düzeltmelerini few-shot olarak prompt'a katma)
