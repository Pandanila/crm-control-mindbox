from datetime import date, timedelta

import pandas as pd
import pytest

from core.analysis import Settings, analyze, metrics
from core.demo import demo, raw_demo
from core.imports import REQUIRED, csv_bytes, read_csv_bytes, suggest_mapping, validate
from core.storage import attach_reviews, connect, save_review

TODAY = date(2026, 10, 30)


def run(data, settings=None, **kwargs):
    return analyze(data, settings or Settings(), TODAY, TODAY-timedelta(days=7),
                   TODAY-timedelta(days=1), expected_daily=data.campaign_key.unique(), **kwargs)


def test_demo_detects_exactly_four_known_cases():
    data, truth = demo(TODAY)
    signals, _ = run(data)
    assert {(r.campaign_id,r.date,r.rule) for r in signals.itertuples()} == {
        (r.campaign_id,r.date,r.rule) for r in truth.itertuples()}
    assert signals.id.is_unique


def test_normal_data_has_no_alerts():
    signals, _ = run(demo(TODAY, False)[0])
    assert signals.empty


def test_missing_row_is_not_zero_without_explicit_confirmation():
    data, _ = demo(TODAY)
    day = TODAY-timedelta(days=3)
    data = data[~((data.campaign_id=='welcome') & (data.date==day))]
    signals, checks = run(data)
    assert 'no_sends' not in signals.rule.tolist()
    assert checks['Результат'].str.contains('нулевые отправки не подтверждены').any()
    signals, _ = run(data, complete_period=True)
    assert 'no_sends' in signals.rule.tolist()


def test_stopped_campaign_tail_only_inside_confirmed_file_range():
    data, _ = demo(TODAY, False)
    key = data[data.campaign_id=='welcome'].iloc[0].campaign_key
    data=data[~((data.campaign_key==key) & (data.date>=TODAY-timedelta(days=2)))]
    signals, _ = run(data, complete_period=True)
    assert len(signals[signals.rule=='no_sends'])==2


def test_small_volume_and_history_are_not_anomalies():
    data, _ = demo(TODAY)
    assert run(data, Settings(min_volume=100_000))[0].empty
    # Отписки проверяются абсолютным порогом даже без истории.
    recent=data[data.date>=TODAY-timedelta(days=3)]
    signals,_=run(recent)
    assert signals.rule.tolist()==['unsubscribe']


def test_recent_reactions_excluded_but_delivery_checked():
    data, _ = demo(TODAY)
    signals,_=run(data, Settings(reaction_age_days=4))
    assert set(signals.rule)=={'delivery','no_sends'}


def test_baseline_does_not_use_future_data():
    data,_=demo(TODAY, False)
    target=TODAY-timedelta(days=3)
    data.loc[(data.campaign_id=='cart') & (data.date>target),'delivered']=0
    signals,_=analyze(data,Settings(),TODAY,target,target)
    assert signals.empty


def test_zero_denominators_do_not_become_percentages():
    data,_=demo(TODAY)
    row=metrics(data).query("sent == 0").iloc[0]
    assert pd.isna(row.delivery_rate) and pd.isna(row.click_rate)


@pytest.mark.parametrize('field,value', [('sent','-1'),('sent','NaN'),('sent','1.5'),
    ('date','2026-99-01'),('campaign_id',''),('delivered','999999'),('clicked','999999'),
    ('unsubscribed','inf')])
def test_invalid_rows_block_entire_import(field,value):
    raw=raw_demo(TODAY).astype(str)
    raw.loc[0,field]=value
    result=validate(raw,suggest_mapping(raw.columns),TODAY)
    assert not result.ok and result.data.empty and not result.issues.empty


def test_duplicates_rejected_but_variants_separate():
    raw=raw_demo(TODAY).head(1).astype(str)
    duplicated=pd.concat([raw,raw],ignore_index=True)
    assert not validate(duplicated,suggest_mapping(duplicated.columns),TODAY).ok
    duplicated['ReportMailingVariantNum']=['1','2']
    result=validate(duplicated,suggest_mapping(duplicated.columns),TODAY)
    assert result.ok and result.data.campaign_key.nunique()==2


def test_csv_roundtrip_and_mindbox_headers():
    raw=raw_demo(TODAY)
    names=['ReportDate','ReportMailingId','ReportMessageName','ReportSent',
           'ReportDelivered','ReportClicked','ReportUnsubscribed']
    raw.columns=names
    parsed=read_csv_bytes(csv_bytes(raw))
    checked=validate(parsed,suggest_mapping(parsed.columns),TODAY)
    assert checked.ok and len(checked.data)==210


def test_decimal_comma_and_grouping():
    raw=raw_demo(TODAY).head(1).astype(str)
    raw.loc[0,'sent']='2 000,0'
    result=validate(raw,suggest_mapping(raw.columns),TODAY)
    assert result.ok and result.data.iloc[0].sent==2000


def test_future_day_and_unsupported_channel_rejected():
    raw=raw_demo(TODAY).head(1).astype(str)
    raw['date']=str(TODAY+timedelta(days=1))
    assert not validate(raw,suggest_mapping(raw.columns),TODAY).ok
    raw['date']=str(TODAY)
    raw['ReportChannel']='SMS'
    assert not validate(raw,suggest_mapping(raw.columns),TODAY).ok


def test_csv_formula_injection_escaped():
    decoded=csv_bytes(pd.DataFrame({'name':['=HYPERLINK("bad")','@SUM(1)','Normal']})).decode('utf-8-sig')
    assert "'=HYPERLINK" in decoded and "'@SUM" in decoded


def test_review_survives_reanalysis_and_is_session_isolated():
    data,_=demo(TODAY)
    signals,_=run(data)
    db=connect()
    save_review(db,signals.iloc[0].id,'Проверен','Согласовано')
    rerun,_=run(data)
    reviewed=attach_reviews(db,rerun)
    assert len(reviewed)==4 and reviewed.iloc[0].status=='Проверен'
    assert reviewed.iloc[0]['comment']=='Согласовано'
    assert (attach_reviews(connect(),rerun).status=='Новый').all()


def test_review_namespace_differs_by_project():
    data,_=demo(TODAY)
    a,_=run(data,project='A')
    b,_=run(data,project='B')
    assert not set(a.id)&set(b.id)


def test_disk_storage_survives_reconnect(tmp_path):
    path=str(tmp_path/'reviews.db')
    db=connect(path)
    save_review(db,'abc','В работе','Проверить ссылки')
    db.close()
    assert connect(path).execute('SELECT status FROM reviews').fetchone()[0]=='В работе'


def test_invalid_settings():
    with pytest.raises(ValueError):
        Settings(history_days=7,min_history=8)


def test_unfinished_day_not_analyzed():
    data,_=demo(TODAY)
    signals,checks=analyze(data,Settings(),TODAY,TODAY,TODAY)
    assert signals.empty and (checks['Результат']=='День не завершён').all()
