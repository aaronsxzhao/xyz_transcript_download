"""Atomic quotas and service-role-only grants in an isolated PostgreSQL database."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--docker-container')
    args=parser.parse_args()
    prefix=(['docker','--host=unix:///var/run/docker.sock','exec','-i',args.docker_container] if args.docker_container else [])
    # Dedicated database; never accept a caller-supplied production DSN.
    base=prefix+['psql','-U','postgres','-At','-v','ON_ERROR_STOP=1']
    subprocess.run(base+['-d','postgres'],input='CREATE DATABASE platform_token_test;',text=True,check=True,capture_output=True)
    def sql(value):
        return subprocess.check_output(base+['-d','platform_token_test'],input=value,text=True,timeout=30).strip()
    try:
        sql("CREATE SCHEMA auth; CREATE TABLE auth.users(id uuid primary key); DO $$ BEGIN "
            "IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='anon') THEN CREATE ROLE anon; END IF; "
            "IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='authenticated') THEN CREATE ROLE authenticated; END IF; "
            "IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='service_role') THEN CREATE ROLE service_role BYPASSRLS; END IF; END $$;")
        sql((Path(__file__).resolve().parents[1]/'supabase/migrations/20261103164329_scoped_platform_test_tokens.sql').read_text())
        sql("insert into auth.users values ('10000000-0000-0000-0000-000000000001'); "
            "insert into platform_test_tokens(token_digest,owner_id,scopes,expires_at) values "
            "(repeat('a',64),'10000000-0000-0000-0000-000000000001',array['content:read','models:probe'],now()+interval '1 day');")
        for role in ('anon','authenticated'):
            assert sql(f"select has_table_privilege('{role}','platform_test_tokens','select');")=='f'
            assert sql(f"select has_function_privilege('{role}','consume_platform_test_token(text,text,text)','execute');")=='f'
        def consume(scope='models:probe'):
            return sql("set role service_role; select consume_platform_test_token(repeat('a',64),'"+scope+"','/api/settings/models')->>'status';").splitlines()[-1]
        with ThreadPoolExecutor(max_workers=12) as pool:
            results=list(pool.map(lambda _:consume(),range(12)))
        assert results.count('ok')==6 and results.count('limited')==6, results
        assert consume('diagnostics:run')=='denied'
        assert consume('content:read')=='ok'
        sql("update platform_test_tokens set read_count=120, read_window=now();")
        assert consume('content:read')=='limited'
        sql("update platform_test_tokens set read_window=now()-interval '2 minutes';")
        assert consume('content:read')=='ok'
        sql("update platform_test_tokens set revoked_at=now();")
        assert consume('content:read')=='invalid'
        sql("update platform_test_tokens set revoked_at=null,created_at=now()-interval '2 days',expires_at=now()-interval '1 day';")
        assert consume('content:read')=='invalid'
        print('PASS: token grants, owner binding, atomic probe budget, read budget/reset, scopes, revocation and expiry')
    finally:
        subprocess.run(base+['-d','postgres'],input='DROP DATABASE platform_token_test;',text=True,check=True,capture_output=True)


if __name__=='__main__': main()
