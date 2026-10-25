"""Static assets build natively; production executables stay on target ARM."""
import re
from pathlib import Path

DOCKERFILE=Path(__file__).resolve().parents[1]/'Dockerfile'


def stages():
    result=[]
    for line in DOCKERFILE.read_text().splitlines():
        if line.startswith('FROM '):
            match=re.fullmatch(r'FROM (?:--platform=(\S+) )?(\S+)(?: AS (\S+))?',line)
            result.append({'platform':match[1] or '$TARGETPLATFORM','image':match[2],'name':match[3], 'lines':[]})
        elif result:result[-1]['lines'].append(line)
    return result


def test_frontend_bundler_runs_on_the_native_builder():
    frontend=next(stage for stage in stages() if 'RUN npm run build' in stage['lines'])
    assert frontend['platform']=='$BUILDPLATFORM'


def test_target_node_binary_never_comes_from_native_frontend_stage():
    parsed=stages();runtime=parsed[-1]
    copy=next(line for line in runtime['lines'] if line.endswith('/usr/local/bin/node /usr/local/bin/node'))
    source=re.search(r'--from=(\S+)',copy)[1]
    node=next(stage for stage in parsed if stage['name']==source)
    assert runtime['platform']==node['platform']=='$TARGETPLATFORM'
    assert node['image'].startswith('node:')
    assert 'RUN node --version' in runtime['lines']


def test_only_static_frontend_output_is_copied_into_runtime():
    parsed=stages();runtime=parsed[-1]
    frontend=next(stage for stage in parsed if 'RUN npm run build' in stage['lines'])
    copies=[line for line in runtime['lines'] if line.startswith('COPY --from='+frontend['name']+' ')]
    assert copies==['COPY --from='+frontend['name']+' /web/dist /app/web/dist']
