"""Serve build-time compressed public assets without per-request compression."""
import mimetypes
import anyio
from starlette.datastructures import Headers
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles, NotModifiedResponse


class VersionedStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code not in (200, 304):
            return response
        response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'
        if not path.endswith(('.js', '.css')):
            return response
        response.headers['Vary'] = 'Accept-Encoding'
        request = Headers(scope=scope)
        # A Range request is defined against the identity representation.
        if request.get('range'):
            return response
        qualities = {}
        for item in request.get('accept-encoding', '').lower().split(','):
            fields = item.strip().split(';')
            try:
                quality = next((float(field.strip()[2:]) for field in fields[1:] if field.strip().startswith('q=')), 1.0)
            except ValueError:
                quality = 0
            qualities[fields[0]] = max(0, min(quality, 1))
        for encoding, suffix in sorted([('br', '.br'), ('gzip', '.gz')], key=lambda item: qualities.get(item[0], qualities.get('*', 0)), reverse=True):
            if qualities.get(encoding, qualities.get('*', 0)) <= 0:
                continue
            filename, stat = await anyio.to_thread.run_sync(self.lookup_path, path + suffix)
            if stat is None:
                continue
            headers = {'Cache-Control': response.headers['cache-control'], 'Vary': 'Accept-Encoding', 'Content-Encoding': encoding}
            encoded = FileResponse(filename, stat_result=stat, media_type=mimetypes.guess_type(path)[0], headers=headers)
            if self.is_not_modified(encoded.headers, request):
                return NotModifiedResponse(encoded.headers)
            return encoded
        return response
