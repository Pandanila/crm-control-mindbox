"""Объяснимые правила: сравнение каждого дня только с предшествующей историей."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

RULES = {'no_sends': 'Нет отправок', 'delivery': 'Снижение доставляемости',
         'click': 'Снижение кликабельности', 'unsubscribe': 'Рост отписок'}
TIPS = {
    'no_sends': 'Проверьте активность рассылки, расписание и условия входа в сценарий Mindbox.',
    'delivery': 'Проверьте статусы недоставки, качество контактов и настройки отправителя в Mindbox.',
    'click': 'Проверьте ссылки, контент и изменения аудитории. Сравните сопоставимые периоды в Mindbox.',
    'unsubscribe': 'Проверьте частоту коммуникаций, аудиторию и соответствие содержания ожиданиям подписчиков.',
}


@dataclass(frozen=True)
class Settings:
    history_days: int = 14
    min_history: int = 7
    min_volume: int = 100
    delivery_drop_pp: float = 5.0
    click_drop_pct: float = 40.0
    unsubscribe_rate_pct: float = 1.0
    reaction_age_days: int = 3

    def __post_init__(self):
        if not 1 <= self.min_history <= self.history_days <= 90:
            raise ValueError('Число дней истории должно быть от 1 до длины окна (не более 90).')
        if self.min_volume < 1 or self.reaction_age_days < 1:
            raise ValueError('Минимальный объём и возраст данных должны быть положительными.')
        if not 0 < self.delivery_drop_pp <= 100 or not 0 < self.click_drop_pct <= 100:
            raise ValueError('Пороги снижения должны быть больше 0 и не больше 100.')
        if not 0 <= self.unsubscribe_rate_pct <= 100:
            raise ValueError('Порог отписок должен быть от 0 до 100%.')


def metrics(data: pd.DataFrame) -> pd.DataFrame:
    out = data.copy()
    for name, num, den in [('delivery_rate', 'delivered', 'sent'), ('click_rate', 'clicked', 'delivered'),
                           ('unsubscribe_rate', 'unsubscribed', 'delivered')]:
        out[name] = out[num].div(out[den].where(out[den] > 0)) * 100
    return out


def signal_id(project: str, campaign: str, day: date, rule: str) -> str:
    return hashlib.sha256(f'{project}\0{campaign}\0{day}\0{rule}'.encode()).hexdigest()[:24]


def analyze(data: pd.DataFrame, settings: Settings, today: date, start: date, end: date,
            expected_daily=(), complete_period=False, project='demo') -> tuple[pd.DataFrame, pd.DataFrame]:
    if start > end:
        raise ValueError('Начало периода позже окончания.')
    if (end - start).days > 90:
        raise ValueError('Для одного анализа выберите не более 91 календарного дня.')
    if data.empty:
        return pd.DataFrame(), pd.DataFrame()
    df = metrics(data)
    signals, checks = [], []
    expected_daily = set(expected_daily)
    for key, group in df.groupby('campaign_key', sort=False):
        group = group.sort_values('date')
        name = str(group.iloc[-1]['campaign_name'])
        campaign_id = str(group.iloc[-1]['campaign_id'])
        lookup = group.set_index('date')
        lower, upper = group['date'].min(), df['date'].max()
        for day in pd.date_range(start, end).date:
            if day >= today:
                checks.append({'Рассылка': name, 'Дата': day, 'Проверка': 'Все', 'Результат': 'День не завершён'})
                continue
            hist = group[(group['date'] < day) & (group['date'] >= day - timedelta(days=settings.history_days))]
            actual = lookup.loc[day] if day in lookup.index else None
            inferred_zero = actual is None and complete_period and key in expected_daily and lower <= day <= upper
            def check(label, reason):
                checks.append({'Рассылка': name, 'Дата': day, 'Проверка': label, 'Результат': reason})
            def emit(rule, value, baseline, explanation, metric, severity='Высокий'):
                signals.append({'id': signal_id(project, key, day, rule), 'project': project,
                    'campaign_key': key, 'campaign_id': campaign_id, 'campaign_name': name,
                    'date': day, 'rule': rule, 'type': RULES[rule], 'severity': severity,
                    'value': value, 'baseline': baseline, 'metric': metric,
                    'explanation': explanation, 'recommendation': TIPS[rule]})
            if actual is None and not inferred_zero:
                check('Все', 'Нет строки: нулевые отправки не подтверждены')
                continue
            sent = 0 if inferred_zero else int(actual['sent'])
            if key in expected_daily:
                h = hist[hist['sent'] >= settings.min_volume]
                if sent == 0 and len(h) >= settings.min_history:
                    typical = float(h['sent'].median())
                    source = 'Отсутствующая строка интерпретирована как ноль по подтверждению полноты.' if inferred_zero else 'В файле явно указано 0 отправок.'
                    emit('no_sends', 0, typical, f'Отправок нет. Медиана истории: {typical:,.0f} сообщений. {source}', 'sent')
                    check(RULES['no_sends'], 'Сигнал')
                elif sent == 0:
                    check(RULES['no_sends'], 'Недостаточно истории с достаточным объёмом')
                else:
                    check(RULES['no_sends'], 'Отклонения нет')
            if sent == 0:
                check('Процентные метрики', 'Нет отправок, деление на ноль исключено')
                continue
            # Доставляемость сравниваем с достаточно объёмными днями.
            h = hist[hist['sent'] >= settings.min_volume]
            if actual['sent'] < settings.min_volume:
                check(RULES['delivery'], 'Малый объём отправок')
            elif len(h) < settings.min_history:
                check(RULES['delivery'], 'Недостаточно истории')
            else:
                base, value = float(h['delivery_rate'].median()), float(actual['delivery_rate'])
                if base - value >= settings.delivery_drop_pp:
                    emit('delivery', value, base, f'Доставляемость {value:.2f}% против медианы {base:.2f}%. Снижение {base-value:.2f} п.п.', 'delivery_rate')
                    check(RULES['delivery'], 'Сигнал')
                else:
                    check(RULES['delivery'], 'Отклонения нет')
            mature = day <= today - timedelta(days=settings.reaction_age_days)
            if not mature:
                check('Клики и отписки', 'Реакции ещё накапливаются')
                continue
            if actual['delivered'] < settings.min_volume:
                check('Клики и отписки', 'Малый объём доставленных сообщений')
                continue
            h = hist[hist['delivered'] >= settings.min_volume]
            if len(h) < settings.min_history:
                check(RULES['click'], 'Недостаточно истории')
            else:
                base, value = float(h['click_rate'].median()), float(actual['click_rate'])
                if base <= 0:
                    check(RULES['click'], 'Нулевая база сравнения')
                elif (base-value) / base * 100 >= settings.click_drop_pct:
                    emit('click', value, base, f'Кликабельность {value:.2f}% против медианы {base:.2f}%. Снижение {(base-value)/base*100:.1f}%.', 'click_rate', 'Средний')
                    check(RULES['click'], 'Сигнал')
                else:
                    check(RULES['click'], 'Отклонения нет')
            value = float(actual['unsubscribe_rate'])
            if value > settings.unsubscribe_rate_pct:
                emit('unsubscribe', value, settings.unsubscribe_rate_pct,
                     f'Отписки {value:.2f}% при допустимом пороге {settings.unsubscribe_rate_pct:.2f}%.', 'unsubscribe_rate')
                check(RULES['unsubscribe'], 'Сигнал')
            else:
                check(RULES['unsubscribe'], 'Отклонения нет')
    columns = ['id','project','campaign_key','campaign_id','campaign_name','date','rule','type','severity','value','baseline','metric','explanation','recommendation']
    return pd.DataFrame(signals, columns=columns), pd.DataFrame(checks, columns=['Рассылка','Дата','Проверка','Результат'])
