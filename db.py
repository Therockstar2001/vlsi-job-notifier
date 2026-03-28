import sqlite3

DB_NAME = "jobs.db"


def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company TEXT,
            title TEXT,
            location TEXT,
            url TEXT,
            dedup_key TEXT UNIQUE,
            source TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def job_exists(dedup_key):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("SELECT 1 FROM jobs WHERE dedup_key = ?", (dedup_key,))
    result = cur.fetchone()

    conn.close()
    return result is not None


def save_job(company, title, location, url, dedup_key, source):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO jobs (company, title, location, url, dedup_key, source)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (company, title, location, url, dedup_key, source))

    conn.commit()
    conn.close()