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
        """)
