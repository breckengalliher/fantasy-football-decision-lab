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
