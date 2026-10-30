"""SQLite: по умолчанию отдельная база в памяти для каждой браузерной сессии."""
import sqlite3
from pathlib import Path

import pandas as pd

STATUSES = ('Новый', 'В работе', 'Проверен')


def connect(path=':memory:'):
    if path != ':memory:':
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, check_same_thread=False)
    db.execute('''CREATE TABLE IF NOT EXISTS reviews (
        signal_id TEXT PRIMARY KEY, status TEXT NOT NULL, comment TEXT NOT NULL,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    return db


def save_review(db, signal_id: str, status: str, comment: str):
    if status not in STATUSES:
        raise ValueError('Неизвестный статус')
    if len(comment) > 2000:
        raise ValueError('Комментарий не должен превышать 2000 символов')
    with db:
        db.execute('''INSERT INTO reviews(signal_id,status,comment) VALUES(?,?,?)
            ON CONFLICT(signal_id) DO UPDATE SET status=excluded.status,
            comment=excluded.comment,updated_at=CURRENT_TIMESTAMP''', (signal_id, status, comment))


def attach_reviews(db, signals: pd.DataFrame) -> pd.DataFrame:
    out = signals.copy()
    reviews = {r[0]: r[1:] for r in db.execute('SELECT signal_id,status,comment FROM reviews')}
    out['status'] = [reviews.get(i, ('Новый', ''))[0] for i in out['id']]
    out['comment'] = [reviews.get(i, ('Новый', ''))[1] for i in out['id']]
    return out
