from pathlib import Path

from streamlit.testing.v1 import AppTest

APP=Path(__file__).parents[1]/'app.py'


def test_all_pages_render_and_demo_switch():
    app=AppTest.from_file(str(APP),default_timeout=30).run()
    assert not app.exception
    assert app.metric[1].value=='4'
    for page in ['Сигналы','Данные','Правила','О проекте','Обзор']:
        app.sidebar.radio[0].set_value(page).run()
        assert not app.exception, page
    app.sidebar.button[1].click().run()
    assert not app.exception and app.metric[1].value=='0'


def test_status_saved_and_rule_change():
    app=AppTest.from_file(str(APP),default_timeout=30).run()
    app.sidebar.radio[0].set_value('Сигналы').run()
    assert not app.exception
    app.selectbox[-1].set_value('Проверен')
    app.text_area[0].set_value('Тест проверки')
    next(b for b in app.button if b.label=='Сохранить результат').click().run()
    assert not app.exception
    assert 'Проверен' in app.dataframe[0].value['Статус'].tolist()
    app.sidebar.radio[0].set_value('Обзор').run()
    assert app.metric[2].value=='3'
