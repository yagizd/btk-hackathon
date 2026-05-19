import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.path.join(os.path.dirname(__file__), "pazarmuhasebe.db")


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _migrate(conn):
    """Mevcut DB'lerde eksik kolonları güvenli şekilde ekler."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(order_lines)").fetchall()}
    if "gemini_alternatives" not in existing:
        try:
            conn.execute("ALTER TABLE order_lines ADD COLUMN gemini_alternatives TEXT")
        except Exception:
            pass


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                marketplace TEXT NOT NULL,
                marketplace_order_id TEXT UNIQUE,
                customer_name TEXT,
                customer_tax_id TEXT,
                is_company INTEGER DEFAULT 0,
                customer_city TEXT,
                is_return INTEGER DEFAULT 0,
                gross_amount REAL DEFAULT 0,
                commission REAL DEFAULT 0,
                shipping_cost REAL DEFAULT 0,
                campaign_discount REAL DEFAULT 0,
                net_payout REAL DEFAULT 0,
                classify_status TEXT DEFAULT 'pending',
                order_date TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS order_lines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER REFERENCES orders(id) ON DELETE CASCADE,
                product_name TEXT,
                category TEXT,
                barcode TEXT,
                quantity INTEGER DEFAULT 1,
                unit_price REAL,
                gemini_kdv_rate INTEGER,
                gemini_account_code TEXT,
                gemini_account_name TEXT,
                gemini_reasoning TEXT,
                gemini_confidence REAL,
                gemini_alternatives TEXT,         -- JSON: [{kdv_orani, hesap_kodu, hesap_adi, gerekce, guven_skoru}]
                user_approved INTEGER,
                approved_at TEXT
            );

            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id INTEGER REFERENCES orders(id) ON DELETE CASCADE,
                invoice_type TEXT,
                invoice_number TEXT UNIQUE,
                ubl_xml TEXT,
                status TEXT DEFAULT 'draft',
                created_at TEXT DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS chat_sessions (
                session_id TEXT NOT NULL,
                turn INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (session_id, turn)
            );

            CREATE TABLE IF NOT EXISTS return_classifications (
                order_id INTEGER PRIMARY KEY REFERENCES orders(id) ON DELETE CASCADE,
                reason TEXT,                    -- damaged | wrong_item | size_fit | preference | late_delivery | quality | other
                refund_category TEXT,           -- cash_refund | replacement | partial_refund | warranty
                kdv_adjustment_needed INTEGER DEFAULT 0,
                gemini_explanation TEXT,
                gemini_confidence REAL,
                created_at TEXT DEFAULT (datetime('now'))
            );
        """)
        _migrate(conn)
