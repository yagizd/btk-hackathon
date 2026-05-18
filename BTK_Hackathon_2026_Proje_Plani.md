# BTK Hackathon 2026 — Ön Muhasebe Otomasyon Projesi
## Kapsamlı Proje Planı

> **Ürün adı (öneri):** PazarMuhasebe  
> **Süre:** 14 gün (6–19 Mayıs 2026)  
> **Takım:** En fazla 3 kişi  
> **Zorunluluk:** Google Gemini API çekirdekte kullanılmalı  
> **Hedef:** İlk 10'a girerek 5 Haziran jüri sunumuna kalmak

---

## 1. Ürün Ne Yapıyor? (Tek Cümle)

Trendyol, Hepsiburada ve Amazon TR'deki satışları, iadeleri, komisyon kesintilerini ve kargo masraflarını otomatik çekerek Gemini ile KDV/hesap sınıflandırması yapan ve tek tuşla e-Arşiv/e-Fatura kesen web uygulaması.

---

## 2. Neden Bu Ürün? (Jüri İçin Argüman)

| Argüman | Veri |
|---|---|
| Pazar büyüklüğü | 600.800 aktif e-ticaret işletmesi, 540.000+ pazaryeri satıcısı |
| Regülatif zorlama | 500.000 TL ciro üzeri e-Fatura zorunlu (2025), 2027'de tüm faturalar |
| Rakipsiz alan | Türkiye'de çoklu kanal payout mutabakatı + Gemini sınıflandırması yapan ürün yok |
| Gemini zorunluluğu | KDV sınıflandırma + anomali tespiti + NL raporlama = Gemini çekirdekte, çıkarılamaz |

---

## 3. Sistem Mimarisi

```
┌─────────────────────────────────────────────────────┐
│  VERİ KAYNAKLARI                                    │
│  Trendyol Partner API  │  Hepsiburada API  │  Amazon SP-API │
└──────────────┬──────────────────┬───────────────────┘
               │ webhook + polling│
┌──────────────▼──────────────────▼───────────────────┐
│  NORMALIZER KATMANI (Python/FastAPI)                │
│  Her pazaryerinden gelen ham veriyi                 │
│  kanonik sipariş şemasına dönüştürür                │
│  Order | Customer | Payout | Commission | Refund    │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│  GEMİNİ AJAN KATMANI (LangGraph)                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌───────┐ │
│  │KDV Ajanı │ │Mutabakat │ │İade Ajanı│ │NL Rap.│ │
│  │%1/10/20  │ │Payout vs │ │KDV düz.  │ │Soru   │ │
│  │Hesap eşl.│ │Sipariş   │ │Muhasebe  │ │Cevap  │ │
│  └──────────┘ └──────────┘ └──────────┘ └───────┘ │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│  E-BELGE KATMANI                                    │
│  UBL-TR 1.2 XML üretimi                             │
│  → Bireysel müşteri: e-Arşiv                        │
│  → Kurumsal (GİB mükellef listesi): e-Fatura        │
│  → GİB Özel Entegratör API (NES / QNB eFinans)      │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│  ÇIKTILAR                                           │
│  Satıcı Dashboard  │  Mali Müşavir Paneli  │  e-Defter │
└─────────────────────────────────────────────────────┘
```

---

## 4. Teknoloji Seçimleri

| Katman | Teknoloji | Gerekçe |
|---|---|---|
| Backend | Python + FastAPI | Gemini SDK, LangGraph ile doğal uyum |
| Veritabanı | PostgreSQL | Muhasebe verisi için ACID uyumu şart |
| Kuyruk / cache | Redis | Polling job yönetimi, rate limit buffer |
| AI orchestration | LangGraph + Gemini 2.0 Flash | Multi-agent akış, düşük gecikme |
| Frontend | React + Next.js | SSR ile dashboard hızlı yüklenir |
| e-Belge | Kendi UBL-TR üretici | GİB şema değişikliklerine bağımsızlık |
| Auth | JWT + OAuth2 | Pazaryeri API tokenları için |
| Deployment | Railway / Render (hackathon) | Ücretsiz, hızlı deploy |

---

## 5. 14 Günlük Sprint Planı

### Gün 1–2: Temel kurulum
- [ ] GitHub repo oluştur, README yaz, mimari diyagramı ekle
- [ ] FastAPI boilerplate + PostgreSQL schema (sipariş, fatura, cari, kalem tabloları)
- [ ] Trendyol stage API credentials al, Postman koleksiyonunu import et
- [ ] Gemini API key al, basit prompt testi yap

### Gün 3–4: Trendyol connector
- [ ] `GET /orders` endpoint polling — her 10 dakikada bir çalışan cron job
- [ ] Webhook endpoint yaz — Trendyol sipariş bildirimi gelince tetiklensin
- [ ] Kanonik sipariş modeline normalizasyon (brüt tutar, komisyon, kargo, KDV satırları)
- [ ] Rate limit yönetimi: exponential backoff + Redis kuyruk

### Gün 5–6: Gemini ajan katmanı
- [ ] **KDV ajanı:** ürün adı → `{kdv_orani: 1|10|20, gerekce: "...", hesap_kodu: "153"}` structured output
- [ ] **Mutabakat ajanı:** Trendyol payout JSON'u parse et, sipariş toplamıyla karşılaştır, fark varsa uyarı üret
- [ ] **İade ajanı:** iade siparişini tanı, KDV düzeltme kaydı oluştur
- [ ] LangGraph ile ajanları pipeline'a bağla

### Gün 7–8: e-Belge üretimi
- [ ] UBL-TR 1.2 XML şemasını implemente et (zorunlu alanlar: VKN/TCKN, adres, kalem, KDV, toplam)
- [ ] GİB mükellef sorgusu: müşteri VKN'si mükellef listesinde mi? → e-Fatura / e-Arşiv dallandırma
- [ ] Sandbox XML üretimi ve validasyonu (imzasız — hackathon için yeterli)
- [ ] NES veya QNB eFinans sandbox API bağlantısı dene

### Gün 9–10: Frontend dashboard
- [ ] Satıcı dashboard: metrik kartlar (brüt satış, komisyon, net hak ediş, belge sayısı)
- [ ] Sipariş listesi: pazaryeri etiketi, ürün adı, Gemini KDV önerisi, onay butonu
- [ ] e-Belge durumu paneli: gönderildi / beklemede / hata
- [ ] Gemini analiz kutusu: otomatik tespitler, mutabakat sonucu
- [ ] Doğal dil sorgu inputu: "Bu ay kâr marjım ne?" → Gemini cevabı

### Gün 11–12: Test + hata düzeltme
- [ ] Stage ortamında 50+ sipariş ile uçtan uca test
- [ ] Hatalı KDV önerisi senaryosu: Gemini ne öneriyor, kullanıcı onay akışı çalışıyor mu?
- [ ] Rate limit simülasyonu: Redis kuyruğunu kasıtlı doldur, recover süresini ölç
- [ ] XML validasyonu: GİB şema kontrolünden geçiyor mu?

### Gün 13: Demo hazırlığı
- [ ] Hepsiburada için gerçek API şemasına uygun fixture JSON hazırla
- [ ] Demo senaryosu yaz: sipariş gelişinden e-Arşiv kesimine kadar 3 dakikalık akış
- [ ] 90 saniyelik tanıtım videosu çek (demo gününe girememe senaryosu için)

### Gün 14: Teslim
- [ ] GitHub README güncelle: kurulum adımları, mimari diyagram, video linki
- [ ] Canlı URL deploy et (Railway ücretsiz tier yeterli)
- [ ] BTK Akademi başvuru sayfasına yükle

---

## 6. Kim Ne Yapacak? (3 Kişilik Takım)

### Kişi A — Backend + API entegrasyonu
**Elle yapılması lazım:**
- Trendyol stage API credentials almak (satıcı paneline manuel giriş gerekiyor)
- Rate limit davranışını gerçek isteklerle test etmek — otomatize edilemez
- GİB mükellef listesi güncel versiyonunu indirip veritabanına yüklemek

**Claude Code yapabilir:**
- FastAPI boilerplate + endpoint şablonları
- Trendyol connector kodu (polling + webhook handler)
- PostgreSQL migration dosyaları
- Exponential backoff + Redis kuyruk implementasyonu
- UBL-TR XML üretici sınıfı

### Kişi B — AI / Gemini katmanı
**Elle yapılması lazım:**
- Gemini prompt'larını gerçek sipariş verileriyle iteratif olarak ayarlamak
- KDV sınıflandırmasının edge case'lerini elle test etmek (gıda takviyesi, kozmetik gibi muğlak kategoriler)
- LangGraph agent grafiğinin mantıksal akışını tasarlamak

**Claude Code yapabilir:**
- Gemini structured output şemaları (Pydantic modeller)
- LangGraph agent pipeline kodu
- Her ajan için prompt şablonları (ilk versiyon)
- Mutabakat hesaplama mantığı
- NL → SQL dönüşüm ajanı

### Kişi C — Frontend + demo
**Elle yapılması lazım:**
- Demo senaryosunu tasarlamak ve prova yapmak
- Jüri sunumu 7 dakikalık scriptini yazmak
- Fixture JSON'ları gerçek Trendyol API yanıtına bakarak hazırlamak

**Claude Code yapabilir:**
- React dashboard komponentleri
- Sipariş listesi, metrik kartlar, e-belge durum paneli
- Gemini analiz kutusu UI
- NL sorgu inputu ve cevap gösterimi
- Responsive layout

---

## 7. Gemini Kullanım Noktaları (Jüri İçin Kritik)

Jüri "Gemini neden var?" diye soracak. Bunların hepsi hazır olmalı:

| # | Kullanım | Neden kural tabanlı yapılamaz? |
|---|---|---|
| 1 | Ürün adından KDV oranı çıkarma | 50.000+ ürün varyasyonu, belirsiz Türkçe ifadeler |
| 2 | Ürün → Tek Düzen Hesap Planı eşleme | Bağlam gerektiriyor, kural sayısı patlar |
| 3 | Payout anomali açıklaması | Fark neden oluştu? Doğal dil açıklama üretimi |
| 4 | İade nedenini sınıflandırma | Serbest metin — "beğenmedim", "bozuk geldi" |
| 5 | NL sorgulama | "Bu ay Trendyol kârım ne?" → SQL + hesaplama |

---

## 8. Kritik Riskler ve Çözümleri

### Risk 1: Trendyol stage credentials geç gelir
**Olasılık:** Orta  
**Çözüm:** İlk gün başvur. Gecikirse Trendyol'un public Postman koleksiyonundaki mock response'ları kullan, connector kodunu onunla geliştir. Stage bağlantısı gelince kolay swap edilir.

### Risk 2: Hepsiburada manuel onayı gelmez
**Olasılık:** Yüksek  
**Çözüm:** Demo'da hibrit model: Trendyol gerçek canlı veri + Hepsiburada için resmi API şemasına birebir uygun fixture JSON. Jüriye açıkça söyle — bu dürüstlük puan kazandırır.

### Risk 3: Gemini KDV önerisi hatalı olursa
**Olasılık:** Orta (edge case'lerde)  
**Çözüm:** "İnsan döngüde" tasarım. Gemini önerir, satıcı onaylar — onay olmadan fatura kesilmez. Onay ekranı UI'da görünür olmalı.

### Risk 4: UBL-TR XML GİB validasyonundan geçmez
**Olasılık:** Orta  
**Çözüm:** Hackathon için imzasız XML üretimi yeterli. GİB'in açık XSD şemasını indirip XML'i buna validate et — imzalama olmadan da yapısal doğruluk gösterilebilir.

### Risk 5: Rate limit demo günü sistemi çökertir
**Olasılık:** Düşük (stage'de sınırlı veri)  
**Çözüm:** Demo'da canlı polling yerine önceden çekilmiş cache'lenmiş veri göster. "Gerçek zamanlı" yanılsamasını bozma — ama güvenli tut.

### Risk 6: Takım kapsamı aşar, 14 günde bitmez
**Olasılık:** Yüksek  
**Çözüm:** MVP scope'u koru. Çalışan 1 kanal (Trendyol) + Gemini KDV + XML üretim + dashboard = kazanmaya yeter. Amazon SP-API karmaşık, ikinci fazda bırak.

---

## 9. MVP Scope (Ne Olursa Olsun Bitmeli)

| Özellik | Durum |
|---|---|
| Trendyol stage bağlantısı | Zorunlu |
| Sipariş normalizasyonu | Zorunlu |
| Gemini KDV sınıflandırması | Zorunlu |
| Kullanıcı onay akışı | Zorunlu |
| UBL-TR XML üretimi (imzasız) | Zorunlu |
| Satıcı dashboard | Zorunlu |
| Payout mutabakatı | Yüksek öncelik |
| NL sorgu (Gemini) | Yüksek öncelik |
| Hepsiburada canlı bağlantı | Düşürülebilir → fixture |
| Amazon SP-API | Kapsam dışı |
| Gerçek mali mühür / imzalama | Kapsam dışı |
| e-Defter export | Kapsam dışı (yol haritası) |

---

## 10. Veritabanı Şeması (Temel Tablolar)

```sql
-- Pazaryeri siparişleri
orders (
  id, marketplace, marketplace_order_id,
  gross_amount, commission, shipping_cost,
  campaign_discount, stoppage_amount,
  net_payout, status, created_at
)

-- Sipariş kalemleri
order_lines (
  id, order_id, product_name, barcode,
  quantity, unit_price,
  gemini_kdv_rate,      -- Gemini'nin önerisi
  gemini_account_code,  -- Tek Düzen Hesap
  gemini_confidence,    -- 0.0-1.0
  user_approved_kdv,    -- Kullanıcı onayı
  approved_at
)

-- Müşteriler / cariler
customers (
  id, name, tax_number, is_company,
  is_efatura_taxpayer,  -- GİB mükellef listesi
  address, city
)

-- e-Belgeler
invoices (
  id, order_id, invoice_type,  -- earsiv / efatura / iptal
  invoice_number, ubl_xml,
  status,  -- draft / sent / accepted / error
  integrator_response, sent_at
)

-- Payout mutabakat kayıtları
payout_reconciliations (
  id, marketplace, period,
  expected_amount, actual_amount,
  difference, gemini_explanation, status
)
```

---

## 11. Gemini Prompt Şablonları (Başlangıç)

### KDV Ajanı
```
Sen Türkiye vergi mevzuatına hakim bir muhasebe asistanısın.
Aşağıdaki ürün bilgisine bakarak:
1. KDV oranını belirle (1, 10 veya 20)
2. Tek Düzen Hesap Planı'ndan uygun hesap kodunu seç
3. Kararının gerekçesini 1 cümleyle açıkla

Ürün adı: {urun_adi}
Kategori (pazaryerinden): {kategori}

Yanıtı SADECE JSON olarak döndür:
{
  "kdv_orani": 20,
  "hesap_kodu": "153",
  "hesap_adi": "Ticari Mallar",
  "gerekce": "Tekstil ürünü, genel KDV oranı uygulanır.",
  "guven_skoru": 0.95
}
```

### Mutabakat Ajanı
```
Trendyol'un ödediği tutar ile bizim hesapladığımız tutar arasında 
{fark} TL fark var.

Payout detayı: {payout_json}
Sipariş toplamları: {siparis_json}

Bu farkın olası nedenini kısa ve anlaşılır Türkçe ile açıkla.
Satıcıya ne yapması gerektiğini söyle.
```

---

## 12. Jüri Sunumu 7 Dakika Planı

| Dakika | İçerik |
|---|---|
| 0:00–1:00 | Problem: "Türkiye'de 540.000 pazaryeri satıcısı var, hepsi e-Belge kesmek zorunda, ama hiçbiri payout mutabakatını otomatik yapamıyor" |
| 1:00–2:30 | Demo: Trendyol'dan canlı sipariş çekimi → Gemini KDV önerisi → kullanıcı onayı → XML üretimi |
| 2:30–3:30 | Fark: Paraşüt vs biz — payout satır ayrıştırması göster |
| 3:30–4:30 | Gemini neden şart: muğlak ürün adı → KDV tespiti canlı göster |
| 4:30–5:30 | Pazar: 600K işletme, 2025 e-Fatura zorunluluğu, 2026 e-Defter |
| 5:30–6:30 | İş modeli: aylık 299-599 TL, TÜRMOB kanal, e-Defter modülü |
| 6:30–7:00 | Yol haritası + takım tanıtımı |

---

## 13. Eksiklikler ve Dürüst Değerlendirme

### Bilinen eksikler (demo öncesi kapatılmalı)
- Gerçek mali mühür / e-imza → sandbox'ta imzasız göster, kabul edilebilir
- Hepsiburada canlı bağlantısı → fixture JSON ile çöz
- KDV edge case'leri (gıda takviyesi, kozmetik) → prompt iterasyonu gerekir

### Bilinen eksikler (jüriye açıkça söyle)
- Amazon SP-API yok → "ikinci faz" olarak sun
- e-Defter export yok → "Ocak 2026 zorunluluğuna hazırlanıyoruz" de
- Gerçek GİB entegratör anlaşması yok → "üretime geçişte beyaz etiket ortaklık" de

### Yapısal zayıflıklar (dikkat)
- Gemini prompt'ları deterministic değil: aynı ürün bazen farklı KDV önerisi alabilir → güven skoru düşükse "elle onayla" uyarısı göster
- GİB mükellef listesi günde birkaç kez değişiyor → günlük senkronizasyon job yaz
- UBL-TR şeması karmaşık, zorunlu alan atlanırsa GİB reddeder → XSD validasyonu şart

---

## 14. Sonraki Adımlar (Hackathon Sonrası)

1. GİB özel entegratör anlaşması için başvuru (NES veya QNB eFinans)
2. Gerçek mali mühür entegrasyonu (KamuSM)
3. Hepsiburada ve Amazon canlı bağlantı
4. e-Defter modülü (Ocak 2026 zorunluluğu için)
5. TÜRMOB üyelerine pilot teklif
6. SaaS fiyatlandırma: aylık 299 TL (küçük satıcı) / 599 TL (çok kanal)

---

*Plan son güncellenme: Mayıs 2026 — BTK Akademi Hackathon 2026 için hazırlanmıştır.*
