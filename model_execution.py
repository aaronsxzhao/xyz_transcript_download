"""Explicit compatible-model controls; provider defaults are not invented modes."""
from types import SimpleNamespace
from urllib.parse import urlsplit

EFFORTS=('none','minimal','low','medium','high','xhigh','max','default')
TIERS=('auto','default','priority','fast','flex','on_demand','performance')


def capabilities(base_url,model):
    host=(urlsplit(base_url).hostname or '').lower()
    if host=='api.groq.com' and model in ('openai/gpt-oss-120b','openai/gpt-oss-20b'):
        return {'reasoning':['low','medium','high'],'tiers':['auto','on_demand','flex','performance'],'known':True}
    if host=='api.openai.com' and model in ('gpt-5','gpt-5-mini','gpt-5-nano','o3','o3-mini','o4-mini'):
        return {'reasoning':(['minimal'] if model.startswith('gpt-5') else [])+['low','medium','high'],'tiers':['auto','default','priority','fast','flex'],'known':True}
    # A custom gateway's /models list often exposes only IDs. Acceptance must
    # be tested against that endpoint, rather than inferred from the name.
    return {'reasoning':list(EFFORTS),'tiers':list(TIERS),'known':False}


def request_options(preferences,base_url,model):
    from api.custom_models import ModelConfigurationError
    values={key:preferences.get(key,'') for key in ('llm_reasoning_effort','llm_service_tier')}
    caps=capabilities(base_url,model)
    if values['llm_reasoning_effort'] and values['llm_reasoning_effort'] not in caps['reasoning']:
        raise ModelConfigurationError('The selected reasoning effort is not supported by this model configuration.')
    if values['llm_service_tier'] and values['llm_service_tier'] not in caps['tiers']:
        raise ModelConfigurationError('The selected service tier is not supported by this model configuration.')
    return {target:values[source] for source,target in (('llm_reasoning_effort','reasoning_effort'),('llm_service_tier','service_tier')) if values[source]}


class ConfiguredClient:
    """Inject the same selected options into generation, audit and editing."""
    def __init__(self,client,options):
        self.raw=client;self.options=dict(options)
        self.chat=SimpleNamespace(completions=SimpleNamespace(create=self.create))

    @property
    def base_url(self): return self.raw.base_url

    def create(self,**kwargs):
        from processing_execution import CURRENT
        execution=CURRENT.get()
        if execution: execution.check()
        # Explicit user values take priority over legacy per-pass defaults.
        return self.raw.chat.completions.create(**{**kwargs,**self.options})

    def with_options(self,**kwargs): return ConfiguredClient(self.raw.with_options(**kwargs),self.options)
    def close(self): return self.raw.close()


def configure(client,options): return ConfiguredClient(client,options) if options else client


def request_timeout():
    from config import _get_env_int
    return _get_env_int('LLM_REQUEST_TIMEOUT_SECONDS',120,min_val=30)
