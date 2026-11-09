"""Real local HTTP gateway failures through the SDK; no external model calls."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
from openai import APIStatusError, OpenAI
from execution_store import Store
from processing_execution import Execution, bind
from reading_editor import call_editor
from summarizer import Summarizer

@pytest.fixture
def gateway():
    state = {'statuses': [], 'calls': 0}
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']))
            state['calls'] += 1
            status = state['statuses'].pop(0) if state['statuses'] else 200
            body = b'<html>Gateway timeout</html>' if status == 524 else json.dumps({
                'id': 'synthetic', 'object': 'chat.completion', 'created': 1, 'model': 'synthetic',
                'choices': [{'index': 0, 'finish_reason': 'stop', 'message': {'role': 'assistant', 'content': '{"text":"saved result"}'}}],
            }).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'text/html' if status == 524 else 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers(); self.wfile.write(body)
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
    state['url'] = f'http://127.0.0.1:{server.server_port}/v1'
    try: yield state
    finally: server.shutdown(); server.server_close(); worker.join(timeout=2)


def test_real_http_524_is_retried_by_podcast_model_and_stops_after_limit(gateway):
    engine = Summarizer(api_key='synthetic', base_url=gateway['url'], model='synthetic')
    engine.client.close()
    engine.client = OpenAI(api_key='synthetic', base_url=gateway['url'], max_retries=0, http_client=httpx.Client(trust_env=False))
    try:
        gateway['statuses'] = [524, 200]
        assert engine._call_llm_with_retry('synthetic source').choices[0].message.content == '{"text":"saved result"}'
        assert gateway['calls'] == 2
        from summarizer import MAX_RETRIES
        gateway['statuses'] = [524] * (MAX_RETRIES + 1)
        before = gateway['calls']
        with pytest.raises(APIStatusError) as error:
            engine._call_llm_with_retry('another synthetic source')
        assert error.value.status_code == 524
        assert gateway['calls'] - before == MAX_RETRIES
    finally: engine.client.close()


def test_real_http_524_does_not_poison_saved_editor_checkpoints(gateway, tmp_path):
    path = tmp_path / 'queue.sqlite'
    store = Store(path)
    with OpenAI(api_key='synthetic', base_url=gateway['url'], max_retries=0, http_client=httpx.Client(trust_env=False)) as client:
        def call(payload): return call_editor(client, 'synthetic', 'synthetic', payload, 5)
        with bind(Execution('test-owner', 'source', store)):
            assert call('{"phase":"draft"}') == {'text': 'saved result'}
            gateway['statuses'] = [524]
            with pytest.raises(APIStatusError): call('{"phase":"repair"}')
        # Reopen the real SQLite store and bind a fresh execution, as on recovery.
        with bind(Execution('test-owner', 'source', Store(path))):
            before = gateway['calls']
            assert call('{"phase":"draft"}') == {'text': 'saved result'}
            assert gateway['calls'] == before
            assert call('{"phase":"repair"}') == {'text': 'saved result'}
            assert gateway['calls'] == before + 1
