"""Воспроизводимые синтетические данные, без реальных клиентов Mindbox."""
from datetime import date, timedelta

import pandas as pd

from core.imports import REQUIRED, suggest_mapping, validate

CAMPAIGNS = [('welcome','Welcome после регистрации'), ('cart','Брошенная корзина'),
             ('repeat','Повторная покупка'), ('reactivation','Реактивация'),
             ('birthday','День рождения'), ('loyalty','Бонусы за покупку')]


def demo(today: date, anomalies=True) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows, truth = [], []
    incident = today - timedelta(days=3)
    for i, (cid, name) in enumerate(CAMPAIGNS):
        for offset in range(35, 0, -1):
            day = today - timedelta(days=offset)
            sent = 1000 + i*90 + ((offset*17+i*11) % 80)
            delivered = round(sent * .98)
            clicked, unsubscribed = round(delivered * .08), 2
            if anomalies and day == incident and i < 4:
                if i == 0:
                    sent = delivered = clicked = unsubscribed = 0
                elif i == 1:
                    delivered = round(sent*.80)
                    clicked = round(delivered*.08)
                elif i == 2:
                    clicked = round(delivered*.02)
                elif i == 3:
                    unsubscribed = round(delivered*.025)
                truth.append({'campaign_id': cid, 'date': day, 'rule': ['no_sends','delivery','click','unsubscribe'][i]})
            rows.append(dict(zip(REQUIRED, [day, cid, name, sent, delivered, clicked, unsubscribed])))
    raw = pd.DataFrame(rows)
    result = validate(raw.astype(str), suggest_mapping(raw.columns), today)
    return result.data, pd.DataFrame(truth, columns=['campaign_id','date','rule'])


def raw_demo(today, anomalies=True):
    data, _ = demo(today, anomalies)
    return data[list(REQUIRED)]
