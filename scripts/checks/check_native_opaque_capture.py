"""Opaque host storage and skill-before-tool order regressions; no file hashes."""
from pathlib import Path
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import copy
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from commands import court_native_bridge as bridge
from checks.check_court_native_bridge import _request, _execution, _p00_context
from court_native_host_dispatch import validate_native_host_action_receipt
from court_native_trace import skill_read_order, NativeEvidencePending
from court_office_bootstrap import build_preload_manifest
from checks.installed_identity_fixture import write_skill

SESSION = '01a0743b-4c11-7021-b2ad-31f2dfe23df5'
PARENT = '01a07440-9c7d-7b52-b53a-51edbd68e6da'
CHILD = '01a0743f-9c12-7842-bfec-8620bf6942c4'


def fixture(home: Path, *, ministry=False, root_distinct=False):
    request = _request()
    if not ministry:
        request.update(role='zhongshu', direct_superior='taizi')
        request['role_ack'].update(role='zhongshu', direct_superior='taizi')
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
            args = json.loads(rows[1]['payload']['arguments'])
            args['message'] = bridge.canonical_host_message(request, execution=_execution(), p00_context=_p00_context(request))
            rows[1]['payload']['arguments'] = json.dumps(args); save()
            evidence = capture()['host_spawn_evidence']
            self.assertEqual(evidence['message_verification'], 'PLAINTEXT_EXACT_MATCHED')
            self.assertEqual(evidence['request_delivery'], 'PENDING_PRELOAD_ACK')
        with self.assertRaises(NativeEvidencePending):
            bridge.captured_child_read_order({'native_host_action_receipt_id':'legacy-plaintext'}, object())


class SkillOrderTests(unittest.TestCase):
    def test_captured_ack_requires_active_install_and_child_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            rows, meta, context, save, capture = fixture(home)
            captured = capture()['host_spawn_evidence']
            root = home/'skills/decretum-matrix'; root.mkdir(parents=True); write_skill(root)
            manifest = build_preload_manifest('zhongshu', skill_root=root)
            record = {'native_host_spawn_evidence':captured,'role':'zhongshu','office_instance_id':'instance',
                      'native_host_request_sha256':'a'*64}
            trace = next((home/'sessions').rglob(f'*{CHILD}.jsonl'))
            header = json.loads(trace.read_text(encoding='utf-8'))
            reads = []
            for kind, path in [('skill',manifest.court_skill_path),('profile',manifest.profile_source),('dossier',manifest.dossier_path)]:
                reads.append({'type':'event_msg','payload':{'type':'item_completed','thread_id':CHILD,
                    'item':{'type':'CommandExecution','id':'read-'+kind,'status':'completed','exit_code':0,
                    'command':['Get-Content -Raw'],'parsed_cmd':[{'type':'read','cmd':'Get-Content -Raw','path':str(root/path)}]}}})
            ack = {'schema':'court.child_preload_acceptance.v1','task_id':'test','role_key':'zhongshu',
                'office_instance_id':'instance','request_sha256':'a'*64,
                'skill_loaded':True,'profile_loaded':True,'dossier_loaded':True}
            event = {'type':'event_msg','payload':{'type':'item_completed','thread_id':CHILD,
                'item':{'type':'AgentMessage','phase':'commentary','id':'ack','content':[{'type':'Text','text':json.dumps(ack)}]}}}
            output = {'type':'response_item','payload':{'type':'message','role':'assistant','phase':'commentary',
                'id':'ack','content':[{'type':'output_text','text':json.dumps(ack)}]}}
            def write(values):trace.write_text('\n'.join(json.dumps(row) for row in [header,*values])+'\n',encoding='utf-8')
            with patch.dict(os.environ,{'CODEX_HOME':str(home),'CODEX_THREAD_ID':SESSION,'CODEX_SESSION_ID':SESSION}):
                write(reads)
                with self.assertRaisesRegex(NativeEvidencePending,'child_acceptance_not_observed'):
                    bridge.captured_child_read_order(record,manifest,task_id='test')
                write([*reads,event,output])
                self.assertEqual(bridge.captured_child_read_order(record,manifest,task_id='test')['child_acceptance_event'],'ack')
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
                'office_instance_id':'instance','request_sha256':'a'*64,
                'skill_loaded':True,'profile_loaded':True,'dossier_loaded':True}
            event = {'type':'event_msg','payload':{'type':'item_completed','thread_id':CHILD,
                'item':{'type':'AgentMessage','id':'child-acceptance','phase':'commentary','content':[{'type':'Text','text':json.dumps(ack)}]}}}
            output = {'type':'response_item','payload':{'type':'message','role':'assistant','phase':'commentary',
                'id':'child-acceptance','content':[{'type':'output_text','text':json.dumps(ack)}]}}
            rows = [skill,batch,event,output]
            def verify(values):
                return skill_read_order(values,paths,child_ack=ack,child_thread_id=CHILD)
            self.assertEqual(verify(rows)['child_acceptance_event'],'child-acceptance')
            mixed = command('Get-Content full batch', [*skill['payload']['item']['parsed_cmd'], *batch['payload']['item']['parsed_cmd']])
            self.assertEqual(verify([mixed,event,output])['child_acceptance_event'],'child-acceptance')
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
                             'node bin/decretum-matrix.js'):
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
