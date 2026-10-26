"""Expose application duration separately from the user's network wait."""
import time


class RequestTimingMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not scope.get('path', '').startswith('/api/'):
            return await self.app(scope, receive, send)
        started = time.perf_counter()

        async def timed_send(message):
            if message['type'] == 'http.response.start':
                duration = (time.perf_counter() - started) * 1000
                headers = list(message.get('headers', []))
                if scope.get('path') in ('/api/jobs', '/api/video-notes/progress'):
                    headers = [(key, value) for key, value in headers if key.lower() != b'cache-control']
                    headers.append((b'cache-control', b'private, no-store'))
                message = {**message, 'headers': [*headers,
                           (b'server-timing', f'app;dur={duration:.1f}'.encode())]}
            await send(message)

        await self.app(scope, receive, timed_send)
