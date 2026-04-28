import sqlite3
from datetime import datetime

DB_PATH = "leads.db"

def init_db():
    """Создаёт таблицу при первом запуске"""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                name TEXT,
                contact TEXT NOT NULL,
                source TEXT,
                comment TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_contact ON leads(contact)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON leads(created_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_source ON leads(source)")

def save_lead(name, contact, source, comment) -> int:
    """Сохраняет заявку, возвращает её id"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.execute(
                "INSERT INTO leads (created_at, name, contact, source, comment) VALUES (?,?,?,?,?)",
                (datetime.utcnow().isoformat(), name, contact, source, comment)
            )
            return cursor.lastrowid
    except sqlite3.Error as e:
        raise RuntimeError(f"Database write failed: {e}") from e

def get_all_leads():
    """Получить все заявки"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT id, created_at, name, contact, source, comment FROM leads ORDER BY created_at DESC")
        leads = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return leads
    except sqlite3.Error as e:
        raise RuntimeError(f"Database read failed: {e}") from e

def get_lead_by_id(lead_id: int):
    """Получить заявку по ID"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(
            "SELECT id, created_at, name, contact, source, comment FROM leads WHERE id = ?", (lead_id,)
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    except sqlite3.Error as e:
        raise RuntimeError(f"Database read failed: {e}") from e

def get_leads_filtered(date_from=None, date_to=None, source=None):
    """Получить заявки с фильтрацией (без лишнего логирования)"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    query = "SELECT id, created_at, name, contact, source, comment FROM leads WHERE 1=1"
    params = []
    
    if date_from and date_from.strip():
        clean_date = date_from.split('T')[0].strip()
        query += " AND DATE(created_at) >= ?"
        params.append(clean_date)
    
    if date_to and date_to.strip():
        clean_date = date_to.split('T')[0].strip()
        query += " AND DATE(created_at) <= ?"
        params.append(clean_date)
    
    if source and source.strip():
        query += " AND source LIKE ?"
        params.append(f"%{source.strip()}%")
    
    query += " ORDER BY created_at DESC"
    
    try:
        cursor = conn.execute(query, params)
        leads = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return leads
    except Exception as e:
        conn.close()
        # Пробрасываем ошибку, чтобы main.py её поймал
        raise RuntimeError(f"Filter query failed: {e}")

def get_unique_sources():
    """Получить список уникальных источников"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("SELECT DISTINCT source FROM leads WHERE source IS NOT NULL ORDER BY source")
    sources = [row[0] for row in cursor.fetchall()]
    conn.close()
    return sources

def get_lead_stats():
    """Статистика для графиков"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    # Заявки по дням (последние 7 дней)
    cursor = conn.execute("""
        SELECT DATE(created_at) as date, COUNT(*) as count 
        FROM leads 
        WHERE created_at >= datetime('now', '-7 days')
        GROUP BY DATE(created_at)
        ORDER BY date
    """)
    by_date = {row['date']: row['count'] for row in cursor.fetchall()}
    
    # Заявки по источникам
    cursor = conn.execute("""
        SELECT source, COUNT(*) as count 
        FROM leads 
        WHERE source IS NOT NULL AND source != ''
        GROUP BY source
        ORDER BY count DESC
        LIMIT 5
    """)
    by_source = {row['source']: row['count'] for row in cursor.fetchall()}
    
    # Общая статистика
    cursor = conn.execute("SELECT COUNT(*) as total, MAX(id) as last_id FROM leads")
    row = cursor.fetchone()
    
    conn.close()
    
    return {
        "by_date": by_date,
        "by_source": by_source,
        "total": row['total'] if row else 0,
        "last_id": row['last_id'] if row else 0
    }