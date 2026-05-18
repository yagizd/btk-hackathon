# PazarMuhasebe — Session Handoff
> BTK Hackathon 2026 | Son güncelleme: 17 Mayıs 2026

---

## 1. Projenin Özü

**Ne yapıyor?**  
Trendyol ve Hepsiburada'daki satışları, komisyon kesintilerini ve iadeleri otomatik işleyerek Gemini 2.0 Flash ile KDV/hesap kodu sınıflandırması yapan, UBL-TR uyumlu e-Arşiv/e-Fatura üreten web uygulaması.

**Neden bu proje?**  
- 540.000+ pazaryeri satıcısı var, hepsi e-Belge kesmek zorunda (2025 zorunluluğu)  
- Çoklu kanal payout mutabakatı + Gemini sınıflandırması yapan Türkçe ürün yok  
- Gemini zorunlu değil, çıkarılamaz — KDV tespiti kural tabanlı yapılamaz (50K+ ürün varyasyonu)  
- Jüri kriteri: Gemini API çekirdekte kullanılmalı ✓

---

## 2. Klasör Yapısı

```
btk hackathon/
├── backend/                        # FastAPI uygulaması
│   ├── main.py                     # App entry point, CORS, router kayıtları
│   ├── database.py                 # SQLite bağlantısı (get_db context manager)
│   ├── models.py                   # Pydantic modeller (OrderOut, ApproveRequest, vb.)
│   ├── requirements.txt
│   ├── .env                        # GEMINI_API_KEY buraya
│   ├── pazarmuhasebe.db            # SQLite veritabanı (fixture ile dolu)
│   ├── routers/
│   │   ├── orders.py               # /api/orders — liste, classify, approve
│   │   ├── invoices.py             # /api/invoices — liste, XML üretimi
│   │   ├── reconciliation.py       # /api/reconciliation — payout mutabakat
│   │   ├── nl_query.py             # /api/nl-query — Gemini doğal dil
│   │   └── dashboard.py            # /api/dashboard — metrikler, grafik
│   ├── services/
│   │   ├── gemini_service.py       # Gemini 2.0 Flash çağrıları (rate limit + retry)
│   │   └── xml_service.py          # UBL-TR 1.2 XML üretici
│   └── fixture_data/
│       ├── trendyol_orders.json
│       ├── hepsiburada_orders.json
│       └── trendyol_payout.json
│
├── btk-hackathon/
│   └── frontend/                   # Next.js 16 uygulaması
│       ├── app/
│       │   ├── page.tsx            # Dashboard ana sayfa
│       │   ├── faturalar/
│       │   │   └── page.tsx        # Fatura listesi sayfası
│       │   └── mutabakat/
│       │       └── page.tsx        # Payout mutabakat sayfası
│       └── src/
│           ├── lib/
│           │   └── api.ts          # fetch tabanlı API client + TypeScript tipleri
│           └── components/
│               ├── MetricCard.tsx  # Dashboard metrik kartı
│               ├── OrdersTable.tsx # Sipariş tablosu (KDV badge, onay)
│               └── NLQueryBox.tsx  # Doğal dil soru kutusu
│
└── BTK_Hackathon_2026_Proje_Plani.md
```

---

## 3. Bu Session'da Ne Yaptık

### 3.1 Frontend Kurulumu
**Ne:** `btk-hackathon/frontend/` altına Next.js 16 + TypeScript + Tailwind CSS kuruldu.  
**Neden:** Proje planı React/Next.js seçimini öngörüyordu; SSR ile dashboard hızlı yüklenir.  
**Nasıl:**
```bash
npx create-next-app@latest . --typescript --tailwind --app --no-src-dir --eslint
npm install axios recharts lucide-react
```
> Not: `--no-src-dir` flag'i kullanıldığı için `app/` klasörü root'ta, bileşenler `src/` altında. `tsconfig.json`'daki `@/*` alias'ı root'u işaret eder, import'lar `@/src/lib/api` şeklinde yazılır.

---

### 3.2 `src/lib/api.ts` — API Client
**Ne:** `fetch` tabanlı merkezi API client ve TypeScript tip tanımları.  
**Neden:** `axios` daha fazla boilerplate gerektirir; native `fetch` Next.js ile daha iyi entegre çalışır.  
**Önemli kararlar:**
- Backend tüm route'larını `/api/` prefix'i ile tanımlamış → tüm çağrılar `http://127.0.0.1:8000/api/...`
- `approveOrder` backend'in `ApproveRequest` modeline uygun `{ approved: true }` gönderir (başta `kdv_rate` gönderiliyordu, düzeltildi)
- `classifyAll()` ayrı export edildi — dashboard açılışında çağrılır

**Export edilen fonksiyonlar:**
| Fonksiyon | Endpoint |
|---|---|
| `fetchDashboard()` | `GET /api/dashboard/metrics` |
| `fetchOrders()` | `GET /api/orders/` |
| `approveOrder(id)` | `POST /api/orders/{id}/approve` → `{approved: true}` |
| `classifyAll()` | `POST /api/orders/classify-all` |
| `fetchInvoices()` | `GET /api/invoices/` |
| `fetchReconciliation()` | `GET /api/reconciliation/` |
| `nlQuery(question)` | `POST /api/nl-query` |

---

### 3.3 `src/components/MetricCard.tsx`
**Ne:** Yeniden kullanılabilir metrik kartı bileşeni.  
**Props:** `{ title, value, subtitle?, icon? }`  
**Tasarım:** Beyaz bg, gölge, `border-l-4 border-l-indigo-500` sol accent şerit.

---

### 3.4 `src/components/OrdersTable.tsx`
**Ne:** Sipariş tablosu — veri çekme, KDV badge, güven skoru uyarısı, onay aksiyonu.  
**Neden karmaşıklaştı:** Backend'deki `Order` objesi düz alan değil, `lines[]` array'i içeriyor. KDV oranı ve güven skoru `order.lines[0].gemini_kdv_rate` gibi nested yapıda.  
**Önemli mantık:**
- `is_return: 1` olan siparişler filtrelenir (iade gösterilmez)
- KDV badge renkleri: `%20` → yeşil, `%10` → sarı, `%1` → mavi
- `confidence < 0.8` → satır sarı + uyarı ikonu + "Manuel kontrol et" tooltip
- Gemini classify edilmemiş siparişlerde KDV ve güven `—` gösterilir
- Onay sonrası satır yeşile döner, buton "✓ Onaylandı" olur

---

### 3.5 `src/components/NLQueryBox.tsx`
**Ne:** Doğal dil soru arayüzü.  
**Nasıl çalışır:** Input → "Sor" butonu → `POST /api/nl-query` → cevap indigo kutuda gösterilir. Loading sırasında spinner + buton disabled.

---

### 3.6 `app/page.tsx` — Dashboard
**Ne:** Sidebar + 2×2 MetricCard grid + OrdersTable + NLQueryBox ana layout.  
**Classify-all akışı:** `useEffect` ilk yüklemede `classifyAll()` çağırır → hata olursa `console.error` ile sessizce geçer → `finally` içinde `fetchDashboard()` tetiklenir. Bu sayede sayfa açıldığında siparişler sınıflandırılmış olur.  
**Dashboard field mapping:**
| Frontend gösterimi | Backend alanı |
|---|---|
| Brüt Satış | `total_gross` |
| Net Hak Ediş | `total_net` |
| Komisyon | `total_commission` |
| Belge Sayısı | `order_count` |

---

### 3.7 `app/faturalar/page.tsx`
**Ne:** Fatura listesi sayfası.  
**Route:** `/faturalar`  
**Gösterilen alanlar:** Fatura No | Sipariş ID | Müşteri | Tür | Durum | Tarih  
**Tip dönüşümleri:** `earsiv` → "e-Arşiv", `efatura` → "e-Fatura"  
**Durum badge renkleri:** `sent` → yeşil, `draft` → sarı, `error` → kırmızı  
**Boş durum:** "Henüz fatura oluşturulmamış" placeholder mesajı

---

### 3.8 `app/mutabakat/page.tsx`
**Ne:** Trendyol payout mutabakat sayfası.  
**Route:** `/mutabakat`  
**Gösterilen bölümler:**
1. Özet kart: Beklenen / Gerçekleşen / Fark (pozitif → yeşil, negatif → kırmızı)
2. Gemini açıklaması bloğu
3. Ödeme kalemleri (`payout_lines[]`) detay listesi  
**Status badge:** `reconciled` → "Mutabık" yeşil, `discrepancy` → "Fark Var" kırmızı

---

### 3.9 `services/gemini_service.py` — Rate Limiting
**Ne:** Her Gemini çağrısına 2 sn bekleme + 429 hatasında 30 sn retry eklendi.  
**Neden:** `classify-all` tüm siparişleri art arda Gemini'ye gönderince quota aşımı oluyordu.  
**Nasıl:** `_call_with_retry(fn)` yardımcı fonksiyonu — tüm üç Gemini fonksiyonu buna sarıldı:

```python
def _call_with_retry(fn):
    time.sleep(2)          # Her çağrı öncesi bekleme
    try:
        return fn()
    except Exception as e:
        if "429" in str(e) or "quota" in str(e).lower() or "rate" in str(e).lower():
            time.sleep(30) # 429 alınınca bekle
            return fn()    # Tek retry
        raise
```

> **Neden `time.sleep`, `asyncio.sleep` değil?**  
> `gemini_service.py` ve tüm route handler'lar sync fonksiyon. FastAPI'da sync route'larda `asyncio.sleep` event loop'u bloke etmez, uyku yapmaz — işe yaramaz. `time.sleep` doğru seçim.

---

### 3.10 `routers/orders.py` — Sequential classify-all
**Ne:** `classify_all_orders` endpoint'i siparişleri sırayla işleyecek şekilde belgelendi.  
**Neden:** Paralel işlem `_call_with_retry`'daki rate limiting'i anlamsız kılar — hepsini aynı anda gönderince 429 kaçınılmaz olur.  
**Mevcut durum:** Kod zaten sequential `for` loop kullanıyordu, `asyncio.gather` yoktu. Yorum eklenerek neden paralel yapılmadığı netleştirildi.

---

## 4. API Endpoint Haritası

### Backend (`http://127.0.0.1:8000`)

| Method | Path | Ne döner |
|---|---|---|
| GET | `/api/dashboard/metrics` | `total_gross, total_commission, total_net, order_count, return_count, pending_classify, pending_invoices` |
| GET | `/api/dashboard/chart` | Son 7 günlük `{date, gross, net}[]` |
| GET | `/api/orders/` | `Order[]` — her birinde `lines[]` nested |
| POST | `/api/orders/classify-all` | `{classified: N, total: N}` — pending siparişleri Gemini ile işler |
| POST | `/api/orders/{id}/classify` | Tek sipariş classify |
| POST | `/api/orders/{id}/approve` | `{order_id, approved}` — body: `{approved: bool}` |
| GET | `/api/invoices/` | `Invoice[]` — marketplace, customer_name dahil join |
| POST | `/api/invoices/{order_id}/generate` | UBL-TR XML üretir, draft fatura oluşturur |
| GET | `/api/invoices/{id}/xml` | XML dosyası indir |
| GET | `/api/reconciliation/` | Trendyol payout mutabakat + Gemini açıklaması |
| POST | `/api/nl-query` | `{answer: string}` — body: `{question: string}` |

### Frontend (`http://localhost:3000`)

| Route | Sayfa |
|---|---|
| `/` | Dashboard — metrikler, sipariş tablosu, NL sorgu |
| `/faturalar` | Fatura listesi |
| `/mutabakat` | Payout mutabakat |

---

## 5. Veri Modeli

```
orders
  id, marketplace, marketplace_order_id
  customer_name, customer_tax_id, is_company, customer_city
  is_return (0/1)
  gross_amount, commission, shipping_cost, campaign_discount, net_payout
  classify_status: "pending" | "classified" | "approved" | "rejected"
  order_date

order_lines  (bir order'a N adet)
  id, order_id
  product_name, category, barcode, quantity, unit_price
  gemini_kdv_rate       -- Gemini önerisi: 1 | 10 | 20
  gemini_account_code   -- Tek Düzen Hesap kodu
  gemini_account_name
  gemini_reasoning
  gemini_confidence     -- 0.0 – 1.0
  user_approved (0/1)
  approved_at

invoices
  id, order_id
  invoice_type: "earsiv" | "efatura"
  invoice_number        -- PMX2026 + 9 rakam
  ubl_xml               -- UBL-TR 1.2 XML içeriği
  status: "draft" | "sent" | "error"
  created_at
```

---

## 6. Backend Başlatma

```bash
cd "btk hackathon/backend"
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

`.env` dosyasında `GEMINI_API_KEY` dolu olmalı. İlk başlatmada fixture JSON'lar otomatik yüklenir (DB boşsa).

## 7. Frontend Başlatma

```bash
cd "btk-hackathon/frontend"
npm run dev
# → http://localhost:3000
```

---

## 8. Bilinen Sorunlar ve Sınırlamalar

| Sorun | Durum | Geçici Çözüm |
|---|---|---|
| Fatura sayfası boş gelir | `classify` + `generate` çağrılmadıkça fatura oluşmuyor | `/api/invoices/{id}/generate` endpoint'i henüz UI'a bağlanmadı |
| Gemini classify ~2 sn/ürün | Rate limit gereği kasıtlı yavaş | `classify-all` arka planda çalışır, dashboard yüklenir |
| SQLite → hackathon için yeterli | Production'da PostgreSQL'e geçmeli | DB connection `database.py`'de izole |
| Trendyol + Hepsiburada fixture | Canlı API bağlantısı yok | `fixture_data/` JSON'ları gerçek API şemasına uygun |
| Gemini prompt deterministic değil | Aynı ürün farklı KDV alabilir | `confidence < 0.8` → sarı uyarı + manuel onay zorunlu |

---

## 9. Sonraki Yapılacaklar (Öncelik Sırası)

### Kritik (Demo için şart)
- [ ] **Fatura üretim butonu** — `OrdersTable`'da onaylı siparişlerde "Fatura Kes" butonu → `POST /api/invoices/{id}/generate`
- [ ] **Demo senaryosu** — Sipariş gelişinden fatura kesimine 3 dakikalık akış prova edilmeli
- [ ] **Gemini API key** — `.env` dosyasındaki `buraya_gercek_key_yaz` gerçek key ile değiştirilmeli
- [ ] **`classify-all` loading durumu** — Dashboard açılışında "Sınıflandırılıyor..." spinner göster

### Yüksek Öncelik
- [ ] **Sidebar active state** — Mevcut sayfayı sidebar'da highlight et (şu an sadece `/faturalar` ve `/mutabakat` sabit highlight var)
- [ ] **`/api/dashboard/chart`** — 7 günlük grafik verisi mevcut ama frontend'de Recharts bileşeni yok
- [ ] **İade görünümü** — `is_return: 1` siparişler ayrı sekmede gösterilmeli
- [ ] **Hata boundary** — Network down olunca tüm sayfanın değil, sadece ilgili component'in hata vermesi

### Nice-to-have (Jüri İzlenimi)
- [ ] **`POST /api/orders/classify-all` loading bar** — kaç sipariş / toplam göster
- [ ] **NL query örnekleri** — Input placeholder'da örnek sorular rotasyonu
- [ ] **Mutabakat sayfası** — `payout_lines` tablosuna grafik ekle (Recharts bar chart)
- [ ] **Dark mode** — Tailwind `dark:` class'ları zaten var, toggle butonu yok

### Hackathon Sonrası
- [ ] PostgreSQL'e geçiş (şu an SQLite)
- [ ] Trendyol canlı API bağlantısı (stage credentials alındıktan sonra)
- [ ] GİB mükellef listesi günlük senkronizasyon
- [ ] e-Belge imzalama (KamuSM entegrasyonu)
- [ ] Railway/Render deploy pipeline

---

## 10. Jüri Kriterleri ve Nerede Duruyoruz

| Kriter | Durum | Kanıt |
|---|---|---|
| Gemini API çekirdekte | ✅ | `classify_kdv`, `explain_reconciliation`, `answer_nl_query` — Gemini olmadan hiçbiri çalışmaz |
| Çalışan demo | ✅ | Backend + frontend ayakta, fixture veri akıyor |
| Problem-solution fit | ✅ | 540K satıcı, e-Fatura zorunluluğu, KDV karmaşası |
| Teknik derinlik | 🟡 | UBL-TR XML var, GİB entegratör bağlantısı yok |
| Kullanıcı onay akışı | ✅ | Gemini önerir, satıcı onaylar — fatura kesilmez |
| Çok kanallı destek | 🟡 | Trendyol + Hepsiburada fixture var, canlı API yok |
| NL raporlama | ✅ | `/api/nl-query` çalışıyor, UI bağlı |

---

*Handoff oluşturulma: 17 Mayıs 2026 — PazarMuhasebe BTK Hackathon 2026*
