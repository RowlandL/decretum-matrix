"""Opaque host storage and skill-before-tool order regressions."""
from pathlib import Path
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import copy
import json
import os
import tempfile
import unittest
from types import MappingProxyType
from unittest.mock import patch
from commands import court_native_bridge as bridge
import court_runtime
from checks.check_court_native_bridge import _request, _execution, _p00_context
from court_native_host_dispatch import validate_native_host_action_receipt
from court_case_binding import office_capsule_reference
from court_native_trace import (
    NativeEvidencePending,
    _command_text,
    _direct_niu_payload,
    _invokes_court_cli,
    _static_niu_cat_read,
    skill_read_order,
)
from court_office_bootstrap import build_preload_manifest
from checks.installed_identity_fixture import write_skill

SESSION = '01a0743b-4c11-7021-b2ad-31f2dfe23df5'
PARENT = '01a07440-9c7d-7b52-b53a-51edbd68e6da'
CHILD = '01a0743f-9c12-7842-bfec-8620bf6942c4'
_UNSET = object()


def fixture(home: Path, *, ministry=False, root_distinct=False):
    request = _request()
    if not ministry:
        request.update(role='zhongshu', direct_superior='taizi')
        request['role_ack'].update(role='zhongshu', direct_superior='taizi')
    request['office_capsule_ref'] = office_capsule_reference(
        request['case_ref'], request['role'], request['instance_id'],
        '2026-09-06T09:05:00+08:00',
    )
    native = bridge.native_request_result(request, execution=_execution(), p00_context=_p00_context(request))
    arguments = copy.deepcopy(native['host_invocation']['arguments'])
    arguments['message'] = 'gAAAAA' + 'A' * 120  # Deliberately not a decryptable payload.
    parent = PARENT if ministry or root_distinct else SESSION
    parent_path = '/root/shangshu_ready' if ministry else '/root'
    child_path = parent_path + '/' + arguments['task_name']
    rows = [
        {'type':'session_meta','payload':{'id':parent,'session_id':SESSION}},
        {'timestamp':'2026-09-06T01:05:20.100Z','type':'response_item','payload':{
            'type':'function_call','name':'spawn_agent','namespace':'collaboration','call_id':'call-fixture',
            'arguments':json.dumps(arguments)}},
        {'timestamp':'2026-09-06T01:05:20.500Z','type':'response_item','payload':{
            'type':'function_call_output','call_id':'call-fixture','output':json.dumps({'task_name':child_path})}},
        {'timestamp':'2026-09-06T01:05:20.600Z','type':'event_msg','payload':{
            'type':'item_completed','thread_id':parent,'item':{'type':'SubAgentActivity','id':'call-fixture',
            'kind':'started','agent_thread_id':CHILD,'agent_path':child_path}}},
    ]
    child_meta = {'id':CHILD,'session_id':SESSION,'parent_thread_id':parent,'agent_path':child_path,
        'thread_source':'subagent','timestamp':'2026-09-06T01:05:20.300Z',
        'source':{'subagent':{'thread_spawn':{'parent_thread_id':parent,'agent_path':child_path}}}}
    sessions = home/'sessions/2026/09/06';sessions.mkdir(parents=True)
    parent_file = sessions/f'rollout-{parent}.jsonl'
    child_file = sessions/f'rollout-{CHILD}.jsonl'
    def save():
        parent_file.write_text('\n'.join(json.dumps(row) for row in rows)+'\n',encoding='utf-8')
        child_file.write_text(json.dumps({'type':'session_meta','payload':child_meta})+'\n',encoding='utf-8')
    save()
    context = {'case_session_id':SESSION,'semantic_epoch':request['semantic_epoch'],
        'trusted_parent_paths':[{'path':parent_path,'kind':'same_case_ready_shangshu','thread_id':PARENT}
                                if ministry else {'path':'/root','kind':'taizi_root'}]}
    def capture():
        return bridge.capture_current_native_delivery(request, execution=_execution(),
            p00_context=_p00_context(request), identity_context=context,
            environment={'CODEX_THREAD_ID':parent,'CODEX_SESSION_ID':SESSION,'CODEX_HOME':str(home)}, codex_home=home)
    return rows, child_meta, context, save, capture


def model_capture_fixture(
    home: Path,
    *,
    model: str | None,
    reasoning_effort: str | None,
    request_model_field: str,
    request_effort_field: str,
    selection_digit: str,
    parent_model: str = 'gpt-parent-inherited',
    parent_effort: str = 'medium',
):
    request = _request()
    selection = {
        'schema': 'court.codex.model_selection.v1',
        'selection_id': 'MEA-' + selection_digit * 32,
        'source': 'current_user_explicit',
        'case_ref': copy.deepcopy(request['case_ref']),
        'semantic_epoch': request['semantic_epoch'],
        'model': model,
        'reasoning_effort': reasoning_effort,
    }
    route = {
        'transport': 'codex',
        'protocol': 'v2',
        'role': request['role'],
        'spawn_metadata': {'fork_turns': 'none'},
        'model_authorization_binding': copy.deepcopy(selection),
    }
    admission = {
        'wave_id': request['wave_id'],
        'selected_protocol': 'v2',
        'model_authorization_binding': copy.deepcopy(selection),
        'model_routes': {request['instance_id']: route},
    }
    task = {
        'task_id': request['task_id'],
        **request['case_ref'],
        'case_binding': MappingProxyType({
            **request['case_ref'],
            'case_execution': {'authority': 'super', 'behavior': 'parallel'},
        }),
        'semantic_receipt': {
            'semantic_epoch': request['semantic_epoch'],
            'case_ref': copy.deepcopy(request['case_ref']),
            'receipt_id': 'SEM-MODEL-CAPTURE-01',
            'plan_cursor': 'ThreeDepartments@3',
        },
    }
    binding = {
        'role': request['role'],
        'instance_id': request['instance_id'],
        'office_instance_kind': 'child_agent',
        'preload_sources': court_runtime._semantic_preload_sources(str(request['role'])),
    }
    execution, p00_context = court_runtime._native_bridge_host_message_inputs(
        task, admission
    )
    native = court_runtime._native_bridge_request_result(
        task,
        admission,
        binding,
        request,
        spawn_model_field=request_model_field,
        spawn_reasoning_effort_field=request_effort_field,
    )
    child_model = model if model is not None else parent_model
    child_effort = (
        reasoning_effort
        if reasoning_effort is not None
        else ("low" if model is not None else parent_effort)
    )
    parent_rows = [
        {'type': 'session_meta', 'payload': {
            'id': PARENT, 'session_id': SESSION, 'thread_id': PARENT,
        }},
        {'timestamp': '2026-09-06T01:05:19.900Z', 'type': 'turn_context', 'payload': {
            'turn_id': 'parent-turn-001', 'thread_id': PARENT, 'session_id': SESSION,
            'model': parent_model, 'effort': parent_effort,
        }},
        {'timestamp': '2026-09-06T01:05:20.100Z', 'type': 'response_item', 'payload': {
            'type': 'function_call', 'name': native['host_invocation']['tool_name'],
            'namespace': 'collaboration', 'call_id': 'call-model-capture',
            'arguments': json.dumps(native['host_invocation']['arguments']),
        }},
        {'timestamp': '2026-09-06T01:05:20.500Z', 'type': 'response_item', 'payload': {
            'type': 'function_call_output', 'call_id': 'call-model-capture',
            'output': json.dumps({
                'ok': True,
                'agent_id': 'gongbu-model-capture-agent',
                'thread_id': CHILD,
                'task_id': 'gongbu-model-capture-task',
            }),
        }},
    ]
    child_rows = [
        {'type': 'session_meta', 'payload': {
            'id': CHILD, 'session_id': SESSION, 'thread_id': CHILD,
            'parent_thread_id': PARENT, 'thread_source': 'subagent',
            'source': {'subagent': {'thread_spawn': {
                'parent_thread_id': PARENT, 'agent_role': None,
            }}},
        }},
        {'timestamp': '2026-09-06T01:05:20.700Z', 'type': 'turn_context', 'payload': {
            'turn_id': 'child-turn-001', 'thread_id': CHILD, 'session_id': SESSION,
            'model': child_model, 'effort': child_effort,
        }},
    ]
    sessions = home / 'sessions/2026/09/06'
    sessions.mkdir(parents=True)
    parent_file = sessions / f'rollout-{PARENT}.jsonl'
    child_file = sessions / f'rollout-{CHILD}.jsonl'

    def save():
        parent_file.write_text(
            '\n'.join(json.dumps(row) for row in parent_rows) + '\n',
            encoding='utf-8',
        )
        child_file.write_text(
            '\n'.join(json.dumps(row) for row in child_rows) + '\n',
            encoding='utf-8',
        )

    save()
    context = {
        'case_session_id': SESSION,
        'semantic_epoch': request['semantic_epoch'],
        'trusted_parent_paths': [{
            'path': '/root/shangshu_ready',
            'kind': 'same_case_ready_shangshu',
            'thread_id': PARENT,
        }],
    }

    def capture(
        *,
        capture_model_field: object = _UNSET,
        capture_effort_field: object = _UNSET,
        selection_override: object = _UNSET,
    ):
        kwargs = {
            'model_authorization_binding': (
                selection
                if selection_override is _UNSET
                else selection_override
            ),
        }
        if capture_model_field is not _UNSET:
            kwargs['spawn_model_field'] = capture_model_field
        if capture_effort_field is not _UNSET:
            kwargs['spawn_reasoning_effort_field'] = capture_effort_field
        return bridge.capture_current_native_delivery(
            request,
            execution=execution,
            p00_context=p00_context,
            identity_context=context,
            environment={
                'CODEX_THREAD_ID': PARENT,
                'CODEX_SESSION_ID': SESSION,
                'CODEX_HOME': str(home),
            },
            codex_home=home,
            **kwargs,
        )

    return {
        'request': request,
        'selection': selection,
        'native': native,
        'request_model_field': request_model_field,
        'request_effort_field': request_effort_field,
        'parent_model': parent_model,
        'parent_effort': parent_effort,
        'child_model': child_model,
        'child_effort': child_effort,
        'parent_rows': parent_rows,
        'child_rows': child_rows,
        'save': save,
        'capture': capture,
    }


class OpaqueCaptureTests(unittest.TestCase):
    def test_host_facts_capture_without_decrypting_or_claiming_message_delivery(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows, meta, context, save, capture = fixture(Path(tmp))
            # Reproduce the old plaintext-marker-only lookup on the same fixture.
            real = bridge._exact_spawn_call
            def old_marker_only(payload, **kw):
                if not bridge._marker_present(payload, kw['marker']):return None
                return real(payload, **kw)
            with patch.object(bridge, '_exact_spawn_call', side_effect=old_marker_only):
                with self.assertRaisesRegex(ValueError,'marked_host_action_missing'):
                    capture()
            result = capture();receipt=result['native_host_action_receipt']
            self.assertEqual(result['capture_scope'],'HOST_SPAWN_ONLY_PRELOAD_PENDING')
            self.assertEqual(receipt['host_spawn_evidence']['message_verification'],'OPAQUE_NOT_INSPECTED')
            self.assertEqual(receipt['host_spawn_evidence']['request_delivery'],'PENDING_PRELOAD_ACK')
            self.assertEqual(receipt['host_spawn_evidence']['child_thread_id'],CHILD)
            validate_native_host_action_receipt(receipt,expected=receipt['request'],replay_guard=set())

    def test_metadata_disagreement_and_replay_are_rejected(self):
        changes = ['missing_activity','duplicate_activity','wrong_call','wrong_path','wrong_parent',
                   'wrong_child','wrong_session','wrong_creation_order','wrong_event_order','plaintext_mismatch']
        for change in changes:
            with self.subTest(change=change), tempfile.TemporaryDirectory() as tmp:
                rows, meta, ctx, save, capture=fixture(Path(tmp))
                if change=='missing_activity':rows.pop()
                elif change=='duplicate_activity':rows.append(copy.deepcopy(rows[-1]))
                elif change=='wrong_call':rows[-1]['payload']['item']['id']='foreign'
                elif change=='wrong_path':rows[-1]['payload']['item']['agent_path']='/root/foreign'
                elif change=='wrong_parent':meta['parent_thread_id']=PARENT
                elif change=='wrong_child':meta['id']=PARENT
                elif change=='wrong_session':meta['session_id']=PARENT
                elif change=='wrong_creation_order':meta['timestamp']='2026-09-05T00:00:00Z'
                elif change=='wrong_event_order':rows.insert(1,rows.pop())
                else:
                    args=json.loads(rows[1]['payload']['arguments']);args['message']='different plaintext'
                    rows[1]['payload']['arguments']=json.dumps(args)
                save()
                with self.assertRaises(ValueError):capture()

    def test_ministry_needs_concrete_ready_parent_thread_and_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows,meta,ctx,save,capture=fixture(Path(tmp),ministry=True)
            result=capture()
            self.assertEqual(result['host_spawn_evidence']['parent_thread_id'],PARENT)
            ctx['trusted_parent_paths'][0]['thread_id']=CHILD
            with self.assertRaises(ValueError):capture()

    def test_root_thread_is_not_assumed_to_be_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            *_, capture = fixture(Path(tmp), root_distinct=True)
            self.assertEqual(capture()['host_spawn_evidence']['parent_thread_id'], PARENT)

    def test_plaintext_native_spawn_gets_same_pending_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows, meta, context, save, capture = fixture(Path(tmp))
            request = _request(); request.update(role='zhongshu', direct_superior='taizi')
            request['role_ack'].update(role='zhongshu', direct_superior='taizi')
            request['office_capsule_ref'] = office_capsule_reference(
                request['case_ref'], request['role'], request['instance_id'],
                '2026-09-06T09:05:00+08:00',
            )
            args = json.loads(rows[1]['payload']['arguments'])
            args['message'] = bridge.canonical_host_message(request, execution=_execution(), p00_context=_p00_context(request))
            rows[1]['payload']['arguments'] = json.dumps(args); save()
            evidence = capture()['host_spawn_evidence']
            self.assertEqual(evidence['message_verification'], 'PLAINTEXT_EXACT_MATCHED')
            self.assertEqual(evidence['request_delivery'], 'PENDING_PRELOAD_ACK')
        with self.assertRaises(NativeEvidencePending):
            bridge.captured_child_read_order({'native_host_action_receipt_id':'legacy-plaintext'}, object())

    def test_explicit_model_capture_binds_parent_child_turn_contexts(self):
        cases = (
            ('pair', 'gpt-6-astra', 'ultra', 'visible', 'visible', '1'),
            ('model-only', 'gpt-6-astra', None, 'visible', 'hidden', '2'),
            ('effort-only', None, 'high', 'hidden', 'visible', '3'),
        )
        for label, model, effort, model_field, effort_field, digit in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                case = model_capture_fixture(
                    Path(tmp),
                    model=model,
                    reasoning_effort=effort,
                    request_model_field=model_field,
                    request_effort_field=effort_field,
                    selection_digit=digit,
                )
                result = case['capture'](
                    capture_model_field=model_field,
                    capture_effort_field=effort_field,
                )
                applied = []
                if model is not None:
                    applied.append('model')
                if effort is not None:
                    applied.append('reasoning_effort')
                expected = {
                    'schema': 'court.host_model_execution_binding.v1',
                    'selection_id': case['selection']['selection_id'],
                    'applied_spawn_fields': applied,
                    'parent_turn_context': {
                        'model': case['parent_model'],
                        'effort': case['parent_effort'],
                        'trace_line': 2,
                        'turn_id': 'parent-turn-001',
                    },
                    'child_turn_context': {
                        'model': case['child_model'],
                        'effort': case['child_effort'],
                        'trace_line': 2,
                        'turn_id': 'child-turn-001',
                    },
                    'status': 'MATCHED',
                }
                self.assertEqual(result['host_model_execution_binding'], expected)
                receipt = result['native_host_action_receipt']
                self.assertEqual(receipt['host_model_execution_binding'], expected)
                self.assertEqual(
                    receipt['host_result']['host_model_execution_binding'],
                    expected,
                )
                self.assertEqual(
                    receipt['model_authorization_binding'],
                    case['selection'],
                )
                self.assertEqual(
                    receipt['host_result']['model_authorization_binding'],
                    case['selection'],
                )
                validate_native_host_action_receipt(
                    receipt,
                    expected=receipt['request'],
                    replay_guard=set(),
                )

    def test_capture_requires_selected_capabilities_but_allows_visible_unselected_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            pair = model_capture_fixture(
                Path(tmp),
                model='gpt-6-astra',
                reasoning_effort='ultra',
                request_model_field='visible',
                request_effort_field='visible',
                selection_digit='4',
            )
            for field, kwargs in (
                ('model-hidden', {'capture_model_field': 'hidden', 'capture_effort_field': 'visible'}),
                ('model-missing', {'capture_effort_field': 'visible'}),
                ('effort-hidden', {'capture_model_field': 'visible', 'capture_effort_field': 'hidden'}),
                ('effort-missing', {'capture_model_field': 'visible'}),
            ):
                with self.subTest(field=field), self.assertRaises(ValueError):
                    pair['capture'](**kwargs)
        for label, model, effort, digit in (
            ('model-only-all-visible', 'gpt-6-astra', None, '5'),
            ('effort-only-all-visible', None, 'high', '6'),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                case = model_capture_fixture(
                    Path(tmp),
                    model=model,
                    reasoning_effort=effort,
                    request_model_field='visible',
                    request_effort_field='visible',
                    selection_digit=digit,
                )
                result = case['capture'](
                    capture_model_field='visible',
                    capture_effort_field='visible',
                )
                expected_fields = [
                    field
                    for field, selected in (
                        ('model', model),
                        ('reasoning_effort', effort),
                    )
                    if selected is not None
                ]
                self.assertEqual(
                    result['host_model_execution_binding'][
                        'applied_spawn_fields'
                    ],
                    expected_fields,
                )

    def test_model_capture_turn_context_pending_and_fatal_matrix(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = model_capture_fixture(
                Path(tmp),
                model='gpt-6-astra',
                reasoning_effort='ultra',
                request_model_field='visible',
                request_effort_field='visible',
                selection_digit='7',
            )
            case['child_rows'].pop(1)
            case['save']()
            with self.assertRaises(NativeEvidencePending):
                case['capture'](
                    capture_model_field='visible',
                    capture_effort_field='visible',
                )
        for field in ('model', 'effort'):
            with self.subTest(child_mismatch=field), tempfile.TemporaryDirectory() as tmp:
                case = model_capture_fixture(
                    Path(tmp),
                    model='gpt-6-astra',
                    reasoning_effort='ultra',
                    request_model_field='visible',
                    request_effort_field='visible',
                    selection_digit='8',
                )
                case['child_rows'][1]['payload'][field] = 'foreign-' + field
                case['save']()
                with self.assertRaises(ValueError):
                    case['capture'](
                        capture_model_field='visible',
                        capture_effort_field='visible',
                    )
        for mutation in ('missing', 'foreign', 'ambiguous', 'after-spawn'):
            with self.subTest(parent=mutation), tempfile.TemporaryDirectory() as tmp:
                case = model_capture_fixture(
                    Path(tmp),
                    model='gpt-6-astra',
                    reasoning_effort='ultra',
                    request_model_field='visible',
                    request_effort_field='visible',
                    selection_digit='9',
                )
                if mutation == 'missing':
                    case['parent_rows'].pop(1)
                elif mutation == 'foreign':
                    case['parent_rows'][1]['payload']['thread_id'] = CHILD
                elif mutation == 'ambiguous':
                    duplicate = copy.deepcopy(case['parent_rows'][1])
                    duplicate['payload']['model'] = 'ambiguous-parent-model'
                    case['parent_rows'].insert(2, duplicate)
                else:
                    turn = case['parent_rows'].pop(1)
                    case['parent_rows'].insert(2, turn)
                case['save']()
                with self.assertRaises(ValueError):
                    case['capture'](
                        capture_model_field='visible',
                        capture_effort_field='visible',
                    )
        with tempfile.TemporaryDirectory() as tmp:
            case = model_capture_fixture(
                Path(tmp),
                model='gpt-6-astra',
                reasoning_effort='ultra',
                request_model_field='visible',
                request_effort_field='visible',
                selection_digit='a',
            )
            output = json.loads(case['parent_rows'][3]['payload']['output'])
            output['thread_id'] = 'explicit-child-not-a-uuid'
            case['parent_rows'][3]['payload']['output'] = json.dumps(output)
            case['save']()
            with self.assertRaises(ValueError):
                case['capture'](
                    capture_model_field='visible',
                    capture_effort_field='visible',
                )

    def test_model_execution_binding_receipt_layers_are_exact_and_tamper_evident(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = model_capture_fixture(
                Path(tmp),
                model='gpt-6-astra',
                reasoning_effort='ultra',
                request_model_field='visible',
                request_effort_field='visible',
                selection_digit='b',
            )
            result = case['capture'](
                capture_model_field='visible',
                capture_effort_field='visible',
            )
            receipt = result['native_host_action_receipt']
            variants = []
            missing_authorization_top = copy.deepcopy(receipt)
            missing_authorization_top.pop('model_authorization_binding')
            variants.append(('missing-authorization-top', missing_authorization_top))
            missing_authorization_result = copy.deepcopy(receipt)
            missing_authorization_result['host_result'].pop(
                'model_authorization_binding'
            )
            variants.append((
                'missing-authorization-host-result',
                missing_authorization_result,
            ))
            missing_top = copy.deepcopy(receipt)
            missing_top.pop('host_model_execution_binding')
            variants.append(('missing-top', missing_top))
            missing_result = copy.deepcopy(receipt)
            missing_result['host_result'].pop('host_model_execution_binding')
            variants.append(('missing-host-result', missing_result))
            foreign_id = copy.deepcopy(receipt)
            foreign_id['host_model_execution_binding']['selection_id'] = 'MEA-' + 'c' * 32
            variants.append(('foreign-selection-id', foreign_id))
            foreign_value = copy.deepcopy(receipt)
            foreign_value['host_result']['host_model_execution_binding'][
                'child_turn_context'
            ]['model'] = 'foreign-child-model'
            variants.append(('foreign-child-model', foreign_value))
            foreign_status = copy.deepcopy(receipt)
            foreign_status['host_model_execution_binding']['status'] = 'FOREIGN'
            variants.append(('foreign-status', foreign_status))
            coherently_forged_child = copy.deepcopy(receipt)
            for layer in (
                coherently_forged_child['host_model_execution_binding'],
                coherently_forged_child['host_result'][
                    'host_model_execution_binding'
                ],
            ):
                layer['child_turn_context']['model'] = 'gpt-forged-model'
            variants.append(('coherently-forged-child-model', coherently_forged_child))
            for label, candidate in variants:
                with self.subTest(label=label), self.assertRaises(ValueError):
                    validate_native_host_action_receipt(
                        candidate,
                        expected=receipt['request'],
                        replay_guard=set(),
                    )

    def test_explicit_model_capture_rejects_dispatch_context_replacement(self):
        with tempfile.TemporaryDirectory() as tmp:
            case = model_capture_fixture(
                Path(tmp),
                model='gpt-6-astra',
                reasoning_effort='ultra',
                request_model_field='visible',
                request_effort_field='visible',
                selection_digit='d',
            )
            arguments = json.loads(case['parent_rows'][2]['payload']['arguments'])
            message = json.loads(arguments['message'])
            message['p00']['dispatch_context']['semantic_receipt_id'] = 'SEM-TAMPERED'
            message['p00']['dispatch_context']['pointers'] = [{
                'path': 'court-runtime:tasks/foreign/charter',
                'case_ref': copy.deepcopy(message['p00']['case_ref']),
            }]
            arguments['message'] = json.dumps(
                message, ensure_ascii=False, sort_keys=True, separators=(',', ':')
            )
            case['parent_rows'][2]['payload']['arguments'] = json.dumps(arguments)
            case['save']()
            with self.assertRaisesRegex(ValueError, 'host_message_mismatch'):
                case['capture'](
                    capture_model_field='visible',
                    capture_effort_field='visible',
                )


class SkillOrderTests(unittest.TestCase):
    def test_shell_wrappers_preserve_executable_positions(self):
        for argv in (
            ['bash', '-lc', 'exec decretum-matrix court status'],
            ['pwsh.exe', '-Command', '$r = decretum-matrix court status'],
            ['python', 'bin/decretum-matrix.py', 'court', 'status'],
        ):
            with self.subTest(argv=argv):
                self.assertTrue(_invokes_court_cli(_command_text({'command': argv})))
        self.assertFalse(_invokes_court_cli(_command_text(
            {'command': ['rg', '-c', 'decretum-matrix', 'scripts']})))

    def test_startup_must_precede_both_office_materials(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = {
                kind: [str(Path(tmp) / name)]
                for kind, name in (
                    ('skill', 'SKILL.md'),
                    ('startup', 'court-normal-startup.md'),
                    ('profile', 'role.toml'),
                    ('dossier', 'AGENTS.md'),
                )
            }

            def read(kind):
                path = paths[kind][0]
                return {'type':'event_msg','payload':{'type':'item_completed','item':{
                    'type':'CommandExecution','id':'read-'+kind,'status':'completed','exit_code':0,
                    'command':['Get-Content',path],
                    'parsed_cmd':[{'type':'read','path':path,'cmd':'Get-Content -Raw'}]}}}

            valid = skill_read_order(
                [read('skill'), read('startup'), read('dossier'), read('profile')],
                paths,
            )
            self.assertEqual(set(valid['read_events']), set(paths))
            with self.assertRaisesRegex(
                ValueError,
                'startup_must_load_before_office_materials',
            ):
                skill_read_order(
                    [read('skill'), read('profile'), read('startup'), read('dossier')],
                    paths,
                )

    def test_direct_niu_cat_observes_startup_between_skill_and_office_materials(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = {
                kind: [str(Path(tmp) / name)]
                for kind, name in (
                    ('skill', 'SKILL.md'),
                    ('startup', 'court-normal-startup.md'),
                    ('profile', 'role.toml'),
                    ('dossier', 'AGENTS.md'),
                )
            }

            def powershell_read(kind):
                path = paths[kind][0]
                return {'type':'event_msg','payload':{'type':'item_completed','item':{
                    'type':'CommandExecution','id':'read-'+kind,'status':'completed','exit_code':0,
                    'command':['Get-Content',path],
                    'parsed_cmd':[{'type':'read','path':path,'cmd':'Get-Content -Raw'}]}}}

            startup_path = paths['startup'][0]
            niu_command = ['niu.exe', '-c', "cat '" + startup_path + "'"]
            niu_startup = {'type':'event_msg','payload':{'type':'item_completed','item':{
                'type':'CommandExecution','id':'read-startup','status':'completed','exit_code':0,
                'command':niu_command,
                'parsed_cmd':[{'type':'unknown','cmd':' '.join(niu_command)}]}}}
            try:
                result = skill_read_order(
                    [powershell_read('skill'), niu_startup,
                     powershell_read('profile'), powershell_read('dossier')],
                    paths,
                )
            except NativeEvidencePending as exc:
                self.fail(
                    'a successful direct niu.exe -c cat of the exact startup path '
                    f'must be observed as a full read: {exc}'
                )
            self.assertEqual(
                tuple(result['read_events']),
                ('skill', 'startup', 'profile', 'dossier'),
            )

    def test_direct_niu_court_cli_before_preload_is_business(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = {
                kind: [str(Path(tmp) / name)]
                for kind, name in (
                    ('skill', 'SKILL.md'),
                    ('startup', 'court-normal-startup.md'),
                    ('profile', 'role.toml'),
                    ('dossier', 'AGENTS.md'),
                )
            }

            def powershell_read(kind):
                path = paths[kind][0]
                return {'type':'event_msg','payload':{'type':'item_completed','item':{
                    'type':'CommandExecution','id':'read-'+kind,'status':'completed','exit_code':0,
                    'command':['Get-Content',path],
                    'parsed_cmd':[{'type':'read','path':path,'cmd':'Get-Content -Raw'}]}}}

            niu_cli = {'type':'event_msg','payload':{'type':'item_completed','item':{
                'type':'CommandExecution','id':'business-before-preload','status':'completed','exit_code':0,
                'command':['niu', '-c', 'decretum-matrix court status'],
                'parsed_cmd':[{'type':'unknown','cmd':'niu -c decretum-matrix court status'}]}}}
            reads = [powershell_read(kind) for kind in ('skill', 'startup', 'profile', 'dossier')]
            with self.assertRaisesRegex(ValueError, 'skill_must_load_before_cli_mcp'):
                skill_read_order([niu_cli, *reads], paths)

    def test_powershell_wrapped_exact_niu_read_and_business_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = {
                kind: [str(Path(tmp) / name)]
                for kind, name in (
                    ('skill', 'SKILL.md'),
                    ('startup', 'court-normal-startup.md'),
                    ('profile', 'role.toml'),
                    ('dossier', 'AGENTS.md'),
                )
            }

            def powershell_read(kind):
                path = paths[kind][0]
                return {'type':'event_msg','payload':{'type':'item_completed','item':{
                    'type':'CommandExecution','id':'read-'+kind,'status':'completed','exit_code':0,
                    'command':['Get-Content',path],
                    'parsed_cmd':[{'type':'read','path':path,'cmd':'Get-Content -Raw'}]}}}

            niu_path = r'C:\TOOLS\NIUBASH\NIU.EXE'

            def quote(value):
                return "'" + value.replace("'", "''") + "'"

            def wrapped(payload, event_id):
                outer = '& ' + quote(niu_path) + ' -c ' + quote(payload)
                return {'type':'event_msg','payload':{'type':'item_completed','item':{
                    'type':'CommandExecution','id':event_id,'status':'completed','exit_code':0,
                    'command':['pwsh', '-Command', outer],
                    'parsed_cmd':[{'type':'unknown','cmd':outer}]}}}

            startup_payload = 'cat ' + quote(paths['startup'][0])
            with self.subTest(kind='full-read'):
                try:
                    result = skill_read_order(
                        [powershell_read('skill'), wrapped(startup_payload, 'read-startup'),
                         powershell_read('profile'), powershell_read('dossier')],
                        paths,
                    )
                except NativeEvidencePending as exc:
                    self.fail(
                        'the exact PowerShell argv wrapper around literal NIU cat '
                        f'must be observed as a full startup read: {exc}'
                    )
                self.assertEqual(result['read_events']['startup'], 'read-startup')

            for business_payload in (
                'decretum-matrix court status',
                'python -B scripts/court_cli.py court status',
            ):
                with self.subTest(kind='business-order', payload=business_payload):
                    reads = [
                        powershell_read(kind)
                        for kind in ('skill', 'startup', 'profile', 'dossier')
                    ]
                    with self.assertRaisesRegex(ValueError, 'skill_must_load_before_cli_mcp'):
                        skill_read_order(
                            [wrapped(business_payload, 'business-before-preload'), *reads],
                            paths,
                        )

    def test_powershell_wrapped_niu_dangerous_grammar_is_never_a_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            startup = str((Path(tmp) / 'court-normal-startup.md').resolve())
            other = str((Path(tmp) / 'other.md').resolve())
            marker = Path(tmp) / 'PARSER_MUST_NOT_EXECUTE'
            niu_path = r'C:\tools\niubash\niu.exe'

            def quote(value):
                return "'" + value.replace("'", "''") + "'"

            def item(payload, *, switch='-c', dynamic_executable=False):
                executable = '$niu' if dynamic_executable else quote(niu_path)
                outer = '& ' + executable + ' ' + switch + ' ' + quote(payload)
                return {
                    'command': ['pwsh', '-Command', outer],
                    'parsed_cmd': [{'type':'unknown','cmd':outer}],
                }

            cases = (
                ('dollar-variable', "cat '$STARTUP'", '-c', False),
                ('braced-variable', "cat '${STARTUP}'", '-c', False),
                ('percent-variable', "cat '%STARTUP%'", '-c', False),
                ('command-substitution', "cat '$(Get-Content x)'", '-c', False),
                ('backtick', "cat '`pwd`/court-normal-startup.md'", '-c', False),
                ('tilde', "cat '~/court-normal-startup.md'", '-c', False),
                ('brace-expansion', "cat '/tmp/{a,b}.md'", '-c', False),
                ('glob-star', "cat '/tmp/*.md'", '-c', False),
                ('glob-question', "cat '/tmp/?.md'", '-c', False),
                ('glob-bracket', "cat '/tmp/[ab].md'", '-c', False),
                ('traversal', "cat '/tmp/../court-normal-startup.md'", '-c', False),
                ('pipe', 'cat ' + quote(startup) + ' | head -n 1', '-c', False),
                ('redirect-out', 'cat ' + quote(startup) + ' > out.txt', '-c', False),
                ('redirect-in', 'cat < ' + quote(startup), '-c', False),
                ('semicolon', 'cat ' + quote(startup) + '; echo bad', '-c', False),
                ('newline', 'cat ' + quote(startup) + '\necho bad', '-c', False),
                ('multi-command', 'cat ' + quote(startup) + ' && cat ' + quote(other), '-c', False),
                ('multi-path', 'cat ' + quote(startup) + ' ' + quote(other), '-c', False),
                ('cat-option', 'cat -n ' + quote(startup), '-c', False),
                ('cat-double-dash', 'cat -- ' + quote(startup), '-c', False),
                ('head', 'head -n 1 ' + quote(startup), '-c', False),
                ('tail', 'tail -n 1 ' + quote(startup), '-c', False),
                ('sed', 'sed -n 1p ' + quote(startup), '-c', False),
                ('awk', 'awk 1 ' + quote(startup), '-c', False),
                ('cut', 'cut -c 1-2 ' + quote(startup), '-c', False),
                ('less', 'less ' + quote(startup), '-c', False),
                ('more', 'more ' + quote(startup), '-c', False),
                ('non-exact-lc', 'cat ' + quote(startup), '-lc', False),
                ('non-exact-ic', 'cat ' + quote(startup), '-ic', False),
                ('nested-shell', 'bash -lc "cat ' + quote(startup) + '"', '-c', False),
                ('dynamic-executable', 'cat ' + quote(startup), '-c', True),
                ('no-execution', 'cat ' + quote(startup) + '; touch ' + quote(str(marker)), '-c', False),
            )
            for label, payload, switch, dynamic in cases:
                with self.subTest(label=label):
                    observed_payload = _direct_niu_payload(
                        item(payload, switch=switch, dynamic_executable=dynamic)
                    )
                    observed_read = (
                        _static_niu_cat_read(observed_payload)
                        if observed_payload is not None
                        else None
                    )
                    self.assertIsNone(
                        observed_read,
                        f'{label} must remain unobserved as a full read',
                    )
            untrusted_niu = str((Path(tmp) / 'other-tools' / 'niu.exe').resolve())
            untrusted_outer = '& ' + quote(untrusted_niu) + ' -c ' + quote(
                'cat ' + quote(startup)
            )
            self.assertIsNone(
                _direct_niu_payload({
                    'command': ['pwsh', '-Command', untrusted_outer],
                    'parsed_cmd': [{'type': 'unknown', 'cmd': untrusted_outer}],
                }),
                'PowerShell wrapper trusted an arbitrary absolute niu.exe path',
            )
            self.assertFalse(marker.exists(), 'static parsing executed shell text')

    def test_captured_ack_requires_active_install_and_child_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            rows, meta, context, save, capture = fixture(home)
            captured = capture()['host_spawn_evidence']
            root = home/'skills/decretum-matrix'; root.mkdir(parents=True); write_skill(root)
            startup = root/'references/court-normal-startup.md'
            startup.parent.mkdir(parents=True, exist_ok=True)
            startup.write_text('# Isolated startup fixture\n', encoding='utf-8')
            manifest = build_preload_manifest('zhongshu', skill_root=root)
            record = {'native_host_spawn_evidence':captured,'role':'zhongshu','office_instance_id':'instance',
                      'native_host_request_ref':{'court_code':'ZL-20260906-0001-TEST','office_instance_id':'instance','dispatch_uid':'DSP-test','attempt':1}}
            trace = next((home/'sessions').rglob(f'*{CHILD}.jsonl'))
            header = json.loads(trace.read_text(encoding='utf-8'))
            reads = []
            for kind, path in [('skill',manifest.court_skill_path),('startup',manifest.startup_guide_path),
                               ('profile',manifest.profile_source),('dossier',manifest.dossier_path)]:
                reads.append({'type':'event_msg','payload':{'type':'item_completed','thread_id':CHILD,
                    'item':{'type':'CommandExecution','id':'read-'+kind,'status':'completed','exit_code':0,
                    'command':['Get-Content -Raw'],'parsed_cmd':[{'type':'read','cmd':'Get-Content -Raw','path':str(root/path)}]}}})
            ack = {'schema':'court.child_preload_acceptance.v1','task_id':'test','role_key':'zhongshu',
                'office_instance_id':'instance','request_ref':{'court_code':'ZL-20260906-0001-TEST','office_instance_id':'instance','dispatch_uid':'DSP-test','attempt':1},
                'skill_loaded':True,'startup_guide_loaded':True,
                'profile_loaded':True,'dossier_loaded':True}
            event = {'type':'event_msg','payload':{'type':'item_completed','thread_id':CHILD,
                'item':{'type':'AgentMessage','phase':'commentary','id':'ack','content':[{'type':'Text','text':json.dumps(ack)}]}}}
            output = {'type':'response_item','payload':{'type':'message','role':'assistant','phase':'commentary',
                'id':'ack','content':[{'type':'output_text','text':json.dumps(ack)}]}}
            def write(values):trace.write_text('\n'.join(json.dumps(row) for row in [header,*values])+'\n',encoding='utf-8')
            def acceptance_rows(value):
                detailed_event, detailed_output = copy.deepcopy(event), copy.deepcopy(output)
                text = json.dumps(value)
                detailed_event['payload']['item']['content'][0]['text'] = text
                detailed_output['payload']['content'][0]['text'] = text
                return [detailed_event, detailed_output]
            with patch.dict(os.environ,{'CODEX_HOME':str(home),'CODEX_THREAD_ID':SESSION,'CODEX_SESSION_ID':SESSION}):
                write(reads)
                with self.assertRaisesRegex(NativeEvidencePending,'child_acceptance_not_observed'):
                    bridge.captured_child_read_order(record,manifest,task_id='test')
                write([*reads,event,output])
                with self.subTest(case='complete'):
                    complete = bridge.captured_child_read_order(record,manifest,task_id='test')
                    self.assertEqual(complete['child_acceptance_event'],'ack')
                    self.assertEqual(complete['read_events'].get('startup'), 'read-startup')
                without_startup = [row for row in reads if row['payload']['item']['id'] != 'read-startup']
                with self.subTest(case='missing-startup-read'), self.assertRaises(NativeEvidencePending):
                    write([*without_startup, event, output])
                    bridge.captured_child_read_order(record,manifest,task_id='test')
                wrong_startup = copy.deepcopy(reads)
                wrong_startup[1]['payload']['item']['parsed_cmd'][0]['path'] = str(root/'references/wrong.md')
                with self.subTest(case='wrong-startup-read'), self.assertRaises(NativeEvidencePending):
                    write([*wrong_startup, event, output])
                    bridge.captured_child_read_order(record,manifest,task_id='test')
                for label, changed_ack in (
                    ('missing-startup-loaded', {key:value for key,value in ack.items()
                                                if key != 'startup_guide_loaded'}),
                    ('startup-loaded-false', {**ack, 'startup_guide_loaded':False}),
                ):
                    with self.subTest(case=label), self.assertRaises(NativeEvidencePending):
                        write([*reads, *acceptance_rows(changed_ack)])
                        bridge.captured_child_read_order(record,manifest,task_id='test')
                source_reads = copy.deepcopy(reads)
                source_reads[0]['payload']['item']['parsed_cmd'][0]['path']=str(home/'source/SKILL.md')
                write([*source_reads,event,output])
                with self.assertRaises(NativeEvidencePending):bridge.captured_child_read_order(record,manifest,task_id='test')

    def test_batch_read_and_child_origin_ack(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = {k: [str(Path(tmp)/name)] for k,name in [('skill','SKILL.md'),('profile','role.toml'),('dossier','AGENTS.md')]}
            def command(text, parsed):
                return {'type':'event_msg','payload':{'type':'item_completed','thread_id':CHILD,
                    'item':{'type':'CommandExecution','id':text,'command':[text],'parsed_cmd':parsed,
                            'exit_code':0,'status':'completed'}}}
            skill = command('Get-Content -Raw', [{'type':'read','path':paths['skill'][0],'cmd':'Get-Content -Raw'}])
            batch_text = '; '.join("Get-Content -LiteralPath '"+paths[k][0]+"' -Raw" for k in ('profile','dossier'))
            batch = command(batch_text, [{'type':'unknown','cmd':batch_text}])
            ack = {'schema':'court.child_preload_acceptance.v1','task_id':'test','role_key':'zhongshu',
                'office_instance_id':'instance','request_ref':{'court_code':'ZL-20260906-0001-TEST','office_instance_id':'instance','dispatch_uid':'DSP-test','attempt':1},
                'skill_loaded':True,'profile_loaded':True,'dossier_loaded':True}
            event = {'type':'event_msg','payload':{'type':'item_completed','thread_id':CHILD,
                'item':{'type':'AgentMessage','id':'child-acceptance','phase':'commentary','content':[{'type':'Text','text':json.dumps(ack)}]}}}
            output = {'type':'response_item','payload':{'type':'message','role':'assistant','phase':'commentary',
                'id':'child-acceptance','content':[{'type':'output_text','text':json.dumps(ack)}]}}
            rows = [skill,batch,event,output]
            def verify(values):
                return skill_read_order(values,paths,child_ack=ack,child_thread_id=CHILD)
            self.assertEqual(verify(rows)['child_acceptance_event'],'child-acceptance')
            def with_ack(value):
                detailed_event, detailed_output = copy.deepcopy(event), copy.deepcopy(output)
                detailed_event['payload']['item']['content'][0]['text'] = json.dumps(value)
                detailed_output['payload']['content'][0]['text'] = json.dumps(value)
                return [skill, batch, detailed_event, detailed_output]
            detailed = {**ack, 'note': 'Additional read details do not grant authority.'}
            self.assertEqual(verify(with_ack(detailed))['child_acceptance_event'],'child-acceptance')
            for changes in ({'task_id':'foreign'}, {'profile_loaded':False},
                            {'request_ref':{**ack['request_ref'],'attempt':2}}):
                with self.assertRaises(NativeEvidencePending): verify(with_ack({**detailed, **changes}))
            missing = dict(detailed); missing.pop('skill_loaded')
            with self.assertRaises(NativeEvidencePending): verify(with_ack(missing))
            for lookup in (
                "rg -n -m 5 -A 8 -B 2 'decretum-matrix' CODE_CAPABILITY_INDEX.md",
                "Get-Command decretum-matrix",
                "Write-Output 'decretum-matrix court status'",
            ):
                with self.subTest(lookup=lookup):
                    self.assertEqual(verify([command(lookup, []), *rows])['child_acceptance_event'],
                                     'child-acceptance')
            mixed = command('Get-Content full batch', [*skill['payload']['item']['parsed_cmd'], *batch['payload']['item']['parsed_cmd']])
            self.assertEqual(verify([mixed,event,output])['child_acceptance_event'],'child-acceptance')
            for option in ('', '-Path ', '-LiteralPath '):
                for separator in ('; ', '\n', '\r\n'):
                    text=separator.join("Get-Content -Raw -Encoding UTF8 "+option+"'"+paths[k][0]+"'" for k in ('profile','dossier'))
                    observed=command(text,[{'type':'unknown','cmd':text}])
                    with self.subTest(option=option,separator=separator):
                        self.assertEqual(verify([skill,observed,event,output])['child_acceptance_event'],'child-acceptance')
            with self.assertRaises(NativeEvidencePending):verify([skill,batch,event,{'type':'unrelated'},output])
            with self.assertRaises(NativeEvidencePending): verify(rows[:2])
            wrong = copy.deepcopy(event); wrong['payload']['thread_id']=SESSION
            with self.assertRaises(NativeEvidencePending): verify([skill,batch,wrong])
            with self.assertRaises(ValueError): verify([event,output,skill,batch])
            incoming = copy.deepcopy(output); incoming['payload']['role']='user'
            with self.assertRaises(NativeEvidencePending): verify([skill,batch,event,incoming])
            with self.assertRaises(NativeEvidencePending): verify([skill,batch,event])
            for alias in ('agent-report','agent-start','agent-finish','create','office report','court status'):
                cli=command('decretum-matrix '+alias,[])
                with self.subTest(alias=alias), self.assertRaises(ValueError):verify([cli,*rows])
                with self.subTest(alias=alias), self.assertRaises(ValueError):verify([skill,cli,batch,event])
            for entrance in ('python -B scripts/court_cli.py', 'python -B scripts/court_runtime.py',
                             'node bin/decretum-matrix.js',
                             "& 'C:/Program Files/court/decretum-matrix.cmd'",
                             "rg 'decretum-matrix' index.md; decretum-matrix",
                             "$result = decretum-matrix", "$result=decretum-matrix",
                             "try { decretum-matrix"):
                with self.subTest(entrance=entrance), self.assertRaises(ValueError):
                    verify([command(entrance+' agent-report', []), *rows])
            for suffix in (' | Select-Object -First 1', ' -TotalCount 2'):
                bad=command(batch_text+suffix,[{'type':'unknown','cmd':batch_text+suffix}])
                with self.assertRaises(NativeEvidencePending):verify([skill,bad,event])
            fake=command("Write-Output '"+batch_text+"'",[{'type':'unknown','cmd':"Write-Output '"+batch_text+"'"}])
            with self.assertRaises(NativeEvidencePending):verify([skill,fake,event])

    def test_skill_and_own_materials_precede_business_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths={k:[str(Path(tmp)/name)] for k,name in [('skill','SKILL.md'),('profile','role.toml'),('dossier','AGENTS.md')]}
            def read(kind):
                return {'type':'event_msg','payload':{'type':'item_completed','item':{'type':'CommandExecution',
                    'id':'read-'+kind,'status':'completed','exit_code':0,'command':['Get-Content',paths[kind][0]],
                    'parsed_cmd':[{'type':'read','path':paths[kind][0],'cmd':'Get-Content -Raw'}]}}}
            tool={'type':'event_msg','payload':{'type':'item_started','item':{'type':'McpToolCall','id':'mcp'}}}
            rows=[read('skill'),read('profile'),read('dossier'),tool]
            self.assertEqual(skill_read_order(rows,paths)['status'],'HOST_READ_EVENTS_OBSERVED')
            for bad in ([tool,*rows[:3]],[rows[1],rows[0],rows[2]],rows[:2],
                        [rows[0],tool,rows[1],rows[2]]):
                with self.assertRaises(ValueError):skill_read_order(bad,paths)
            preview=copy.deepcopy(rows);preview[0]['payload']['item']['parsed_cmd'][0]['cmd']='Get-Content -TotalCount 3'
            with self.assertRaises(ValueError):skill_read_order(preview,paths)


if __name__=='__main__':unittest.main()
