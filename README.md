# PazarMuhasebe — BTK Hackathon 2026

E-ticaret pazaryeri satıcıları için Google Gemini destekli ön muhasebe otomasyonu.

## Özellikler
- Trendyol ve Hepsiburada sipariş entegrasyonu (fixture-based demo)
- Google Gemini ile otomatik KDV sınıflandırması (%1 / %10 / %20)
- Payout mutabakat analizi + Gemini açıklaması
- UBL-TR 1.2 uyumlu e-Arşiv / e-Fatura XML üretimi
- Doğal dil sorgulama ("Bu ay kârım ne?")

## Kurulum

### Backend
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env
# .env dosyasına GEMINI_API_KEY değerini girin
uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Uygulama: http://localhost:3000  
API Docs: http://localhost:8000/docs

## Teknoloji
- Backend: Python 3.11 + FastAPI + SQLite
- AI: Google Gemini 2.0 Flash (google-genai SDK)
- Frontend: Next.js 14 + TypeScript + Tailwind CSS + Recharts

## Mimari
```
Trendyol / Hepsiburada → FastAPI Normalizer → Gemini KDV Ajanı → UBL-TR XML → Next.js Dashboard
```

## BTK Hackathon 2026
Bu proje BTK Akademi × Google × GİRVAK Hackathon 2026 için geliştirilmiştir.  
Gemini API zorunlu kullanım kriteri: KDV sınıflandırma, mutabakat analizi, doğal dil sorgulama.
