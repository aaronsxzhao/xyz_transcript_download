"""Bounded, reusable HTTP/1.1 connections for server-side Supabase requests."""
import logging

import httpx

logger = logging.getLogger(__name__)
READ_TIMEOUT = httpx.Timeout(connect=3, read=6, write=10, pool=3)


class SupabaseHTTPClient(httpx.Client):
    def __init__(self, **kwargs):
        # The shared HTTP/2 connection has produced ConnectionTerminated errors
        # under concurrent page reads. Independent HTTP/1.1 connections avoid
        # one terminated stream disrupting unrelated requests.
        super().__init__(http2=False, follow_redirects=True,
                         limits=httpx.Limits(max_connections=64, max_keepalive_connections=16,
                                             keepalive_expiry=4),
                         timeout=60, **kwargs)

    def send(self, request: httpx.Request, **kwargs) -> httpx.Response:
        rest = request.url.path.startswith('/rest/v1/')
        auth = request.url.path.startswith('/auth/v1/')
        if rest or auth:
            request.extensions['timeout'] = READ_TIMEOUT.as_dict()
        try:
            return super().send(request, **kwargs)
        except (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadError) as error:
            # Replay only idempotent database reads. Mutations, RPCs, sign-in,
            # refresh, and storage uploads must never be repeated implicitly.
            if not rest or request.method not in {'GET', 'HEAD'} or kwargs.get('stream'):
                raise
            logger.warning('[Supabase] Retrying interrupted read (%s)', type(error).__name__)
            return super().send(request, **kwargs)
