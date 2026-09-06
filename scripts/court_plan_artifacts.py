"""Immutable plans and distinct Three-Departments evidence in existing tasks.

This library owns no ledger or dispatcher. Callers commit its copied task through
the existing runtime transaction; actual host acceptance is verified separately.
"""
from __future__ import annotations
from copy import deepcopy
import json
import sys
import uuid
from typing import Any, Mapping
sys.dont_write_bytecode = True

PLAN_SCHEMA = 'court.zhongshu_plan.v1'

def bootstrap_artifact(task: Mapping[str, Any]) -> dict[str, Any]:
    """A named intake projection, explicitly not a Zhongshu plan."""
    value = {'schema': 'court.case_bootstrap.v1', 'plan_status': 'BOOTSTRAP_UNPLANNED',
             'task_id': task['task_id'], 'court_code': task['court_code'],
             'charter_revision': task['charter_revision']}
    return value


def _text(value: object, field: str, limit: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit or (value.startswith('<') and value.endswith('>')):
        raise ValueError('case_plan_invalid_' + field)
    return value


def _texts(value: object, field: str, *, empty: bool = False) -> list[str]:
    if not isinstance(value, list) or len(value) > 32 or (not value and not empty):
        raise ValueError('case_plan_invalid_' + field)
    return [_text(item, field) for item in value]


def validate_document(value: object) -> dict[str, Any]:
    from court_office_bootstrap import OFFICE_ASSIGNMENT_IDENTITIES
    fields = {'goal', 'non_goals', 'steps', 'acceptance', 'write_set'}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError('case_plan_document_fields_invalid')
    steps = value['steps']
    if not isinstance(steps, list) or not 1 <= len(steps) <= 32:
        raise ValueError('case_plan_steps_required')
    ids = set()
    for step in steps:
        if not isinstance(step, dict) or set(step) != {'id', 'role', 'action'}:
            raise ValueError('case_plan_step_fields_invalid')
        key = _text(step['id'], 'step_id', 80)
        if key in ids or step['role'] not in OFFICE_ASSIGNMENT_IDENTITIES:
            raise ValueError('case_plan_step_identity_invalid')
        ids.add(key)
        _text(step['action'], 'step_action')
    document = {'goal': _text(value['goal'], 'goal'),
                'non_goals': _texts(value['non_goals'], 'non_goals', empty=True),
                'steps': deepcopy(steps), 'acceptance': _texts(value['acceptance'], 'acceptance'),
                'write_set': _texts(value['write_set'], 'write_set', empty=True)}
    if len(json.dumps(document, ensure_ascii=False).encode('utf-8')) > 16384:
        raise ValueError('case_plan_document_too_large')
    return document


def _current_charter(record: Mapping[str, Any], task: Mapping[str, Any]) -> bool:
    """Check the current case version without content-digest references."""
    revision = record.get('charter_revision', record.get('semantic_epoch'))
    epoch = record.get('semantic_epoch', revision)
    task_epoch = task.get('semantic_epoch', task.get('charter_revision'))
    return (type(revision) is int and revision == task.get('charter_revision')
            and type(epoch) is int and type(task_epoch) is int and epoch == task_epoch == revision
            and record.get('court_code') == task.get('court_code'))


def _producer(task: Mapping[str, Any], role: str, value: object, events: list[dict[str, Any]]) -> dict[str, str]:
    if not isinstance(value, dict) or set(value) != {'kind', 'agent_id', 'evidence'}:
        raise ValueError('case_plan_producer_fields_invalid')
    evidence = _text(value['evidence'], 'producer_evidence')
    if value['kind'] == 'serial_inline':
        execution = task.get('case_execution', {})
        if execution.get('behavior') != 'serial' or value['agent_id']:
            raise ValueError('case_plan_serial_inline_not_selected')
        return {'kind': 'serial_inline', 'role': role, 'agent_id': '', 'evidence': evidence}
    if value['kind'] != 'host_report':
        raise ValueError('case_plan_real_office_report_required')
    agent_id = _text(value['agent_id'], 'agent_id', 256)
    agent = task.get('agents', {}).get(agent_id, {})
    if (agent.get('task_id', task.get('task_id')) != task.get('task_id')
            or agent.get('role') != role or agent.get('direct_superior') != 'taizi'
            or agent.get('preload_status') != 'PASSED' or agent.get('office_execution_ready') is not True
            or not _current_charter(agent, task)):
        raise ValueError('case_plan_current_office_report_required')
    matching = [event for event in events if event.get('action') == 'agent_report'
                and event.get('task_id') == task.get('task_id') and _current_charter(event, task)
                and event.get('agent_role') == role and event.get('agent_id') == agent_id
                and event.get('evidence') == evidence]
    if len(matching) != 1:
        raise ValueError('case_plan_report_event_required')
    result = {'kind': 'host_report', 'role': role, 'agent_id': agent_id, 'evidence': evidence}
    if isinstance(task.get('case_binding'), dict):
        receipt_id = agent.get('native_host_action_receipt_id')
        stored = task.get('native_host_action_receipts', {}).get(receipt_id, {})
        canonical = agent.get('native_host_identity_kind') == 'canonical_agent_path'
        identity = agent.get('native_host_instance_id') if canonical else agent.get('native_host_thread_id')
        if (not receipt_id or not identity
                or stored.get('target_id') != agent_id):
            raise ValueError('case_plan_native_delivery_receipt_required')
        if canonical:
            if agent.get('native_host_thread_id') is not None:
                raise ValueError('case_plan_canonical_path_is_not_a_thread')
            result.update(identity_kind='canonical_agent_path', host_instance_id=identity)
        else:
            result.update(host_thread_id=identity)
        result['native_receipt_id'] = receipt_id
    return result


def current_plan(task: Mapping[str, Any]) -> dict[str, Any] | None:
    plan = task.get('zhongshu_plan')
    if plan is None:
        return None
    if not isinstance(plan, dict) or plan.get('schema') != PLAN_SCHEMA:
        raise ValueError('case_plan_artifact_invalid')
    if (plan.get('task_id') != task.get('task_id')
            or plan.get('court_code') != task.get('court_code')
            or plan.get('charter_revision') != task.get('charter_revision')
            or not isinstance(plan.get('revision'), int)
            or isinstance(plan.get('revision'), bool)
            or plan.get('revision', 0) < 1):
        raise ValueError('case_plan_artifact_stale_or_changed')
    validate_document(plan.get('document'))
    return deepcopy(plan)


def submit_plan(task: Mapping[str, Any], document: object, producer: object, events: list[dict[str, Any]]) -> dict[str, Any]:
    if task.get('state') not in {'Taizi', 'ThreeDepartments'}:
        raise ValueError('case_plan_wrong_stage')
    normalized = validate_document(document)
    author = _producer(task, 'zhongshu', producer, events)
    old = task.get('zhongshu_plan')
    if old is not None:
        if not isinstance(old, dict) or old.get('task_id') != task.get('task_id') or old.get('court_code') != task.get('court_code'):
            raise ValueError('case_plan_artifact_stale_or_changed')
    if old and old['charter_revision'] == task['charter_revision'] and old['document'] == normalized and old['producer'] == author:
        return deepcopy(task)
    revision = max([int(item['revision']) for item in task.get('zhongshu_plan_history', [])] + [int(old['revision']) if old else 0]) + 1
    artifact = {'schema': PLAN_SCHEMA, 'task_id': task['task_id'],
                'court_code': task['court_code'], 'charter_revision': task['charter_revision'],
                'plan_id': 'PLAN-' + uuid.uuid4().hex.upper(),
                'revision': revision, 'document': normalized, 'producer': author}
    updated = deepcopy(task)
    updated['zhongshu_plan'] = artifact
    updated.setdefault('zhongshu_plan_history', []).append(deepcopy(artifact))
    updated['case_reviews'] = {}
    return updated


def record_review(task: Mapping[str, Any], role: str, decision: str, plan_ref: object,
                  producer: object, events: list[dict[str, Any]]) -> dict[str, Any]:
    allowed = {'menxia': {'approved', 'rejected'}, 'shangshu': {'dispatchable', 'blocked'}}
    if task.get('state') != 'ThreeDepartments' or role not in allowed or decision not in allowed[role]:
        raise ValueError('case_plan_review_role_or_stage_invalid')
    plan = current_plan(task)
    if plan is None:
        raise ValueError('case_plan_review_foreign_or_stale')
    from court_case_binding import plan_reference
    try:
        requested_plan_ref = plan_reference(plan_ref)
    except (TypeError, ValueError) as exc:
        raise ValueError('case_plan_review_foreign_or_stale') from exc
    if requested_plan_ref != plan_reference(plan):
        raise ValueError('case_plan_review_foreign_or_stale')
    author = _producer(task, role, producer, events)
    other = [plan['producer'], *[item['producer'] for name, item in task.get('case_reviews', {}).items() if name != role]]
    if author['agent_id'] and any(item.get('agent_id') == author['agent_id'] or
            (_host_identity(author) and _host_identity(item) == _host_identity(author)) for item in other):
        raise ValueError('case_plan_departments_must_be_distinct')
    review = {'schema': 'court.plan_review.v1', 'role': role, 'decision': decision,
              'task_id': task['task_id'], 'court_code': task['court_code'],
              'charter_revision': task['charter_revision'],
              'plan_revision': plan['revision'], 'review_id': 'REV-' + uuid.uuid4().hex.upper(),
              'producer': author}
    updated = deepcopy(task)
    updated.setdefault('case_reviews', {})[role] = review
    return updated


def require_reviewed_plan(task: Mapping[str, Any]) -> dict[str, Any]:
    plan = current_plan(task)
    if plan is None:
        raise ValueError('case_plan_not_drafted')
    producers = [plan['producer']]
    for role, expected in (('menxia', 'approved'), ('shangshu', 'dispatchable')):
        review = task.get('case_reviews', {}).get(role)
        if not isinstance(review, dict):
            raise ValueError('case_plan_' + role + '_required')
        if (review.get('role') != role
                or review.get('decision') != expected or review.get('plan_revision') != plan['revision']
                or review.get('task_id') != task.get('task_id')
                or review.get('court_code') != task.get('court_code')
                or review.get('charter_revision') != task.get('charter_revision')
                or not isinstance(review.get('review_id'), str) or not review.get('review_id')):
            raise ValueError('case_plan_' + role + '_review_invalid')
        producers.append(review['producer'])
    ids = [item['agent_id'] for item in producers if item.get('kind') == 'host_report']
    if len(ids) != len(set(ids)):
        raise ValueError('case_plan_departments_must_be_distinct')
    host_ids = [_host_identity(item) for item in producers if _host_identity(item)]
    if len(host_ids) != len(set(host_ids)):
        raise ValueError('case_plan_departments_must_be_distinct')
    return plan


def _host_identity(producer: Mapping[str, Any]) -> tuple[str, str] | None:
    if producer.get('identity_kind') == 'canonical_agent_path':
        return ('canonical_agent_path', producer['host_instance_id'])
    if producer.get('host_thread_id'):
        return ('host_thread_id', producer['host_thread_id'])
    return None
