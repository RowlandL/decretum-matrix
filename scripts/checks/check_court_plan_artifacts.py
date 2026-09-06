"""Debug regressions for real plans and independent department evidence."""
from pathlib import Path
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import copy
import json
import subprocess
from unittest.mock import patch
import unittest
import court_plan_artifacts as plans
from court_case_binding import plan_reference


def fixture():
    task = {'task_id': 'case-fixture', 'state': 'ThreeDepartments',
            'court_code': 'CCR-20260906-1-ABCD', 'charter_revision': 1, 'semantic_epoch': 1,
            'case_execution': {'authority': 'super', 'behavior': 'parallel'}, 'agents': {}}
    events = []
    producers = {}
    for role in ('zhongshu', 'menxia', 'shangshu'):
        agent_id = 'fixture-' + role
        task['agents'][agent_id] = {'task_id':task['task_id'], 'role': role, 'direct_superior': 'taizi',
            'preload_status': 'PASSED', 'office_execution_ready': True,
            'court_code': task['court_code'], 'charter_revision': 1, 'semantic_epoch':1}
        events.append({'action': 'agent_report', 'agent_role': role,
                       'task_id':task['task_id'], 'court_code': task['court_code'], 'semantic_epoch':1,
                       'agent_id': agent_id, 'evidence': 'report-' + role})
        producers[role] = {'kind': 'host_report', 'agent_id': agent_id, 'evidence': 'report-' + role}
    document = {'goal': 'Count public text files', 'non_goals': ['No external writes'],
                'steps': [{'id': 'count', 'role': 'gongbu', 'action': 'Count files'}],
                'acceptance': ['Count is reproducible'], 'write_set': ['result.json']}
    return task, document, producers, events


class PlanArtifactTests(unittest.TestCase):
    def test_runtime_epoch_is_compatible_when_old_revision_field_is_absent(self):
        task, doc, p, events = fixture()
        del task['agents'][p['zhongshu']['agent_id']]['charter_revision']
        del task['agents'][p['zhongshu']['agent_id']]['task_id']  # task-scoped container + exact report still bind it
        result = plans.submit_plan(task, doc, p['zhongshu'], events)
        self.assertEqual(result['zhongshu_plan']['charter_revision'], 1)
        self.assertNotIn('charter_revision', task['agents'][p['zhongshu']['agent_id']])

    def test_current_identity_and_report_version_are_required(self):
        for field,value in [('task_id','foreign'),('court_code','CCR-20260906-1-EEEE'),
                            ('charter_revision',2),('semantic_epoch',2),('semantic_epoch',True),
                            ('direct_superior','shangshu'),('role','menxia')]:
            task, doc, p, events = fixture()
            task['agents'][p['zhongshu']['agent_id']][field]=value
            with self.subTest(agent_field=field), self.assertRaises(ValueError):
                plans.submit_plan(task,doc,p['zhongshu'],events)
        for field,value in [('task_id','foreign'),('court_code','CCR-20260906-1-EEEE'),('semantic_epoch',2)]:
            task, doc, p, events = fixture();events[0][field]=value
            with self.subTest(event_field=field), self.assertRaises(ValueError):
                plans.submit_plan(task,doc,p['zhongshu'],events)
        task,doc,p,events=fixture();task['charter_revision']=task['semantic_epoch']=2
        with self.assertRaises(ValueError):plans.submit_plan(task,doc,p['zhongshu'],events)

    def test_capsule_cannot_stand_in_for_a_plan(self):
        task, _, p, events = fixture()
        before = copy.deepcopy(task)
        with self.assertRaises(ValueError):
            plans.submit_plan(task, {'schema': 'court.semantic.invariant_capsule.v1'}, p['zhongshu'], events)
        self.assertEqual(task, before)

    def test_role_and_actual_report_are_required(self):
        task, doc, p, events = fixture()
        for producer, observed in ((p['menxia'], events), (p['zhongshu'], [])):
            with self.assertRaises(ValueError):
                plans.submit_plan(task, doc, producer, observed)

    def test_three_departments_are_independent_and_bind_one_plan(self):
        task, doc, p, events = fixture()
        task = plans.submit_plan(task, doc, p['zhongshu'], events)
        plan_ref = plan_reference(task['zhongshu_plan'])
        with self.assertRaises(ValueError):
            plans.require_reviewed_plan(task)
        task = plans.record_review(task, 'menxia', 'approved', plan_ref, p['menxia'], events)
        with self.assertRaises(ValueError):
            plans.require_reviewed_plan(task)
        task = plans.record_review(task, 'shangshu', 'dispatchable', plan_ref, p['shangshu'], events)
        self.assertEqual(plans.require_reviewed_plan(task)['revision'], plan_ref['plan_revision'])
        for role, wrong in (('menxia', p['zhongshu']), ('shangshu', p['menxia'])):
            with self.assertRaises(ValueError):
                plans.record_review(task, role, 'approved', plan_ref, wrong, events)

    def test_plan_changes_invalidate_reviews_and_replay_is_stable(self):
        task, doc, p, events = fixture()
        task = plans.submit_plan(task, doc, p['zhongshu'], events)
        self.assertEqual(plans.submit_plan(task, doc, p['zhongshu'], events), task)
        plan_ref = plan_reference(task['zhongshu_plan'])
        task = plans.record_review(task, 'menxia', 'approved', plan_ref, p['menxia'], events)
        doc['goal'] = 'Count another public fixture'
        changed = plans.submit_plan(task, doc, p['zhongshu'], events)
        self.assertEqual(changed['zhongshu_plan']['revision'], 2)
        self.assertEqual(changed['case_reviews'], {})
        with self.assertRaises(ValueError):
            plans.record_review(changed, 'menxia', 'approved', plan_ref, p['menxia'], events)
        self.assertEqual(len(changed['zhongshu_plan_history']), 2)

    def test_malformed_artifact_and_charter_drift_are_rejected(self):
        task, doc, p, events = fixture()
        task = plans.submit_plan(task, doc, p['zhongshu'], events)
        task['zhongshu_plan']['document']['goal'] = ''
        with self.assertRaises(ValueError):
            plans.current_plan(task)
        task = plans.submit_plan(fixture()[0], doc, p['zhongshu'], events)
        task['charter_revision'] = 2
        with self.assertRaises(ValueError):
            plans.current_plan(task)

    def test_serial_inline_is_not_parallel_delivery(self):
        task, doc, _, events = fixture()
        producer = {'kind': 'serial_inline', 'agent_id': '', 'evidence': 'inline drafting'}
        with self.assertRaises(ValueError):
            plans.submit_plan(task, doc, producer, events)
        task['case_execution']['behavior'] = 'serial'
        result = plans.submit_plan(task, doc, producer, [])
        self.assertEqual(result['zhongshu_plan']['producer']['kind'], 'serial_inline')


class RuntimePlanFlowTests(unittest.TestCase):
    # Reuse only isolated filesystem fixture setup, not a production substitute.
    from check_court_case_binding import StandardCaseRuntimeTests as _Fixture
    setUp = _Fixture.setUp
    tearDown = _Fixture.tearDown

    def cli(self, *args, ok=True):
        command = [sys.executable, '-X', 'utf8', '-B', str(Path(__file__).resolve().parents[1] / 'court_cli.py'), '--format', 'json', 'court', *args]
        result = subprocess.run(command, capture_output=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        value = json.loads(result.stdout)
        return value['payload'] if value.get('payload') is not None else value

    def write(self, name, value):
        path = self.root / name
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        return str(path)

    def start_case(self):
        import court_runtime
        charter = 'Isolated case plan and independent review interface test'
        intake = self.cli('intake-template', '--charter', charter)
        self.cli('create', '--title', 'Case plan interface test', '--charter', charter,
                 '--task-id', 'plan-flow', '--session-id', 'plan-flow-session',
                 '--authority', 'super', '--behavior', 'serial', '--work-kind', 'audit',
                 '--intake-file', self.write('intake.json', intake['conversation_gate']),
                 '--invariant-capsule-file', self.write('capsule.json', intake['invariant_capsule']),
                 '--evidence', 'isolated interface fixture')
        for state in ('Taizi', 'ThreeDepartments'):
            self.cli('transition', '--task-id', 'plan-flow', '--to-state', state,
                     '--actor', 'taizi', '--evidence', 'isolated interface fixture')
        return court_runtime.load_tasks()['plan-flow']

    def test_generated_template_is_directly_submittable_and_task_bound(self):
        self.start_case()
        template=self.cli('plan','template','--task-id','plan-flow')
        template['document']=fixture()[1]
        template['producer']={'kind':'serial_inline','agent_id':'','evidence':'isolated explicit serial fixture'}
        wrong=copy.deepcopy(template);wrong['task_id']='foreign'
        self.cli('plan','submit','--task-id','plan-flow','--request-file',self.write('wrong-template.json',wrong),ok=False)
        self.cli('plan','submit','--task-id','plan-flow','--request-file',self.write('template.json',template))
        self.assertEqual(self.cli('plan','show','--task-id','plan-flow')['plan']['document'],template['document'])

    def test_unplanned_case_can_pause_and_resume_without_skipping_review(self):
        self.start_case()
        self.cli('pause','--task-id','plan-flow','--actor','taizi','--reason','test failure',
            '--affected-scope','current task','--evidence-preserved','fixture evidence','--unsafe-remaining','plan pending')
        self.assertEqual(self.cli('workflow-status','--task-id','plan-flow')['state'],'Paused')
        resume=['resume','--task-id','plan-flow','--actor','taizi','--from-paused-state','ThreeDepartments',
                '--resume-evidence','same task repaired','--affected-scope','current task']
        self.cli(*resume,'--to-state','SixMinistries',ok=False)
        self.cli(*resume,'--to-state','ThreeDepartments')
        self.assertEqual(self.cli('workflow-status','--task-id','plan-flow')['state'],'ThreeDepartments')

    def test_public_create_cannot_silently_choose_legacy(self):
        import court_runtime
        charter = 'Explicit standard case boundary fixture'
        intake = self.cli('intake-template', '--charter', charter)
        arguments = ['create', '--title', 'no session', '--charter', charter,
                     '--task-id', 'no-session', '--authority', 'super', '--behavior', 'serial',
                     '--work-kind', 'audit', '--intake-file', self.write('gate.json', intake['conversation_gate']),
                     '--invariant-capsule-file', self.write('scope.json', intake['invariant_capsule'])]
        self.cli(*arguments, ok=False)
        self.assertNotIn('no-session', court_runtime.load_tasks())
        self.cli(*arguments, '--legacy-compatibility')
        self.assertEqual(self.cli('workflow-status', '--task-id', 'no-session')['case_status'], 'LEGACY_UNBOUND')

    def test_standard_create_rejects_absolute_scope_before_allocating(self):
        import court_runtime
        charter = 'Reject malformed standard scope before task allocation'
        intake = self.cli('intake-template', '--charter', charter)
        capsule = intake['invariant_capsule']
        for scope in (['C:/outside/result.json'], ['../outside'], ['/absolute/result']):
            capsule['write_set'] = scope
            gate_file = self.write('gate.json', intake['conversation_gate'])
            capsule_file = self.write('bad-scope.json', capsule)
            before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
            value = self.cli('create', '--title', 'bad scope', '--charter', charter,
                '--task-id', 'bad-scope', '--session-id', 'bad-scope-session', '--authority', 'super',
                '--behavior', 'parallel', '--work-kind', 'audit', '--intake-file', gate_file,
                '--invariant-capsule-file', capsule_file, ok=False)
            self.assertIn('standard_create_capsule_write_set_requires_relative_paths', str(value))
            self.assertEqual(court_runtime.load_tasks(), {})
            self.assertEqual(before, {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_standard_terminal_checkpoint_cannot_bypass_runtime_closeout(self):
        task = self.start_case()
        command = [sys.executable, '-B', str(Path(__file__).resolve().parents[1] / 'court_cli.py'),
            '--format', 'json', 'shiguan', 'archive-checkpoint', '--topic', 'Unreviewed closeout',
            '--phase', 'light closeout', '--summary', 'Fixture reports only', '--evidence', 'fixture', '--next', 'none',
            '--session-id', task['session_id'], '--case-binding-json', json.dumps(task['case_binding']),
            '--memory-decision', 'SKIP', '--refresh-mode', 'none']
        before = {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        for status in ('DONE', 'DONE_WITH_CONCERNS', 'PASSED', 'PASSED_WITH_CONCERNS'):
            result = subprocess.run([*command, '--status', status], capture_output=True, encoding='utf-8', timeout=30)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertEqual(before, {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
        # Legacy standalone notes are still allowed to record text-only concerns.
        legacy = command[:command.index('--session-id')]
        result = subprocess.run([*legacy, '--status', 'DONE_WITH_CONCERNS', '--memory-decision', 'SKIP', '--refresh-mode', 'none'],
                                capture_output=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_canonical_departments_have_distinct_instances_not_issuer_threads(self):
        task = self.start_case()
        _, doc, producers, events = fixture()
        task['agents'] = fixture()[0]['agents']
        task['native_host_action_receipts'] = {}
        for role in producers:
            agent_id = producers[role]['agent_id']
            agent = task['agents'][agent_id]
            agent.update(task_id=task['task_id'], semantic_epoch=task['semantic_epoch'],
                court_code=task['court_code'], charter_revision=task['charter_revision'],
                native_host_identity_kind='canonical_agent_path', native_host_thread_id=None,
                native_host_instance_id='/root/' + role, native_trace_issuer_thread_id='shared-parent',
                native_host_action_receipt_id=role)
            task['native_host_action_receipts'][role] = {'target_id': agent_id}
        for event in events:
            event.update(task_id=task['task_id'],court_code=task['court_code'],semantic_epoch=task['semantic_epoch'])
        task = plans.submit_plan(task, doc, producers['zhongshu'], events)
        plan_ref = plan_reference(task['zhongshu_plan'])
        task = plans.record_review(task, 'menxia', 'approved', plan_ref, producers['menxia'], events)
        task = plans.record_review(task, 'shangshu', 'dispatchable', plan_ref, producers['shangshu'], events)
        plans.require_reviewed_plan(task)
        bad = copy.deepcopy(task)
        bad['agents']['fixture-shangshu']['native_host_instance_id'] = '/root/menxia'
        with self.assertRaisesRegex(ValueError, 'departments_must_be_distinct'):
            plans.record_review(bad, 'shangshu', 'dispatchable', plan_ref, producers['shangshu'], events)
        bad = copy.deepcopy(task)
        bad['agents']['fixture-shangshu']['native_host_thread_id'] = 'shared-parent'
        with self.assertRaisesRegex(ValueError, 'canonical_path_is_not_a_thread'):
            plans.record_review(bad, 'shangshu', 'dispatchable', plan_ref, producers['shangshu'], events)

    def test_public_runtime_archive_reaches_preflight_without_writing(self):
        import court_runtime
        self.start_case()
        before = court_runtime.tasks_path().read_bytes()
        result = subprocess.run([sys.executable, '-B', str(Path(__file__).resolve().parents[1] / 'court_cli.py'),
            '--format', 'json', 'shiguan', 'archive-runtime-task', '--task-id', 'plan-flow'],
            capture_output=True, encoding='utf-8', timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('unknown command', result.stdout)
        self.assertIn('ARCHIVE_RUNTIME_ERROR case_plan_not_drafted', result.stdout + result.stderr)
        self.assertEqual(court_runtime.tasks_path().read_bytes(), before)

    def test_cancelled_shangshu_cannot_authorize_canonical_ministry(self):
        import court_runtime
        task = self.start_case()
        parent = {'role': 'shangshu', 'direct_superior': 'taizi',
            'native_host_identity_kind': 'canonical_agent_path',
            'native_trace_session_id': task['session_id'], 'semantic_epoch': task['semantic_epoch'],
            'court_code': task['court_code'], 'preload_status': 'PASSED',
            'office_execution_ready': True, 'status': 'running',
            'native_host_action_receipt_id': 'fixture-native-receipt',
            'native_host_instance_id': '/root/shangshu_ready'}
        task['agents'] = {'parent': parent}
        binding = {'role': 'gongbu', 'direct_superior': 'shangshu'}
        with patch('commands.court_native_bridge.current_host_identity',
                   return_value={'thread_id': 'reader', 'session_id': task['session_id']}):
            self.assertEqual(len(court_runtime._native_bridge_identity_context(task, binding)['trusted_parent_paths']), 1)
            for field, value in [('release_status', 'closed'), ('release_status', 'cancel_requested'),
                ('invalidated_at', '2026-09-06'), ('assignment_status', 'INVALIDATED'),
                ('assignment_invalidated_by_semantic_resume', True),
                ('assignment_invalidated_by_charter_revision', 2)]:
                invalid = copy.deepcopy(task); invalid['agents']['parent'][field] = value
                self.assertEqual(court_runtime._native_bridge_identity_context(invalid, binding)['trusted_parent_paths'], [])

    def test_cli_mcp_plan_flow_and_stale_review(self):
        import court_runtime
        task = self.start_case()
        self.assertEqual(task['case_binding']['court_code'], task['court_code'])
        context = self.cli('semantic-context-template', '--task-id', 'plan-flow')
        self.assertEqual(context['plan_status'], 'BOOTSTRAP_UNPLANNED')
        self.assertEqual(context['context']['case_ref'], {
            'court_code': task['court_code'], 'charter_revision': task['charter_revision'],
        })
        self.assertIsNone(context['context']['plan_ref'])
        before = court_runtime.tasks_path().read_bytes()
        self.cli('transition', '--task-id', 'plan-flow', '--to-state', 'ThreeDepartmentsPetition',
                 '--actor', 'taizi', '--evidence', 'not reviewed', ok=False)
        self.assertEqual(before, court_runtime.tasks_path().read_bytes())
        producer = {'kind': 'serial_inline', 'agent_id': '', 'evidence': 'explicit isolated serial-inline report'}
        request = {'document': fixture()[1], 'producer': producer, 'expected_plan_revision': 0}
        self.cli('plan', 'submit', '--task-id', 'plan-flow', '--request-file', self.write('plan.json', request))
        shown = self.cli('plan', 'show', '--task-id', 'plan-flow')['plan']
        context = self.cli('semantic-context-template', '--task-id', 'plan-flow')
        self.assertEqual(context['context']['plan_ref'], plan_reference(shown))
        for role, decision in (('menxia', 'approved'), ('shangshu', 'dispatchable')):
            template = self.cli('plan', 'template', '--task-id', 'plan-flow')
            self.assertEqual(template['review']['plan_ref'], plan_reference(shown))
            self.assertIn('producer', template['review'])
            template['review'].update(role=role, decision=decision, producer=producer)
            review = template['review']
            supplied = review if role == 'menxia' else template
            self.cli('plan', 'review', '--task-id', 'plan-flow', '--request-file', self.write(role + '.json', supplied))
        self.assertEqual(self.cli('plan', 'review', '--task-id', 'plan-flow',
                         '--request-file', self.write('flat-review-replay.json', review))['status'], 'REPLAYED')
        legacy=copy.deepcopy(template);legacy['review'].pop('producer');legacy['producer']=producer
        self.assertEqual(self.cli('plan','review','--task-id','plan-flow',
                         '--request-file',self.write('legacy-review-template.json',legacy))['status'],'REPLAYED')
        status = self.cli('workflow-status', '--task-id', 'plan-flow')
        self.assertEqual(status['plan_status'], 'REVIEWED')
        server = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve().parents[1] / 'court_mcp_server.py')],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8')
        def rpc(message):
            server.stdin.write(json.dumps(message) + '\n'); server.stdin.flush()
            return json.loads(server.stdout.readline())
        try:
            rpc({'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-11-25', 'capabilities': {}, 'clientInfo': {'name': 'isolated-plan-interface', 'version': '1'}}})
            result = rpc({'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call', 'params': {'name': 'court.workflow_status', 'arguments': {'task_id': 'plan-flow'}}})
            received = result['result']['structuredContent']['api']['stdout']
            self.assertEqual(received, status)
        finally:
            server.stdin.close()
            try: server.wait(timeout=10)
            except subprocess.TimeoutExpired: server.kill(); server.wait(timeout=10)
            server.stdout.close(); server.stderr.close()
        self.cli('plan', 'submit', '--task-id', 'plan-flow', '--request-file', self.write('stale.json', request), ok=False)
        self.cli('transition', '--task-id', 'plan-flow', '--to-state', 'ThreeDepartmentsPetition', '--actor', 'taizi', '--evidence', 'reviewed')

    def test_plan_event_failure_restores_task_and_event_bytes(self):
        import court_runtime
        from argparse import Namespace
        self.start_case()
        before = {p: p.read_bytes() for p in (court_runtime.tasks_path(), court_runtime.events_path())}
        request = {'document': fixture()[1], 'producer': {'kind': 'serial_inline', 'agent_id': '', 'evidence': 'isolated rollback report'}, 'expected_plan_revision': 0}
        with patch.object(court_runtime, 'append_event', side_effect=OSError('controlled event failure')):
            with self.assertRaises(OSError):
                court_runtime.case_plan_operation(Namespace(action='submit', task_id='plan-flow', request=request))
        self.assertEqual({p: p.read_bytes() for p in before}, before)

    def test_recharter_preserves_identity_and_reenters_unplanned_bootstrap(self):
        import court_runtime
        task = self.start_case()
        producer = {'kind': 'serial_inline', 'agent_id': '', 'evidence': 'explicit serial fixture'}
        task = plans.submit_plan(task, fixture()[1], producer, [])
        from court_case_binding import refresh_case_binding
        task['case_binding'] = refresh_case_binding(task)
        old_plan = copy.deepcopy(task['zhongshu_plan'])
        new_charter = 'A revised isolated plan request'
        revised = court_runtime.revise_charter_record(task, expected_revision=1,
            case_ref=plan_reference(task['zhongshu_plan']), new_revision=2,
            new_charter=new_charter,
            new_invariant_capsule=court_runtime.invariant_capsule_template(new_charter),
            event_head_id=court_runtime._event_head_id(task['task_id']),
            actor='taizi', evidence='isolated correction')
        self.assertIsNone(revised.get('zhongshu_plan'))
        self.assertEqual(revised['case_reviews'], {})
        self.assertEqual(revised['zhongshu_plan_history'][0], old_plan)
        self.assertEqual(revised['case_binding']['court_code'], task['case_binding']['court_code'])
        self.assertEqual(revised['case_binding']['charter_revision'], 2)
        renewed = plans.submit_plan(revised, fixture()[1], producer, [])
        self.assertEqual(renewed['zhongshu_plan']['revision'], 2)


if __name__ == '__main__':
    unittest.main()
