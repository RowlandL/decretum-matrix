"""Host-event evidence for opaque spawn messages without decrypting them."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
from typing import Mapping
from urllib.parse import unquote, urlsplit

SCHEMA = 'court.host_spawn_evidence.v1'
_UUID = re.compile(r'^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$', re.I)
_OPAQUE = re.compile(r'^gAAAAA[A-Za-z0-9_=-]{90,}$')
_TRUSTED_NIUBASH_WRAPPER = 'c:/tools/niubash/niu.exe'


def is_opaque_message(value: object) -> bool:
    # A storage-shape hint only, not authentication or plaintext verification.
    return isinstance(value, str) and _OPAQUE.fullmatch(value) is not None


def _uuid(value: object, field: str) -> str:
    if not isinstance(value, str) or not _UUID.fullmatch(value):
        raise ValueError('native_trace:' + field + '_invalid')
    return value.lower()


def _time(value: object) -> datetime:
    try:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('native_trace:timestamp_invalid') from exc
    if result.utcoffset() is None:
        raise ValueError('native_trace:timestamp_timezone_missing')
    return result


def spawn_activity(row: Mapping[str, object], line_number: int) -> dict[str, object] | None:
    payload = row.get('payload')
    if row.get('type') != 'event_msg' or not isinstance(payload, Mapping):
        return None
    item = payload.get('item')
    if (payload.get('type') != 'item_completed' or not isinstance(item, Mapping)
            or item.get('type') != 'SubAgentActivity' or item.get('kind') != 'started'):
        return None
    return {'call_id': item.get('id'), 'child_thread_id': item.get('agent_thread_id'),
            'child_agent_path': item.get('agent_path'), 'parent_thread_id': payload.get('thread_id'),
            'timestamp': row.get('timestamp'), 'line': line_number}


def bind_opaque_spawn(*, call_id: str, call_line: int, call_time: str,
                      activity: Mapping[str, object], child_meta: Mapping[str, object],
                      host_result: Mapping[str, object], identity_context: Mapping[str, object],
                      trace_thread_id: str) -> dict[str, object]:
    child = _uuid(activity.get('child_thread_id'), 'child_thread_id')
    parent = _uuid(activity.get('parent_thread_id'), 'parent_thread_id')
    session = _uuid(identity_context.get('case_session_id'), 'case_session_id')
    path = host_result.get('host_instance_id')
    if (activity.get('call_id') != call_id or activity.get('child_agent_path') != path
            or not isinstance(path, str) or not path.startswith('/root/')
            or parent != trace_thread_id.lower()
            or int(activity.get('line', 0)) <= call_line
            or _time(activity.get('timestamp')) < _time(call_time)):
        raise ValueError('native_trace:spawn_activity_mismatch')
    parent_path = path.rsplit('/', 1)[0]
    matches = [p for p in identity_context.get('trusted_parent_paths', [])
               if isinstance(p, Mapping) and p.get('path') == parent_path]
    if len(matches) != 1:
        raise ValueError('native_trace:parent_path_untrusted')
    expected_parent = matches[0].get('thread_id')
    if not expected_parent or parent != str(expected_parent).lower():
        raise ValueError('native_trace:parent_thread_untrusted')
    source = child_meta.get('source')
    spawn = source.get('subagent', {}).get('thread_spawn', {}) if isinstance(source, Mapping) else {}
    if (child_meta.get('id') != child or child_meta.get('session_id') != session
            or child_meta.get('parent_thread_id') != parent or child_meta.get('agent_path') != path
            or child_meta.get('thread_source') != 'subagent' or not isinstance(spawn, Mapping)
            or spawn.get('parent_thread_id') != parent or spawn.get('agent_path') != path):
        raise ValueError('native_trace:child_metadata_mismatch')
    # Source timestamp represents creation, not the later file-write time.
    if not (_time(call_time) <= _time(child_meta.get('timestamp')) <= _time(activity.get('timestamp'))):
        raise ValueError('native_trace:child_creation_order_invalid')
    return {'schema': SCHEMA, 'message_verification': 'OPAQUE_NOT_INSPECTED',
            'request_delivery': 'PENDING_PRELOAD_ACK', 'call_id': call_id,
            'child_thread_id': child, 'child_agent_path': path, 'parent_thread_id': parent,
            'parent_agent_path': parent_path, 'root_session_id': session,
            'spawn_timestamp': call_time, 'activity_timestamp': activity['timestamp'],
            'child_created_at': child_meta['timestamp'], 'source': 'host_managed_trace_metadata'}


def validate_spawn_evidence(value: object, host_identity: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(value, Mapping) or value.get('schema') != SCHEMA:
        raise ValueError('native_trace:spawn_evidence_invalid')
    result = dict(value)
    if set(result) != {'schema', 'message_verification', 'request_delivery', 'call_id',
                       'child_thread_id', 'child_agent_path', 'parent_thread_id', 'parent_agent_path',
                       'root_session_id', 'spawn_timestamp', 'activity_timestamp', 'child_created_at', 'source'}:
        raise ValueError('native_trace:spawn_evidence_fields_invalid')
    if (result.get('message_verification') not in {'OPAQUE_NOT_INSPECTED', 'PLAINTEXT_EXACT_MATCHED'}
            or result.get('request_delivery') != 'PENDING_PRELOAD_ACK'
            or result.get('source') != 'host_managed_trace_metadata'
            or host_identity.get('host_identity_kind') != 'canonical_agent_path'
            or result.get('call_id') != host_identity.get('host_action_id')
            or result.get('child_agent_path') != host_identity.get('host_instance_id')
            or result.get('root_session_id') != host_identity.get('case_session_id')
            or str(result.get('child_agent_path')).rsplit('/', 1)[0] != result.get('parent_agent_path')):
        raise ValueError('native_trace:spawn_evidence_binding_mismatch')
    for field in ('child_thread_id', 'parent_thread_id', 'root_session_id'):
        _uuid(result.get(field), field)
    if not (_time(result.get('spawn_timestamp')) <= _time(result.get('child_created_at'))
            <= _time(result.get('activity_timestamp'))):
        raise ValueError('native_trace:spawn_evidence_order_invalid')
    return result


def _path(value: object, cwd: object = None) -> str:
    if not isinstance(value, str) or not value:
        return ''
    if value.startswith('file:'):
        value = unquote(urlsplit(value).path)
        if re.match(r'^/[A-Za-z]:/', value):
            value = value[1:]
    candidate = Path(value)
    if not candidate.is_absolute() and cwd:
        candidate = Path(_path(cwd)) / candidate
    return str(candidate.resolve(strict=False)).replace('\\', '/').casefold()


class NativeEvidencePending(ValueError):
    """Missing observable host evidence can be supplied later without closing the office."""


def _static_powershell_reads(command: str) -> list[str]:
    """Parse a narrow literal Get-Content batch, without executing shell text.

    Unknown syntax is unobserved, never inferred from a read-looking substring.
    """
    tokens = []
    token = re.compile(r"[ \t\r]*(?:('(?:[^']|'')*')|(\"[^\"`$]*\")|([^\s;'\"|&<>`$(){}]+)|(;|\n))")
    position = 0
    while position < len(command.rstrip()):
        match = token.match(command, position)
        if not match:
            return []
        raw = next(value for value in match.groups() if value is not None)
        quoted = raw[:1] in {"'", '"'}
        tokens.append((raw[1:-1].replace("''", "'") if quoted else raw, quoted))
        position = match.end()
    segments = [[]]
    for value, quoted in tokens:
        if not quoted and value in {';', '\n'}:
            segments.append([])
        else:
            segments[-1].append(value)
    reads = []
    for parts in segments:
        if not parts:
            continue
        if parts.pop(0).lower() != 'get-content':
            return []
        path = None
        while parts:
            value = parts.pop(0)
            option = value.lower()
            if option == '-raw':
                continue
            if option in {'-literalpath', '-path'} and parts and path is None:
                path = parts.pop(0)
                if any(char in path for char in '*?[],') or path.startswith('-'):
                    return []
            elif option == '-encoding' and parts and parts.pop(0).lower() in {'utf8', 'utf-8', 'utf8bom', 'utf8nobom', 'unicode'}:
                continue
            elif option == '-erroraction' and parts and parts.pop(0).lower() == 'stop':
                continue
            elif path is None and not option.startswith('-'):
                path = value
                if any(char in path for char in '*?[],'):
                    return []
            else:
                return []
        if path is None:
            return []
        reads.append(path)
    return reads


def _direct_niu_payload(item: Mapping[str, object]) -> str | None:
    """Return one exact NIUbash payload; never infer or execute shell text."""

    command = item.get('command')
    if not isinstance(command, (list, tuple)) or len(command) != 3:
        return None
    executable = str(command[0]).replace('\\', '/').rsplit('/', 1)[-1].casefold()
    payload = command[2]
    if (
        executable in {'niu', 'niu.exe'}
        and command[1] == '-c'
        and isinstance(payload, str)
        and payload
        and payload == payload.strip()
        and '\x00' not in payload
    ):
        return payload
    if (
        executable not in {'pwsh', 'pwsh.exe', 'powershell', 'powershell.exe'}
        or command[1] != '-Command'
        or not isinstance(payload, str)
    ):
        return None
    match = re.fullmatch(
        r"&[ \t]+'((?:[^']|'')*)'[ \t]+-c[ \t]+'((?:[^']|'')*)'",
        payload,
    )
    if match is None:
        return None
    niu_executable = match.group(1).replace("''", "'")
    inner = match.group(2).replace("''", "'")
    niu_name = niu_executable.replace('\\', '/').rsplit('/', 1)[-1].casefold()
    normalized_niu = niu_executable.replace('\\', '/').casefold()
    if (
        niu_name != 'niu.exe'
        or normalized_niu != _TRUSTED_NIUBASH_WRAPPER
        or not Path(niu_executable).is_absolute()
        or not inner
        or inner != inner.strip()
        or any(character in niu_executable for character in ('\x00', '\r', '\n', '`', '$'))
        or any(character in inner for character in ('\x00', '\r', '\n'))
    ):
        return None
    return inner


def _static_niu_cat_read(payload: str) -> str | None:
    """Recognize only ``cat <one literal path>`` as a completed full read."""

    if any(character in payload for character in ('\r', '\n', ';', '|', '&', '<', '>', '`', '$', '(', ')')):
        return None
    match = re.fullmatch(r"cat[ \t]+(?:'([^']+)'|\"([^\"]+)\"|([^\s]+))", payload)
    if match is None:
        return None
    path = next(value for value in match.groups() if value is not None)
    if (
        not path
        or path.startswith('-')
        or any(character in path for character in ('*', '?', '[', ']', '%', '~', '{', '}'))
        or '..' in re.split(r'[\\\\/]', path)
    ):
        return None
    return path


def _command_text(item: Mapping[str, object]) -> str:
    niu_payload = _direct_niu_payload(item)
    if niu_payload is not None:
        return niu_payload
    command = item.get('command', [])
    if isinstance(command, str):
        return command
    executable = str(command[0] if command else '').replace('\\', '/').rsplit('/', 1)[-1].lower()
    if executable.removesuffix('.exe') in {'pwsh', 'powershell', 'cmd', 'sh', 'bash', 'dash', 'zsh', 'fish'}:
        for index, value in enumerate(command):
            if str(value).lower() in {'-command', '-c', '-lc', '-ic', '-ilc', '/c'} and index + 1 < len(command):
                return ' '.join(str(p) for p in command[index + 1:])
    return ' '.join(str(p) for p in command)


def _invokes_court_cli(command: str) -> bool:
    """Recognize executable positions, never search words or file arguments."""
    tokens = re.findall(r"'(?:[^']|'')*'|\"(?:[^\"`]|`.)*\"|[;&|\n{}()=]|[^\s;&|{}()=]+", command)
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token in {';', '&', '|', '\n', '{', '}', '(', ')'}:
            segments.append([])
        else:
            segments[-1].append(token.strip("'\""))
    for parts in segments:
        if not parts:
            continue
        if len(parts) > 2 and re.fullmatch(r'\$[\w:]+', parts[0]) and parts[1] == '=':
            parts = parts[2:]
        if len(parts) > 1 and parts[0] == 'exec':
            parts = parts[1:]
        executable = parts[0].replace('\\', '/').rsplit('/', 1)[-1].lower()
        if re.fullmatch(r'decretum-matrix(?:\.(?:cmd|ps1|exe|py|js|cjs|mjs))?', executable):
            return True
        if re.fullmatch(r'(?:python[\d.]*|py|node)(?:\.exe)?', executable):
            script = next((part for part in parts[1:] if not part.startswith('-')), '')
            filename = script.replace('\\', '/').rsplit('/', 1)[-1].lower()
            if filename in {'court_cli', 'court_runtime', 'court_cli.py', 'court_runtime.py',
                            'decretum-matrix.py', 'decretum-matrix.js',
                            'decretum-matrix.cjs', 'decretum-matrix.mjs'}:
                return True
    return False


def _acceptance_matches(value: object, expected: Mapping[str, object]) -> bool:
    """Require the binding and load flags; additional metadata grants no authority."""
    return (isinstance(value, dict)
            and all(key in value and value[key] == item for key, item in expected.items())
            and all(value.get(key) is True for key in ('skill_loaded', 'profile_loaded', 'dossier_loaded')))


def skill_read_order(rows: list[dict[str, object]], required: Mapping[str, list[str]],
                     *, child_ack: Mapping[str, object] | None = None,
                     child_thread_id: str | None = None) -> dict[str, object]:
    """Use host-parsed completed reads to establish the preload order."""
    reads: dict[str, tuple[int, int, str]] = {}
    business: list[int] = []
    acknowledgements: list[tuple[int, str]] = []
    candidate_outputs: dict[str, str] = {}
    candidate_lines: dict[str, int] = {}
    if child_ack is not None:
        for line, row in enumerate(rows):
            payload = row.get('payload', {})
            item = payload.get('item', {}) if isinstance(payload, Mapping) else {}
            if (row.get('type') != 'event_msg' or payload.get('type') != 'item_completed'
                    or payload.get('thread_id') != child_thread_id or not isinstance(item, Mapping)
                    or item.get('type') != 'AgentMessage' or item.get('phase') != 'commentary'):
                continue
            content = item.get('content')
            if not (isinstance(content, list) and len(content) == 1 and isinstance(content[0], Mapping)
                    and content[0].get('type') == 'Text'):
                continue
            text = content[0].get('text')
            if not isinstance(text, str) or len(text) > 4096 or not text.lstrip().startswith('{'):
                continue
            try:
                value = json.loads(text)
            except ValueError:
                continue
            if _acceptance_matches(value, child_ack):
                candidate_outputs[str(item.get('id', ''))] = text
                candidate_lines[str(item.get('id', ''))] = line
    assistant_outputs: dict[str, list[str]] = {}
    for line, row in enumerate(rows):
        output = row.get('payload', {})
        if (row.get('type') == 'response_item' and isinstance(output, Mapping)
                and output.get('id') in candidate_outputs
                and line == candidate_lines[output['id']] + 1
                and output.get('type') == 'message' and output.get('role') == 'assistant'
                and output.get('phase') == 'commentary'):
            content = output.get('content')
            if (isinstance(content, list) and len(content) == 1 and isinstance(content[0], Mapping)
                    and content[0].get('type') == 'output_text'):
                if content[0].get('text') == candidate_outputs[output['id']]:
                    assistant_outputs.setdefault(str(output['id']), []).append(candidate_outputs[output['id']])
    paths = {kind: {_path(p) for p in values} for kind, values in required.items()}
    for number, row in enumerate(rows):
        payload = row.get('payload', {})
        item = payload.get('item', {}) if isinstance(payload, Mapping) else {}
        if row.get('type') != 'event_msg' or not isinstance(item, Mapping):
            continue
        if child_thread_id is not None and payload.get('thread_id') != child_thread_id:
            continue
        item_type = str(item.get('type', '')).casefold()
        if (child_ack is not None and item_type == 'agentmessage'
                and payload.get('type') == 'item_completed' and payload.get('thread_id') == child_thread_id
                and item.get('phase') == 'commentary' and item.get('id') in candidate_outputs):
            content = item.get('content')
            if (isinstance(content, list) and len(content) == 1 and isinstance(content[0], Mapping)
                    and content[0].get('type') == 'Text'
                    and assistant_outputs.get(str(item.get('id', ''))) == [str(content[0].get('text', ''))]):
                try:
                    value = json.loads(str(content[0].get('text', '')))
                except (ValueError, TypeError):
                    value = None
                if _acceptance_matches(value, child_ack):
                    acknowledgements.append((number, str(item.get('id', ''))))
        if item_type in {'mcptoolcall', 'mcp_tool_call'}:
            business.append(number)
        if item_type != 'commandexecution':
            continue
        command = _command_text(item)
        if _invokes_court_cli(command):
            business.append(number)
        if payload.get('type') != 'item_completed' or item.get('exit_code') != 0 or item.get('status') != 'completed':
            continue
        observed = []
        niu_payload = _direct_niu_payload(item)
        if niu_payload is not None:
            niu_read = _static_niu_cat_read(niu_payload)
            if niu_read is not None:
                observed.append(niu_read)
        for parsed in item.get('parsed_cmd', []):
            if not isinstance(parsed, Mapping):
                continue
            if parsed.get('type') == 'unknown':
                observed.extend(_static_powershell_reads(str(parsed.get('cmd', ''))))
                continue
            if parsed.get('type') != 'read':
                continue
            # A preview/head/tail is not a full skill load.
            if re.search(r'(?i)-(?:TotalCount|Head|Tail|First|Last)\b|\b(?:head|tail)\b', str(parsed.get('cmd', ''))):
                continue
            observed.append(parsed.get('path'))
        for index, observed_path in enumerate(observed):
            actual = _path(observed_path, item.get('cwd'))
            for kind, accepted in paths.items():
                if actual in accepted and kind not in reads:
                    reads[kind] = (number, index, str(item.get('id', '')))
    if set(reads) != set(paths):
        raise NativeEvidencePending('native_trace:child_required_reads_not_observed')
    if any(reads['skill'][:2] > position[:2] for kind, position in reads.items() if kind != 'skill'):
        raise ValueError('native_trace:skill_must_load_before_office_materials')
    if 'startup' in reads and any(
        reads['startup'][:2] > reads[kind][:2]
        for kind in ('profile', 'dossier')
        if kind in reads
    ):
        raise ValueError('native_trace:startup_must_load_before_office_materials')
    if business and min(business) <= reads['skill'][0]:
        raise ValueError('native_trace:skill_must_load_before_cli_mcp')
    if business and min(business) <= max(position[0] for position in reads.values()):
        raise ValueError('native_trace:office_materials_must_load_before_cli_mcp')
    acknowledgement = None
    if child_ack is not None:
        if not acknowledgements:
            raise NativeEvidencePending('native_trace:child_acceptance_not_observed')
        valid = [(line, event) for line, event in acknowledgements
                 if line > max(position[0] for position in reads.values())
                 and (not business or line < min(business))]
        if not valid:
            raise ValueError('native_trace:child_acceptance_order_invalid')
        acknowledgement = valid[0][1]
    return {'schema': 'court.child_skill_read_order.v1', 'status': 'HOST_READ_EVENTS_OBSERVED',
            'read_events': {kind: data[2] for kind, data in reads.items()},
            'child_acceptance_event': acknowledgement,
            'content_attestation': 'child_preload_ack'}
