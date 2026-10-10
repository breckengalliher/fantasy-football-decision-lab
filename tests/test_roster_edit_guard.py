import copy
import unittest
import ast
from pathlib import Path
from types import SimpleNamespace
from dashboard.roster_edit_guard import edit_is_current


class RosterEditGuardTests(unittest.TestCase):
    def setUp(self):
        self.roster = [dict(id='qb',slot_type='QB',slot_order=0,is_starter=True,
            roster_assignments=[dict(id='a',player_id='allen',updated_at='v1')]),
            dict(id='bench',slot_type='BENCH',slot_order=0,is_starter=False,
            roster_assignments=[dict(id='b',player_id='stafford',updated_at='v1')])]
        self.state = {}
        self.assertTrue(edit_is_current(self.state, 'editor', self.roster))

    def test_stale_confirmation_cannot_reverse_other_tab_swap(self):
        changed = copy.deepcopy(self.roster)
        changed[0]['roster_assignments'], changed[1]['roster_assignments'] = changed[1]['roster_assignments'], changed[0]['roster_assignments']
        self.assertFalse(edit_is_current(self.state, 'editor', changed))

    def test_changed_timestamp_rejects_return_to_same_slot(self):
        changed = copy.deepcopy(self.roster)
        changed[0]['roster_assignments'][0]['updated_at'] = 'v2'
        self.assertFalse(edit_is_current(self.state, 'editor', changed))

    def test_new_occupant_rejects_empty_destination_confirmation(self):
        empty = copy.deepcopy(self.roster)
        empty[1]['roster_assignments'] = []
        state = {}
        self.assertTrue(edit_is_current(state, 'editor', empty))
        self.assertFalse(edit_is_current(state, 'editor', self.roster))

    def test_reordering_and_unchanged_rerun_preserve_confirmation(self):
        self.assertTrue(edit_is_current(self.state, 'editor', list(reversed(self.roster))))

    def test_reopening_explicitly_accepts_new_revision(self):
        changed = copy.deepcopy(self.roster)
        changed[0]['roster_assignments'][0]['updated_at'] = 'v2'
        self.state.pop('editor')
        self.assertTrue(edit_is_current(self.state, 'editor', changed))

    def render_manager(self, changed, click):
        # Execute the actual UI function without importing unavailable UI packages.
        source = Path(__file__).parents[1]/'dashboard/command_center_v2.py'
        function = next(n for n in ast.parse(source.read_text()).body if isinstance(n, ast.FunctionDef) and n.name=='_manage_player')
        calls = []
        class Rerun(Exception):
            pass
        state = self.state
        column = SimpleNamespace(button=lambda *a, **k:False)
        ui = SimpleNamespace(session_state=state,warning=lambda text:calls.append(('warning',text)),
            caption=lambda *a:None,columns=lambda *a:[column,column],checkbox=lambda *a,**k:False,
            selectbox=lambda label,options,**k:options[0],button=lambda *a,**k:click,
            toast=lambda text:calls.append(('toast',text)),
            rerun=lambda:(_ for _ in ()).throw(Rerun()))
        repo = SimpleNamespace(swap_players=lambda *a:calls.append(('swap',a)))
        namespace = dict(st=ui,edit_is_current=edit_is_current,_player_locked=lambda p:False,
            _ordered_slots=lambda r:r,_assignment=lambda s:(s['roster_assignments'] or [None])[0],
            ELIGIBLE={'QB':{'QB'},'BENCH':{'QB'}},SupabaseAPIError=RuntimeError)
        module = ast.Module(body=[ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0),function],type_ignores=[])
        exec(compile(ast.fix_missing_locations(module),str(source),'exec'),namespace)
        lookup = {'allen':{'position':'QB'},'stafford':{'position':'QB'}}
        source_slot = next(s for s in changed if s['roster_assignments'][0]['id']=='a')
        try:
            namespace['_manage_player']({'id':'team'},changed,source_slot,source_slot['roster_assignments'][0],repo,None,lookup)
        except Rerun:
            pass
        return calls

    def test_actual_manager_stale_submit_never_calls_repository(self):
        self.state = {}
        self.render_manager(self.roster,False)
        changed = copy.deepcopy(self.roster)
        changed[0]['roster_assignments'],changed[1]['roster_assignments'] = changed[1]['roster_assignments'],changed[0]['roster_assignments']
        calls = self.render_manager(changed,True)
        self.assertEqual([c[0] for c in calls],['warning'])
        self.assertFalse(self.state['cc_manage_a'])

    def test_actual_manager_current_submit_keeps_database_preconditions(self):
        self.state = {}
        self.render_manager(self.roster,False)
        calls = self.render_manager(self.roster,True)
        self.assertEqual([c[0] for c in calls],['swap','toast'])
        self.assertEqual(calls[1][1], 'Lineup saved')
        self.assertFalse(self.state['cc_manage_a'])
        self.assertEqual(calls[0][1][0]['slot_id'],'qb')
        self.assertEqual(calls[0][1][1]['slot_id'],'bench')
        self.assertNotIn('cc_edit_revision_team_a', self.state)


if __name__ == '__main__':
    unittest.main()
