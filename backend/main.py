from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db
from routers.orders import router as orders_router, import_fixtures_if_empty
from routers.invoices import router as invoices_router
from routers.reconciliation import router as reconciliation_router
from routers.nl_query import router as nl_query_router
from routers.dashboard import router as dashboard_router
from routers.returns import router as returns_router

app = FastAPI(
    title="PazarMuhasebe API",
    description="BTK Hackathon 2026 — E-ticaret ön muhasebe otomasyonu",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(orders_router)
app.include_router(invoices_router)
app.include_router(reconciliation_router)
app.include_router(nl_query_router)
app.include_router(dashboard_router)
app.include_router(returns_router)


@app.on_event("startup")
def startup():
    init_db()
    import_fixtures_if_empty()
    print("[OK] PazarMuhasebe API baslatildi - fixture veriler yuklendi")


@app.get("/")
def root():
    return {"status": "ok", "app": "PazarMuhasebe API", "version": "1.0.0"}


@app.get("/health")
def health():
    return {"status": "healthy"}
