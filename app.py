"""Streamlit-интерфейс. Запуск: streamlit run app.py."""
from __future__ import annotations

import os
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.analysis import RULES, Settings, analyze, metrics
from core.demo import demo, raw_demo
from core.imports import ALIASES, REQUIRED, csv_bytes, read_csv_bytes, suggest_mapping, validate
from core.storage import STATUSES, attach_reviews, connect, save_review

st.set_page_config(page_title='CRM-контроль · Mindbox', page_icon='📊', layout='wide')
TODAY = datetime.now(ZoneInfo('Europe/Moscow')).date()
ROOT = Path(__file__).parent

st.markdown('''<style>
@import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;600;700&display=swap');
html,body,.stApp,.stApp p,.stApp label,.stApp input,.stApp button {font-family:Roboto,Arial,sans-serif;}
.stApp {background:#fff;color:#30343b;}
.block-container {padding-top:3.8rem;max-width:1600px;padding-bottom:3rem;}
h1 {font-size:1.95rem!important;letter-spacing:-.45px;font-weight:500!important;color:#30343b!important;}
h2 {font-size:1.4rem!important;font-weight:500!important;}
h3 {font-size:1.05rem!important;font-weight:500!important;color:#30343b!important;}
[data-testid="stSidebar"] {background:#fff;border-right:1px solid #dce3e7;min-width:326px;max-width:326px;}
[data-testid="stSidebar"]::before {content:"";position:absolute;left:0;top:0;bottom:0;width:52px;background:#282b31;}
[data-testid="stSidebar"]::after {content:"m";position:absolute;left:9px;top:28px;width:34px;height:34px;border-radius:50%;background:#009b77;color:white;text-align:center;font-size:28px;font-weight:600;line-height:33px;}
[data-testid="stSidebarContent"] {padding-left:52px;}
[data-testid="stSidebarContent"] > div:last-child {padding-top:1.5rem;}
[data-testid="stSidebar"] [data-testid="stRadio"] label {width:100%!important;box-sizing:border-box;}
[data-testid="stSidebar"] [data-testid="stDateInput"] input {font-size:13px;}
[data-testid="stSidebarUserContent"] {padding:1.75rem 1rem 1rem;}
[data-testid="stSidebar"] p,[data-testid="stSidebar"] label {color:#64727c;}
[data-testid="stSidebar"] hr {border-color:#e5e9ec;margin:1.3rem 0;}
[data-testid="stSidebar"] [data-testid="stRadio"] label {padding:9px 12px;border-radius:5px;margin:0 0 3px;transition:background .15s;}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {background:#f4f7f8;}
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {background:#eaf8f1;}
[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) p {color:#168565;font-weight:500;}
[data-testid="stSidebar"] [data-testid="stRadio"] label > div:first-child {display:none;}
[data-testid="stSidebar"] [data-testid="stRadio"] label p {font-size:15px;}
[data-testid="stSidebar"] button p {color:#45535b;}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {font-size:12px;line-height:1.5;}
[data-testid="stMetric"] {background:#fff;border:1px solid #dce3e7;border-bottom:3px solid #009b77;border-radius:5px;padding:18px 20px;}
[data-testid="stMetricLabel"] p {font-size:14px;color:#71808a;}
[data-testid="stMetricValue"] {font-size:2rem;font-weight:400;color:#30343b;}
[data-testid="stDataFrame"] {border:1px solid #dce3e7;border-radius:5px;}
[data-baseweb="select"] > div,[data-baseweb="input"],[data-baseweb="textarea"] {background:#fff!important;border-color:#c9d4dc!important;border-radius:5px!important;}
[data-testid="stDateInput"] > div {background:white;border:1px solid #c9d4dc;border-radius:5px;}
[data-testid="stCaptionContainer"] p {color:#7c8992;}
.eyebrow {font-size:13px;font-weight:400;letter-spacing:0;color:#84929a;margin-bottom:12px;}
.brand {font-size:25px;font-weight:600;letter-spacing:-.8px;color:#30343b;margin-bottom:4px;}
.brand-note {font-size:12px;color:#829097;margin-bottom:24px;line-height:1.5;}
.subtle {color:#74818b;font-size:14px;line-height:1.6;margin-top:-6px;margin-bottom:22px;}
.demo-banner {font-size:13px;color:#6e7167;background:#faf9f3;border:1px solid #eeeadc;border-radius:5px;padding:12px 16px;margin:0 0 20px;line-height:1.5;}
.demo-banner strong {font-weight:500;color:#575d55;margin-right:8px;}
.stButton button,.stDownloadButton button,.stLinkButton a {border-radius:5px;font-weight:400;border-color:#c9d4dc;min-height:38px;}
.stButton button[kind="primary"],button[data-testid="stBaseButton-primary"] {background:#009b77;border-color:#009b77;color:#fff;}
.stButton button:hover,.stDownloadButton button:hover {border-color:#009b77;color:#008465;}
div[data-testid="stVerticalBlockBorderWrapper"] {border-radius:5px;}
[data-testid="stForm"] {border-color:#dce3e7!important;border-radius:5px!important;background:#fafbfc;}
.stTabs [data-baseweb="tab"] {font-size:14px;}
footer {visibility:hidden;}
@media(max-width:900px) { [data-testid="stSidebar"] {min-width:260px;max-width:260px;} .block-container {padding:1.4rem 1rem;} h1 {font-size:1.6rem!important;} }
</style>''', unsafe_allow_html=True)


def set_data(data, project, mode, truth=None):
    st.session_state.data = data
    st.session_state.project = project
    st.session_state.mode = mode
    st.session_state.truth = truth
    st.session_state.version = st.session_state.get('version', 0) + 1
    st.session_state.expected = data['campaign_key'].unique().tolist() if mode.startswith('demo') else []
    for key in ('period', 'expected_select', 'active_signal', 'signal_status', 'status_filter', 'campaign_filter', 'type_filter'):
        st.session_state.pop(key, None)
    st.session_state.pop('analysis_cache', None)


if 'db' not in st.session_state:
    # Указывать CRM_DB_PATH можно только для локального однопользовательского запуска.
    st.session_state.db = connect(os.environ.get('CRM_DB_PATH', ':memory:'))
if 'data' not in st.session_state:
    data, truth = demo(TODAY)
    set_data(data, 'Учебный магазин', 'demo-problems', truth)

data = st.session_state.data
db = st.session_state.db

with st.sidebar:
    st.markdown('<div class="brand">mindbox</div><div class="brand-note">CRM-контроль<br>Аналитика рассылок</div>', unsafe_allow_html=True)
    page = st.radio('Рабочее пространство', ['Обзор', 'Сигналы', 'Данные', 'Правила', 'О проекте'], label_visibility='collapsed')
    st.divider()
    st.caption('ПРОЕКТ')
    st.write(st.session_state.project)
    if st.session_state.mode.startswith('demo'):
        st.caption('Демонстрация · синтетические данные')
    else:
        st.caption('Пользовательская загрузка · CSV')
    available_end = min(TODAY - timedelta(days=1), data['date'].max())
    default_start = max(data['date'].min(), available_end - timedelta(days=6))
    period = st.date_input('Период проверки', value=(default_start, available_end),
                           min_value=data['date'].min(), max_value=max(TODAY, data['date'].max()),
                           format='DD.MM.YYYY', key='period')
    st.caption('История до начала периода тоже участвует в сравнении.')
    st.divider()
    if st.button('Демо с отклонениями', width='stretch'):
        d, truth = demo(TODAY)
        set_data(d, 'Учебный магазин', 'demo-problems', truth)
        st.rerun()
    if st.button('Демо без отклонений', width='stretch'):
        d, truth = demo(TODAY, anomalies=False)
        set_data(d, 'Учебный магазин', 'demo-normal', truth)
        st.rerun()
    st.caption('Данные и комментарии хранятся в вашей текущей сессии. Скачайте результаты перед закрытием.')

settings = st.session_state.get('settings', Settings())
if len(period) != 2:
    st.info('Выберите начало и конец периода проверки.')
    st.stop()
start, end = period
if (end-start).days > 90:
    st.warning('Выберите период проверки не более 91 дня.')
    st.stop()
project_key = st.session_state.project + ('::demo' if st.session_state.mode.startswith('demo') else '::upload')
config_key = (st.session_state.version, tuple(asdict(settings).values()), start, end,
              tuple(sorted(st.session_state.expected)), st.session_state.get('complete_period', False), project_key)
cache = st.session_state.get('analysis_cache')
if cache is None or cache[0] != config_key:
    alerts, checks = analyze(data, settings, TODAY, start, end, st.session_state.expected,
                             st.session_state.get('complete_period', False), project_key)
    st.session_state.analysis_cache = (config_key, alerts, checks)
else:
    _, alerts, checks = cache
signals = attach_reviews(db, alerts)
counts = metrics(data)


def header(title, subtitle):
    st.markdown('<div class="eyebrow">Аналитика / Рассылки / Контроль отклонений</div>', unsafe_allow_html=True)
    st.title(title)
    st.markdown(f'<div class="subtle">{subtitle}</div>', unsafe_allow_html=True)
    if st.session_state.mode.startswith('demo'):
        st.markdown('<div class="demo-banner"><strong>Демонстрационные данные</strong> Синтетические рассылки и показатели. Подключение к клиентскому проекту Mindbox отсутствует.</div>', unsafe_allow_html=True)


def display_signals(frame):
    labels = {'date':'Дата', 'campaign_name':'Рассылка', 'campaign_id':'ID', 'type':'Сигнал',
              'severity':'Приоритет', 'status':'Статус', 'explanation':'Что изменилось', 'comment':'Комментарий'}
    return frame[list(labels)].rename(columns=labels)


def graph(key, metric='delivery_rate', signal=None):
    series = counts[counts['campaign_key'] == key].sort_values('date')
    names = {'sent':'Отправлено сообщений','delivery_rate':'Доставляемость, %',
             'click_rate':'Кликабельность, %','unsubscribe_rate':'Отписки, %'}
    baseline=[]
    for day in series['date']:
        hist=series[(series['date'] < day) & (series['date'] >= day-timedelta(days=settings.history_days))]
        denominator = 'sent' if metric in ('sent','delivery_rate') else 'delivered'
        hist=hist[hist[denominator] >= settings.min_volume]
        baseline.append(float(hist[metric].median()) if len(hist)>=settings.min_history else None)
    fig=go.Figure()
    fig.add_trace(go.Scatter(x=series['date'], y=series[metric], name='Фактическое значение',
                             line=dict(color='#6554bd',width=2),mode='lines+markers',marker=dict(size=5)))
    if metric == 'unsubscribe_rate':
        fig.add_hline(y=settings.unsubscribe_rate_pct,line_dash='dash',line_color='#b77941',annotation_text='Порог отписок')
    else:
        fig.add_trace(go.Scatter(x=series['date'],y=baseline,name='Медиана предыдущих дней',
                                 line=dict(color='#b9c7cd',width=1.5,dash='dash'),connectgaps=False))
    if signal is not None:
        fig.add_trace(go.Scatter(x=[signal['date']],y=[signal['value']],mode='markers',
                                marker=dict(color='#d9684b',size=13),name='Сигнал'))
    fig.update_layout(height=330, margin=dict(l=10,r=20,t=25,b=10), paper_bgcolor='rgba(0,0,0,0)',
                      plot_bgcolor='rgba(0,0,0,0)',font=dict(family='Roboto, Arial, sans-serif',color='#6d7b85',size=12),
                      legend=dict(orientation='h',y=1.16,x=0),yaxis_title=names[metric],xaxis_title=None,
                      hovermode='x unified')
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor='#e4eaee',griddash='dot',rangemode='tozero')
    st.plotly_chart(fig, width='stretch')


if page == 'Обзор':
    header('Рассылки под контролем', 'Список отклонений, с которых стоит начать регулярную проверку CRM-коммуникаций.')
    a,b,c,d=st.columns(4)
    a.metric('Рассылки', data['campaign_key'].nunique())
    b.metric('Сигналы', len(signals))
    c.metric('Открытые', int((signals['status']!='Проверен').sum()))
    d.metric('Рассылки с отклонениями', signals['campaign_key'].nunique())
    st.caption(f'Проверка: {start:%d.%m.%Y} — {end:%d.%m.%Y}. Реакции учитываются с возраста {settings.reaction_age_days} дн. Часовой пояс: Москва.')
    left,right=st.columns([2,1],gap='large')
    with left:
        st.subheader('Приоритет проверки')
        if signals.empty:
            st.success('Отклонений по выбранным правилам не найдено.')
            st.caption('Это не гарантирует исправность всех рассылок. Посмотрите результаты проверок ниже.')
        else:
            ranking=signals.assign(_rank=signals['severity'].map({'Высокий':0,'Средний':1})).sort_values(['_rank','date'],ascending=[True,False])
            st.dataframe(display_signals(ranking).drop(columns=['ID','Комментарий','Что изменилось']),hide_index=True,width='stretch')
            st.caption('Подробности, график и фиксация результата находятся в разделе «Сигналы».')
    with right:
        st.subheader('Результат проверок')
        summary=checks['Результат'].value_counts().rename_axis('Результат').reset_index(name='Проверок')
        st.dataframe(summary,hide_index=True,width='stretch')
    st.subheader('Динамика выбранной рассылки')
    keys=data['campaign_key'].unique().tolist()
    labels={k:f"{g.iloc[-1]['campaign_name']} · {g.iloc[-1]['campaign_id']}" for k,g in data.groupby('campaign_key')}
    ca,cb=st.columns([2,1])
    key=ca.selectbox('Рассылка',keys,format_func=labels.get,key='overview_campaign')
    metric=cb.selectbox('Показатель',['delivery_rate','click_rate','unsubscribe_rate','sent'],
                        format_func=lambda x:{'delivery_rate':'Доставляемость','click_rate':'Кликабельность','unsubscribe_rate':'Отписки','sent':'Отправки'}[x])
    graph(key,metric)
    with st.expander('Подробный протокол проверок'):
        st.dataframe(checks,hide_index=True,width='stretch')
        st.download_button('Скачать протокол',csv_bytes(checks),'checks.csv','text/csv')
    if st.session_state.truth is not None:
        truth=st.session_state.truth
        expected={(r.campaign_id,r.date,r.rule) for r in truth.itertuples() if start<=r.date<=end}
        found={(r.campaign_id,r.date,r.rule) for r in signals.itertuples()}
        with st.expander('Проверка на известных демослучаях'):
            st.write(f'Заложено отклонений в выбранном периоде: {len(expected)}. Найдено: {len(found & expected)}. Лишних сигналов: {len(found - expected)}.')
            st.caption('Проверка учебного набора. Результат не является оценкой качества на реальных клиентских данных.')
            st.dataframe(truth,hide_index=True,width='stretch')

elif page == 'Сигналы':
    header('Очередь сигналов', 'Проверьте отклонение, разберитесь с причиной в Mindbox и зафиксируйте результат.')
    a,b,c=st.columns(3)
    selected_types=a.multiselect('Тип сигнала',list(RULES.values()),key='type_filter',placeholder='Все типы')
    selected_status=b.multiselect('Статус',list(STATUSES),key='status_filter',placeholder='Все статусы')
    selected_campaign=c.multiselect('Рассылка',sorted(signals['campaign_name'].unique()),key='campaign_filter',placeholder='Все рассылки')
    filtered=signals.copy()
    for col,selected in [('type',selected_types),('status',selected_status),('campaign_name',selected_campaign)]:
        if selected:
            filtered=filtered[filtered[col].isin(selected)]
    st.caption(f'Показано {len(filtered)} из {len(signals)} сигналов')
    if filtered.empty:
        st.info('Нет сигналов для выбранных фильтров и периода.')
    else:
        st.dataframe(display_signals(filtered),hide_index=True,width='stretch')
        st.download_button('Скачать выбранные сигналы',csv_bytes(display_signals(filtered)),'crm-signals.csv','text/csv')
        by_id=filtered.set_index('id')
        sid=st.selectbox('Открыть сигнал',filtered['id'].tolist(),
                         format_func=lambda i:f"{by_id.loc[i,'date']:%d.%m} · {by_id.loc[i,'campaign_name']} · {by_id.loc[i,'type']}")
        record=by_id.loc[sid]
        left,right=st.columns([1.6,1],gap='large')
        with left:
            st.subheader(record['type'])
            st.write(record['explanation'])
            graph(record['campaign_key'],record['metric'],record)
        with right:
            st.subheader('Что проверить')
            st.write(record['recommendation'])
            st.caption('Подсказка не устанавливает причину отклонения.')
            with st.form(f'review_{sid}'):
                status=st.selectbox('Результат проверки',STATUSES,index=STATUSES.index(record['status']))
                comment=st.text_area('Комментарий',value=record['comment'],max_chars=2000,
                                      placeholder='Что проверили и что решили сделать')
                if st.form_submit_button('Сохранить результат',type='primary',width='stretch'):
                    save_review(db,sid,status,comment)
                    st.rerun()

elif page == 'Данные':
    header('Данные из Mindbox', 'Дневная статистика автоматических email-рассылок. Поддерживается сопоставление колонок выгрузки.')
    st.subheader('Загрузка CSV')
    st.write('В Mindbox откройте «Аналитика → Рассылки», выберите динамику по дням и нужные автоматические email-рассылки. Выгрузите CSV с детализацией по рассылкам, вариантам и брендам, без строк итогов.')
    st.caption('Для сравнения нужно минимум 7 подходящих дней истории, рекомендуем загрузить 35 дней. Формат реальной выгрузки может различаться — проверьте сопоставление колонок.')
    upload=st.file_uploader('CSV до 10 МБ',type=['csv'])
    if upload:
        try:
            raw=read_csv_bytes(upload.getvalue())
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.dataframe(raw.head(8),hide_index=True,width='stretch')
            suggested=suggest_mapping(raw.columns)
            labels={'date':'Дата дня','campaign_id':'ID рассылки','campaign_name':'Название рассылки',
                    'sent':'Отправлено, шт.','delivered':'Доставлено, шт.','clicked':'Сообщений с кликом, шт.',
                    'unsubscribed':'Сообщений с отпиской, шт.','variant':'Вариант','brand':'Бренд','channel':'Канал','category':'Категория'}
            mapping={}
            with st.expander('Сопоставление колонок',expanded=True):
                columns=st.columns(3)
                for i,field in enumerate(ALIASES):
                    options=['— Не выбрано —',*raw.columns]
                    chosen=columns[i%3].selectbox(labels[field]+(' *' if field in REQUIRED else ''),options,
                          index=options.index(suggested[field]) if field in suggested else 0,
                          key=f'map_{upload.file_id}_{field}')
                    if chosen != options[0]:
                        mapping[field]=chosen
            project=st.text_input('Название проекта',value='Мой CRM-проект',max_chars=100)
            daily=st.checkbox('Данные сгруппированы по дням и содержат только автоматические email-рассылки')
            if st.button('Проверить и загрузить',type='primary'):
                if not daily or not project.strip():
                    st.error('Укажите проект и подтвердите дневную статистику автоматических email-рассылок.')
                else:
                    with st.spinner('Проверяем данные…'):
                        validation=validate(raw,mapping,TODAY)
                    if not validation.ok:
                        st.error('Данные не загружены. Исправьте ошибки и повторите загрузку.')
                        st.dataframe(validation.issues,hide_index=True,width='stretch')
                        st.session_state.import_issues=validation.issues
                    else:
                        set_data(validation.data,project.strip(),'upload')
                        st.session_state.pop('import_issues',None)
                        st.session_state.complete_period=False
                        st.rerun()
            if 'import_issues' in st.session_state:
                st.download_button('Скачать последний протокол ошибок',csv_bytes(st.session_state.import_issues),'import-errors.csv','text/csv')
    st.divider()
    st.subheader('Текущий набор')
    a,b,c=st.columns(3)
    a.metric('Строк',len(data));b.metric('Рассылок / вариантов',data['campaign_key'].nunique())
    c.metric('Дней в файле',data['date'].nunique())
    st.caption(f"Диапазон: {data['date'].min():%d.%m.%Y} — {data['date'].max():%d.%m.%Y}. Сырые лишние колонки не сохраняются.")
    st.dataframe(data[list(REQUIRED)+['variant','brand']],hide_index=True,width='stretch',height=320)
    a,b=st.columns(2)
    a.download_button('Скачать текущие данные',csv_bytes(data[list(REQUIRED)+['variant','brand']]),'crm-data.csv','text/csv',width='stretch')
    b.download_button('Скачать образец CSV',csv_bytes(raw_demo(TODAY)),'demo-mindbox.csv','text/csv',width='stretch')
    st.link_button('Документация экспорта Mindbox','https://developers.mindbox.ru/docs/export-api-reports')

elif page == 'Правила':
    header('Правила контроля', 'Настраиваемые пороги учебной модели. Они не являются нормативами Mindbox.')
    with st.form('settings_form'):
        a,b=st.columns(2)
        hd=a.number_input('Окно истории, дней',7,90,settings.history_days)
        mh=b.number_input('Минимум дней истории',1,90,settings.min_history)
        mv=a.number_input('Минимум сообщений в день',1,1_000_000,settings.min_volume)
        age=b.number_input('Возраст данных для кликов и отписок, дней',1,30,settings.reaction_age_days)
        dp=a.number_input('Снижение доставляемости, п.п.',0.1,100.0,float(settings.delivery_drop_pp),step=.5)
        cp=b.number_input('Снижение кликабельности от медианы, %',0.1,100.0,float(settings.click_drop_pct),step=5.)
        up=a.number_input('Максимальная доля отписок, %',0.0,100.0,float(settings.unsubscribe_rate_pct),step=.1)
        campaigns={k:f"{g.iloc[-1]['campaign_name']} · ID {g.iloc[-1]['campaign_id']} · вариант {g.iloc[-1]['variant']}"+(f" · {g.iloc[-1]['brand']}" if g.iloc[-1]['brand'] else '') for k,g in data.groupby('campaign_key')}
        daily=st.multiselect('Ожидаются ежедневные отправки',list(campaigns),default=st.session_state.expected,
                              format_func=campaigns.get,key='expected_select')
        complete=st.checkbox('Подтверждаю полноту файла: пропущенные строки выбранных ежедневных рассылок означают 0 отправок',
                              value=st.session_state.get('complete_period',False))
        st.caption('По умолчанию отсутствие строки означает отсутствие данных. Подтверждение действует только внутри диапазона файла и после первого наблюдения рассылки.')
        if st.form_submit_button('Применить правила',type='primary'):
            try:
                updated=Settings(int(hd),int(mh),int(mv),dp,cp,up,int(age))
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.session_state.settings=updated
                st.session_state.expected=daily
                st.session_state.complete_period=complete
                st.rerun()
    with st.expander('Как считаются показатели',expanded=True):
        st.markdown('''**Доставляемость** = доставлено / отправлено × 100%.  
**Кликабельность** = сообщений с кликом / доставлено × 100%.  
**Отписки** = сообщений с отпиской / доставлено × 100%.

Медиана считается по предыдущим подходящим дням в окне истории, без текущего дня. Варианты и бренды анализируются отдельно. Для нулевых знаменателей проценты не рассчитываются. Рост отписок проверяется по абсолютному порогу и не требует истории.''')

else:
    header('О проекте', 'Учебное приложение для CRM-маркетолога и CSM. Независимый прототип, не официальный продукт Mindbox.')
    st.subheader('Бизнес-проблема')
    st.write('Ручная проверка множества автоматических рассылок занимает время. CRM-контроль выделяет отклонения, объясняет их и помогает фиксировать результаты проверки.')
    st.subheader('Что уже работает')
    st.write('CSV-импорт с проверкой, четыре типа сигналов, история метрик, статусы и комментарии, выгрузка результатов, два демонабора. Данные не отправляются в Mindbox.')
    st.subheader('Ограничения')
    st.write('Сигнал не доказывает техническую неисправность. Сезонность, изменения аудитории и задержка реакций могут влиять на метрики. Данные поступают только при загрузке CSV. Непрерывного мониторинга и авторизации нет.')
    st.write('По умолчанию SQLite работает в памяти отдельной браузерной сессии. После закрытия или перезапуска сессии импорт и комментарии могут исчезнуть. Для локальной работы можно включить постоянную базу результатов; для переноса используйте выгрузки.')
    st.subheader('Сценарий защиты')
    st.markdown('''1. Откройте демо с отклонениями: в нём четыре известных случая.
2. Покажите очередь сигналов и график одного отклонения.
3. Сохраните статус и комментарий, скачайте отчёт.
4. Загрузите скачанный CSV с тем же проектом и убедитесь, что результат проверки сохранён.
5. Откройте нормальный демонабор и сравните результат.
6. Покажите обработку файла с ошибками и настройки порогов.''')
    st.subheader('Документы и источники')
    st.link_button('Определения метрик Mindbox','https://help.mindbox.ru/docs/mailings-dashboard')
    st.link_button('Формат полей экспортов Mindbox','https://developers.mindbox.ru/docs/export-api-reports')
    st.caption('Стек: Python · Streamlit · pandas · Plotly · SQLite. Фактическая экономия времени на реальном проекте не измерялась.')
