import pytest
from api.static_assets import VersionedStaticFiles


def scope(encoding='', **headers):
    return {'type':'http','method':'GET','path':'/file.js','headers':[(k.encode(), v.encode()) for k,v in {'accept-encoding':encoding, **headers}.items()]}


@pytest.mark.asyncio
async def test_precompressed_variants_and_conditional_requests(tmp_path):
    for suffix in ['', '.br', '.gz']:
        (tmp_path / ('file.js' + suffix)).write_bytes(b'const example = 1;' + suffix.encode())
    files = VersionedStaticFiles(directory=str(tmp_path))
    identity = await files.get_response('file.js', scope('identity'))
    brotli = await files.get_response('file.js', scope('gzip, br'))
    assert brotli.headers['content-encoding'] == 'br'
    assert 'javascript' in brotli.headers['content-type']
    assert brotli.headers['vary'] == 'Accept-Encoding'
    assert brotli.headers['etag'] != identity.headers['etag']
    gzip = await files.get_response('file.js', scope('br;q=0, gzip;q=1'))
    assert gzip.headers['content-encoding'] == 'gzip'
    cached = await files.get_response('file.js', scope('br', **{'if-none-match':brotli.headers['etag']}))
    assert cached.status_code == 304
    ranged = await files.get_response('file.js', scope('br', range='bytes=0-3'))
    assert 'content-encoding' not in ranged.headers


@pytest.mark.asyncio
async def test_missing_compressed_files_fall_back_and_paths_stay_scoped(tmp_path):
    (tmp_path / 'file.js').write_bytes(b'const example = 1;')
    files = VersionedStaticFiles(directory=str(tmp_path))
    response = await files.get_response('file.js', scope('br,gzip'))
    assert 'content-encoding' not in response.headers
    with pytest.raises(Exception) as error:
        await files.get_response('../secret.js', scope('br'))
    assert error.value.status_code == 404
