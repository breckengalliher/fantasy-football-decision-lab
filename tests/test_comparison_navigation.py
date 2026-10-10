"""Reproduce Streamlit widget cleanup during a real navigation round trip."""
import ast
from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_position_survives_an_unrendered_page_and_restores_its_comparison():
    source = Path('dashboard/app.py').read_text(encoding='utf-8')
    function = next(node for node in ast.parse(source).body
                    if isinstance(node, ast.FunctionDef) and node.name == '_comparison_position')
    script = 'import streamlit as st\n' + ast.unparse(function) + '''
page = st.radio('View', ['Decision Room', 'Command Center'])
if page == 'Decision Room':
    position = _comparison_position('WR')
    if 'smart_search_selected_QB' not in st.session_state:
        st.session_state['smart_search_selected_QB'] = ['Stafford', 'Goff']
    st.write(st.session_state.get('smart_search_selected_' + position, []))
'''
    app = AppTest.from_string(script).run()
    app.segmented_control[0].set_value('QB').run()
    assert not app.exception
    app.radio[0].set_value('Command Center').run()
    app.radio[0].set_value('Decision Room').run()
    assert not app.exception
    assert app.segmented_control[0].value == 'QB'
    assert app.session_state['smart_search_selected_QB'] == ['Stafford', 'Goff']


def test_latest_scoring_choice_survives_navigation_widget_cleanup():
    tree = ast.parse(Path('dashboard/app.py').read_text(encoding='utf-8'))
    container = next(node for node in ast.walk(tree) if isinstance(node, ast.With)
                     and any(isinstance(child, ast.Assign)
                             and any(isinstance(target, ast.Name) and target.id == 'qb_td_label'
                                     for target in child.targets) for child in node.body))
    start = next(i for i, node in enumerate(container.body) if isinstance(node, ast.Assign)
                 and any(isinstance(target, ast.Name) and target.id == 'qb_td_label'
                         for target in node.targets))
    scoring = ast.unparse(ast.Module(body=container.body[start:], type_ignores=[]))
    script = '''import streamlit as st
page = st.radio('View', ['Compare', 'Command', 'Trends'])
if page != 'Command':
    shared_qb_index = 1 if str(st.query_params.get('qb', '4')) == '6' else 0
''' + '\n'.join('    ' + line for line in scoring.splitlines()) + '''
st.write('Navigation scoring: ' + str(st.query_params.get('qb', '4')))
'''
    app = AppTest.from_string(script)
    app.query_params['qb'] = '6'
    app.run()
    app.radio[1].set_value('4 points').run()
    assert app.query_params['qb'] == '4'
    app.radio[0].set_value('Command').run()
    app.radio[0].set_value('Trends').run()
    assert not app.exception
    assert app.radio[1].value == '4 points'
    app.radio[1].set_value('6 points').run()
    app.radio[0].set_value('Command').run()
    app.radio[0].set_value('Compare').run()
    assert not app.exception
    assert app.radio[1].value == '6 points'
    assert app.query_params['qb'] == '6'
