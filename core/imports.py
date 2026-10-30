"""Чтение CSV и строгая проверка дневных счётчиков сообщений."""
from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import pandas as pd

REQUIRED = ('date', 'campaign_id', 'campaign_name', 'sent', 'delivered', 'clicked', 'unsubscribed')
COUNTS = ('sent', 'delivered', 'clicked', 'unsubscribed')
ALIASES = {
    'date': ['ReportDate', 'Дата', 'Дата периода'],
    'campaign_id': ['ReportMailingId', 'ID рассылки', 'Id рассылки'],
    'campaign_name': ['ReportMessageName', 'Название рассылки', 'Название письма', 'Рассылка'],
    'sent': ['ReportSent', 'Отправлено', 'Отправлено сообщений'],
    'delivered': ['ReportDelivered', 'Доставлено', 'Доставлено сообщений'],
    'clicked': ['ReportClicked', 'Кликов', 'Кликнуто', 'Сообщения с кликом'],
    'unsubscribed': ['ReportUnsubscribed', 'Отписок', 'Отписки'],
    'variant': ['ReportMailingVariantNum', 'Вариант'],
    'brand': ['ReportBrand', 'Бренд'],
    'channel': ['ReportChannel', 'Канал'],
    'category': ['ReportCategory', 'Категория'],
}
MAX_ROWS = 100_000
MAX_BYTES = 10 * 1024 * 1024


@dataclass
class ValidationResult:
    data: pd.DataFrame
    issues: pd.DataFrame

    @property
    def ok(self) -> bool:
        return self.issues.empty and not self.data.empty


def read_csv_bytes(payload: bytes) -> pd.DataFrame:
    if len(payload) > MAX_BYTES:
        raise ValueError('Файл больше 10 МБ. Сократите период выгрузки.')
    decoded = None
    encodings = ('utf-16',) if payload.startswith((b'\xff\xfe', b'\xfe\xff')) else ('utf-8-sig', 'cp1251')
    for encoding in encodings:
        try:
            decoded = payload.decode(encoding)
            break
        except UnicodeError:
            continue
    if decoded is None or not decoded.strip():
        raise ValueError('Не удалось прочитать CSV. Используйте UTF-8 и разделитель ; или ,.')
    try:
        sep = csv.Sniffer().sniff(decoded[:8192], delimiters=';,\t').delimiter
    except csv.Error:
        sep = ';' if ';' in decoded.splitlines()[0] else ','
    try:
        frame = pd.read_csv(io.StringIO(decoded), sep=sep, dtype=str, keep_default_na=False, nrows=MAX_ROWS + 1)
    except (pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise ValueError('Нарушена структура CSV. Проверьте разделитель, кавычки и число колонок.') from exc
    if len(frame) > MAX_ROWS:
        raise ValueError('Больше 100 000 строк. Сократите период выгрузки.')
    frame.columns = [str(c).strip() for c in frame.columns]
    return frame


def suggest_mapping(columns) -> dict[str, str]:
    lookup = {str(c).strip().casefold(): c for c in columns}
    return {key: lookup[name.casefold()] for key, names in ALIASES.items()
            for name in [next((n for n in [key, *names] if n.casefold() in lookup), '')] if name}


def _day(value: str) -> date:
    for fmt in ('%Y-%m-%d', '%d.%m.%Y'):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            pass
    raise ValueError('Дата должна иметь вид ГГГГ-ММ-ДД или ДД.ММ.ГГГГ')


def _count(value: str) -> int:
    cleaned = re.sub(r'[\s\u00a0\u202f]', '', value).replace(',', '.')
    try:
        n = Decimal(cleaned)
    except InvalidOperation as exc:
        raise ValueError('Нужно целое неотрицательное число') from exc
    if not n.is_finite() or n < 0 or n != n.to_integral_value() or n > 10**12:
        raise ValueError('Нужно целое число от 0 до 1 000 000 000 000')
    return int(n)


def validate(frame: pd.DataFrame, mapping: dict[str, str], today: date) -> ValidationResult:
    issues, records = [], []
    def error(row, field, message):
        issues.append({'Строка': row, 'Поле': field, 'Ошибка': message})
    missing = [k for k in REQUIRED if not mapping.get(k) or mapping[k] not in frame.columns]
    if missing:
        error(1, 'Колонки', 'Не сопоставлены: ' + ', '.join(missing))
        return ValidationResult(pd.DataFrame(), pd.DataFrame(issues))
    if len(set(mapping.values())) != len(mapping.values()):
        error(1, 'Колонки', 'Одна колонка не может соответствовать нескольким полям')
        return ValidationResult(pd.DataFrame(), pd.DataFrame(issues))
    if frame.empty:
        error(1, 'Файл', 'Нет строк с данными')
    if len(frame) > MAX_ROWS:
        error(1, 'Файл', 'Превышено ограничение 100 000 строк')
        return ValidationResult(pd.DataFrame(), pd.DataFrame(issues))
    seen = set()
    for offset, (_, row) in enumerate(frame.iterrows(), 2):
        before = len(issues)
        rec = {k: str(row[col]).strip() for k, col in mapping.items()}
        for key in ('campaign_id', 'campaign_name'):
            if not rec[key] or len(rec[key]) > 300:
                error(offset, key, 'Обязательное поле, не более 300 символов')
        try:
            rec['date'] = _day(rec['date'])
            if rec['date'] > today:
                error(offset, 'date', 'Дата находится в будущем')
        except ValueError as exc:
            error(offset, 'date', str(exc))
        for key in COUNTS:
            try:
                rec[key] = _count(rec[key])
            except ValueError as exc:
                error(offset, key, str(exc))
        if rec.get('channel', 'email').casefold() not in ('email', 'e-mail'):
            error(offset, 'channel', 'MVP принимает только email. Отфильтруйте другие каналы.')
        if rec.get('category', 'automatic').casefold() not in ('automatic', 'автоматически', 'автоматические', 'автоматическая', 'автоматические рассылки'):
            error(offset, 'category', 'MVP принимает только автоматические рассылки.')
        if len(issues) != before:
            continue
        if rec['delivered'] > rec['sent']:
            error(offset, 'delivered', 'Доставлено больше, чем отправлено')
        for key in ('clicked', 'unsubscribed'):
            if rec[key] > rec['delivered']:
                error(offset, key, 'Число сообщений превышает доставленные')
        rec['variant'] = rec.get('variant') or '1'
        rec['brand'] = rec.get('brand') or ''
        rec['campaign_key'] = json.dumps([rec['campaign_id'], rec['variant'], rec['brand']], ensure_ascii=False)
        unique = (rec['campaign_key'], rec['date'])
        if unique in seen:
            error(offset, 'date / campaign_id', 'Дубликат дня, рассылки, варианта и бренда. Уберите итоги и лишние разрезы.')
        seen.add(unique)
        records.append({k: rec[k] for k in (*REQUIRED, 'variant', 'brand', 'campaign_key')})
    result = pd.DataFrame(records)
    # Не разрешаем незаметно использовать только корректную часть ошибочного файла.
    if issues:
        result = pd.DataFrame()
    elif not result.empty:
        result = result.sort_values(['date', 'campaign_key']).reset_index(drop=True)
    return ValidationResult(result, pd.DataFrame(issues, columns=['Строка', 'Поле', 'Ошибка']))


def csv_bytes(frame: pd.DataFrame) -> bytes:
    """Защита текстовых ячеек от исполнения формул при открытии в Excel."""
    out = frame.copy()
    def safe(value):
        if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')):
            return "'" + value
        return value
    for col in out.columns:
        out[col] = out[col].map(safe)
    return out.to_csv(index=False, sep=';', lineterminator='\n').encode('utf-8-sig')
