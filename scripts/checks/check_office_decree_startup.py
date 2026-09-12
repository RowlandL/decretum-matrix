"""Regression checks for decree-bound child startup and Shangshu -> Libu delivery."""
from __future__ import annotations

import sys
from pathlib import Path
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from argparse import Namespace
from contextlib import ExitStack, redirect_stdout
from copy import deepcopy
import json
import io
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import court_runtime as runtime
from court_case_binding import case_reference, office_capsule_reference, refresh_case_binding
from court_office_bootstrap import build_preload_manifest
from court_plan_artifacts import record_review, submit_plan
from commands import court_native_bridge as bridge
from checks.check_semantic_continuity import _create_args, _semantic_args, _semantic_context
from checks import check_native_opaque_capture as opaque

SESSION = opaque.SESSION
PARENT = opaque.PARENT
MINISTRIES = ('libu-hr', 'hubu', 'libu', 'bingbu', 'xingbu', 'gongbu')


class OfficeDecreeStartupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(patch.object(runtime, 'runtime_root', return_value=self.root / 'runtime'))
        self.stack.enter_context(patch.dict(os.environ, {
            'COURT_SHARED_SHIGUAN_ROOT': str(self.root / 'shared'),
            'CODEX_HOME': str(self.root / 'host'), 'CODEX_THREAD_ID': PARENT,
            'CODEX_SESSION_ID': SESSION,
        }))
        args = _create_args('office-decree-startup', 'bounded Libu documentation task')
        args.session_id = SESSION
        args.behavior = 'parallel'
        self.task = runtime.create_task(args).task
        self.binding = {'role': 'libu', 'direct_superior': 'shangshu'}
        self.parent = {
            'role': 'shangshu', 'direct_superior': 'taizi',
            'case_ref': case_reference(self.task),
            'semantic_epoch': self.task['semantic_epoch'],
            'native_host_identity_kind': 'canonical_agent_path',
            'native_trace_session_id': SESSION,
            'native_host_instance_id': '/root/shangshu_ready',
            'native_child_thread_id': PARENT,
            'native_host_action_receipt_id': 'HOST-SHANGSHU-FIXTURE',
            'preload_status': 'PASSED', 'office_execution_ready': True,
            'status': 'running', 'release_status': 'open',
        }
        self.task['agents'] = {'shangshu-ready': self.parent}

    def test_libu_parent_is_bound_by_current_decree(self) -> None:
        before = deepcopy(self.task)
        runtime._native_bridge_caller_guard(self.task, self.binding)
        context = runtime._native_bridge_identity_context(self.task, self.binding)
        self.assertEqual(context['trusted_parent_paths'], [{
            'path': '/root/shangshu_ready', 'kind': 'same_case_ready_shangshu',
            'thread_id': PARENT,
        }])
        self.assertEqual(self.task, before)

    def test_other_case_or_revision_is_not_a_parent(self) -> None:
        # A parent record bound to another case or revision must never grant
        # authority over this task's decree.
        valid = case_reference(self.task)
        for reference in (None, {}, {**valid, 'court_code': 'ZL-20260906-9999-TEST'},
                          {**valid, 'charter_revision': valid['charter_revision'] + 1}):
            with self.subTest(reference=reference):
                self.parent['case_ref'] = reference
                self.assertEqual(runtime._native_bridge_identity_context(
                    self.task, self.binding)['trusted_parent_paths'], [])
                with self.assertRaisesRegex(ValueError, 'caller_native_actor_required'):
                    runtime._native_bridge_caller_guard(self.task, self.binding)

    def test_inactive_or_foreign_parent_still_rejected(self) -> None:
        original = deepcopy(self.parent)
        for changes in ({'preload_status': 'PENDING'}, {'office_execution_ready': False},
                        {'status': 'closed'}, {'release_status': 'cancel_requested'},
                        {'invalidated_at': '2026-09-06T12:00:00+00:00'},
                        {'assignment_invalidated_by_semantic_resume': True},
                        {'semantic_epoch': self.task['semantic_epoch'] + 1},
                        {'native_trace_session_id': opaque.CHILD},
                        {'direct_superior': 'libu'}, {'native_host_action_receipt_id': ''}):
            with self.subTest(changes=changes):
                self.parent.clear(); self.parent.update(deepcopy(original)); self.parent.update(changes)
                with self.assertRaisesRegex(ValueError, 'caller_native_actor_required'):
                    runtime._native_bridge_caller_guard(self.task, self.binding)

    def test_capsule_suffix_uses_recorded_24_hour_time(self) -> None:
        reference = case_reference(self.task)
        for role, initials in (('libu', 'LB'), ('gongbu', 'GB'), ('shangshu', 'SSS')):
            for time, suffix in (('00:00:00', '0000'), ('09:05:00', '0905'), ('23:59:59', '2359')):
                with self.subTest(role=role, time=time):
                    issued = f'2026-09-06T{time}+08:00'
                    first = office_capsule_reference(reference, role, f'{role}#0001', issued)
                    self.assertEqual(first['capsule_id'], f"{reference['court_code']}-{suffix}{initials}")
                    self.assertEqual(first, office_capsule_reference(reference, role, f'{role}#0001', issued))
                    second = office_capsule_reference(reference, role, f'{role}#0002', issued)
                    self.assertNotEqual(first, second)  # Human suffix is not the instance authority.

    def test_ministry_preload_requires_no_external_commands(self) -> None:
        with patch.object(subprocess, 'run', side_effect=AssertionError('unexpected startup command')) as run, \
                patch.object(subprocess, 'Popen', side_effect=AssertionError('unexpected startup process')) as popen, \
                patch.object(os, 'system', side_effect=AssertionError('unexpected startup shell')) as system:
            for role in MINISTRIES:
                manifest = build_preload_manifest(role, court_code=self.task['court_code'])
                self.assertEqual(manifest.court_code, self.task['court_code'])
                self.assertEqual(manifest.direct_superior, 'shangshu')
            self.assertEqual((run.call_count, popen.call_count, system.call_count), (0, 0, 0))

    def _review_and_admit_libu(self, *, public_office_request=False) -> tuple[dict, dict]:
        task_id = self.task['task_id']
        for state in ('Taizi', 'ThreeDepartments'):
            runtime.transition_task(runtime.build_parser().parse_args([
                'transition', '--task-id', task_id, '--to-state', state,
                '--actor', 'taizi', '--evidence', 'office startup regression',
            ]))
        task = runtime.load_tasks()[task_id]
        document = {
            'goal': 'bounded Libu documentation work', 'non_goals': ['no external writes'],
            'steps': [{'id': 'libu', 'role': 'libu', 'action': 'review the bounded document'}],
            'acceptance': ['return a bounded report'],
            'write_set': ['scripts/court_semantic_continuity.py'],
        }
        # Recorded department observations are fixtures, not real spawned workers.
        observed, producers = [], {}
        for role in ('zhongshu', 'menxia', 'shangshu'):
            agent_id, receipt_id = role + '-fixture', 'HOST-' + role
            task['agents'][agent_id] = {
                'task_id': task_id, 'role': role, 'direct_superior': 'taizi',
                **case_reference(task), 'semantic_epoch': task['semantic_epoch'],
                'preload_status': 'PASSED', 'office_execution_ready': True,
                'native_host_thread_id': role + '-host-thread', 'native_host_action_receipt_id': receipt_id,
            }
            task.setdefault('native_host_action_receipts', {})[receipt_id] = {'target_id': agent_id}
            evidence = 'fixture-report-' + role
            event = runtime.make_event(task, 'agent_report', 'running', 'running', 'taizi', evidence, '')
            event.update(agent_role=role, agent_id=agent_id, **case_reference(task),
                         semantic_epoch=task['semantic_epoch'])
            runtime.append_event(event); observed.append(event)
            producers[role] = {'kind': 'host_report', 'agent_id': agent_id, 'evidence': evidence}
        task = submit_plan(task, document, producers['zhongshu'], observed)
        plan = runtime.plan_reference(task['zhongshu_plan'])
        for role, verdict in (('menxia', 'approved'), ('shangshu', 'dispatchable')):
            task = record_review(task, role, verdict, plan, producers[role], observed)
        task['case_binding'] = refresh_case_binding(task)
        tasks = runtime.load_tasks(); tasks[task_id] = task; runtime.write_tasks(tasks)
        for state in ('ThreeDepartmentsPetition', 'TaiziReply', 'ShangshuDispatch'):
            runtime.transition_task(runtime.build_parser().parse_args([
                'transition', '--task-id', task_id, '--to-state', state,
                '--actor', 'taizi', '--evidence', 'office startup regression',
            ]))
        context = _semantic_context(task_id)
        runtime.semantic_checkpoint_task(_semantic_args(task_id, 'checkpoint', context=context))
        task = runtime.semantic_verify_task(_semantic_args(task_id, 'verify', context=context)).task
        args = Namespace(
            task_id=task_id, role='libu', calling_office='shangshu',
            write_path='scripts/court_semantic_continuity.py', next_depth=2,
            integration_domain='office-startup', wave_id='libu-wave',
            context_tokens=1000, message_chars=256, host_active_agents=1,
            host_capacity=16, host_retained_agents=0, host_reclamation_status='verified',
            user_agent_budget=4, provider_launch_budget=4, assignment='bounded document review',
            task_focus='documentation', complexity='medium', risk='low', ambiguity='low',
            transport='codex', evidence='office startup regression', system_memory_percent=0.,
        )
        template = runtime.public_admission_template_payload(args)
        if public_office_request:
            output = io.StringIO()
            with redirect_stdout(output):
                status = runtime.main(['office', 'admit', '--request-json', json.dumps(template['request'])])
            self.assertEqual(status, 0, output.getvalue())
            admission = json.loads(output.getvalue())['result']
        else:
            admission = runtime.agent_admit(runtime.build_parser().parse_args(template['argv']))
        self.assertTrue(admission['allowed'])
        task = runtime.load_tasks()[task_id]
        task['agents'] = {'shangshu-ready': deepcopy(self.parent)}
        tasks = runtime.load_tasks(); tasks[task_id] = task; runtime.write_tasks(tasks)
        return task, admission

    def test_generated_admission_request_uses_public_office_entry(self) -> None:
        task, admission = self._review_and_admit_libu(public_office_request=True)
        self.assertTrue(admission['allowed'])
        self.assertEqual(admission['case_ref'], case_reference(task))
        self.assertEqual(admission['selected_roles'], ['libu'])
        self.assertTrue(admission['selected_bindings'][0]['instance_id'])

    def test_public_contract_exposes_current_result_envelope(self) -> None:
        schema = runtime.public_intake_contract_payload()['office_result_envelope_schema']
        self.assertTrue({'agent_id', 'case_ref', 'plan_ref', 'summary', 'evidence', 'produced_at'}
                        <= set(schema['required']))
        self.assertEqual(schema['properties']['status']['enum'], ['completed', 'failed', 'cancelled'])
        self.assertNotIn('charter_sha256', schema['properties'])

    def test_libu_bootstrap_instructs_read_and_ack_only(self) -> None:
        task, admission = self._review_and_admit_libu()
        request = runtime.office_native_request(Namespace(
            schema='court.office.native_request.v1', task_id=task['task_id'],
            wave_id=admission['wave_id'], instance_id=admission['selected_bindings'][0]['instance_id'],
        ))['request']
        packet = runtime.public_dispatch_context_packet(task, admission['wave_id'])
        with patch.object(subprocess, 'Popen', side_effect=AssertionError('unexpected bootstrap process')):
            message = json.loads(bridge.canonical_host_message(
                request, execution=task['case_execution'], p00_context=packet,
            ))
        bootstrap = message['bootstrap']
        self.assertEqual(bootstrap['skill'], 'SKILL.md')
        self.assertEqual(bootstrap['then_read'], [
            'agents/standing-officials/libu.toml', 'agents/office-dossiers/libu/AGENTS.md',
        ])
        self.assertIn('without standalone preflight scripts or root intake', bootstrap['then'])
        self.assertIn('wait for acceptance before business CLI/MCP', bootstrap['then'])
        self.assertEqual(message['p00']['case_ref'], case_reference(task))
        self.assertEqual(message['p00']['office_capsule_ref'], request['office_capsule_ref'])

    def test_reviewed_libu_request_and_opaque_capture(self) -> None:
        task, admission = self._review_and_admit_libu()
        bound = admission['selected_bindings'][0]
        result = runtime.office_native_request(Namespace(
            schema='court.office.native_request.v1', task_id=task['task_id'],
            wave_id=admission['wave_id'], instance_id=bound['instance_id'],
        ))
        request = result['request']
        self.assertEqual(request['role'], 'libu')
        self.assertEqual(request['office_capsule_ref'], bound['office_capsule_ref'])
        self.assertEqual(request['case_ref'], case_reference(task))
        self.assertEqual(result['expected_host_action'], 'spawn')
        packet = runtime.public_dispatch_context_packet(task, admission['wave_id'])
        # Simulate only the host boundary; request building and evidence capture are production code.
        with patch.object(opaque, '_request', return_value=deepcopy(request)), \
                patch.object(opaque, '_p00_context', return_value=packet):
            rows, meta, ctx, save, capture = opaque.fixture(self.root / 'host', ministry=True)
            expected = runtime._native_bridge_identity_context(task, bound)
            ctx.clear(); ctx.update(expected)
            receipt = capture()
        self.assertEqual(receipt['host_spawn_evidence']['parent_thread_id'], PARENT)
        self.assertEqual(receipt['host_spawn_evidence']['child_thread_id'], opaque.CHILD)
        self.assertEqual(receipt['request_ref']['court_code'], task['court_code'])
        self.assertEqual(receipt['host_spawn_evidence']['request_delivery'], 'PENDING_PRELOAD_ACK')


if __name__ == '__main__':
    unittest.main(verbosity=2)
