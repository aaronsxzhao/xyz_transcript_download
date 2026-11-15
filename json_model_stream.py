"""Collect a JSON model response privately; never publish partial prose."""
import json
from types import SimpleNamespace

from summary_errors import SummaryOutputError


def is_completion(value):
    return isinstance(getattr(value, 'choices', None), list)


def unsupported_stream(error):
    if getattr(error, 'status_code', None) not in (400, 422):
        return False
    detail = getattr(error, 'body', None)
    if isinstance(detail, dict) and isinstance(detail.get('error'), dict):
        detail = detail['error']
    return (isinstance(detail,dict) and detail.get('param') in ('stream','stream_options')
            and detail.get('code') in (None,'unsupported_parameter','unsupported_value','invalid_value','invalid_request_error','not_supported'))


def collect_completion(stream):
    """Require a terminal SSE event, close on every exit, retain normal clients.

    Some compatible clients return a completed response despite stream=True.
    A gateway returning application/json is also consumed once, without billing
    a second request merely because it ignored the transport flag.
    """
    if is_completion(stream):
        return stream
    events = 0
    try:
        response = getattr(stream, 'response', None)
        headers = getattr(response, 'headers', {})
        content_type = headers.get('content-type', '') if hasattr(headers, 'get') else ''
        if isinstance(content_type, str) and content_type.split(';')[0].lower() == 'application/json':
            data = json.loads(response.read())
            choices = data.get('choices', []) if isinstance(data, dict) else []
            if not choices:
                raise SummaryOutputError('empty')
            choice = choices[0];message = choice.get('message', {})
            usage = data.get('usage')
            result = SimpleNamespace(choices=[SimpleNamespace(finish_reason=choice.get('finish_reason'),
                message=SimpleNamespace(content=message.get('content'), refusal=message.get('refusal')))],
                model=data.get('model'), usage=SimpleNamespace(**usage) if isinstance(usage, dict) else None,
                _stream_ignored=True, _stream_events=0)
        else:
            parts = [];refusals = [];finish = None;usage = None;model = None
            for chunk in stream:
                from processing_execution import CURRENT
                execution = CURRENT.get()
                if execution: execution.check()
                events += 1
                if getattr(chunk, 'usage', None) is not None: usage = chunk.usage
                if isinstance(getattr(chunk, 'model', None), str): model = chunk.model
                if not chunk.choices: continue
                choice = chunk.choices[0]
                text = getattr(choice.delta, 'content', None)
                refusal = getattr(choice.delta, 'refusal', None)
                if isinstance(text, str): parts.append(text)
                if isinstance(refusal, str): refusals.append(refusal)
                if choice.finish_reason: finish = choice.finish_reason
            result = SimpleNamespace(choices=[SimpleNamespace(finish_reason=finish,
                message=SimpleNamespace(content=''.join(parts), refusal=''.join(refusals)))],
                model=model, usage=usage, _stream_events=events)
        record = getattr(stream, 'record_completed_response', None)
        if callable(record): record(result)
        # Valid-looking JSON is not evidence that a truncated stream ended.
        if result.choices[0].finish_reason is None:
            raise SummaryOutputError('invalid', reason='stream_incomplete')
        return result
    finally:
        try: stream.close()
        except Exception: pass
