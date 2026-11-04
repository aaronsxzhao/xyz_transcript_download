"""Two-connection cancellation races in a disposable PostgreSQL database only."""
import argparse
from pathlib import Path
import subprocess


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--docker-container');args=parser.parse_args()
    prefix=['docker','--host=unix:///var/run/docker.sock','exec','-i',args.docker_container] if args.docker_container else []
    command=prefix+['psql','-U','postgres','-d','queue_cancel_test','-At','-v','ON_ERROR_STOP=1']
    def sql(value):return subprocess.check_output(command,input=value,text=True,timeout=15).strip()
    assert sql('select current_database();')=='queue_cancel_test'
    root=Path(__file__).resolve().parents[1]
    sql("create schema auth;create table auth.users(id uuid primary key);"
        "do $$ begin if not exists(select from pg_roles where rolname='anon') then create role anon;end if;"
        "if not exists(select from pg_roles where rolname='authenticated') then create role authenticated;end if;"
        "if not exists(select from pg_roles where rolname='service_role') then create role service_role bypassrls;end if;end $$;")
    sql((root/'supabase/migrations/20261026064154_durable_processing.sql').read_text())
    sql((root/'supabase/migrations/20261104134945_atomic_processing_cancel.sql').read_text())
    owner='10000000-0000-0000-0000-000000000001';other='10000000-0000-0000-0000-000000000002'
    sql(f"insert into auth.users values ('{owner}'),('{other}');")
    for kind in ['video','podcast']:
        def cancel(deleted='false',user=owner):return f"select cancel_processing_work('{user}','{kind}','task',{deleted});"
        def row():return sql("select state||':'||cancel_requested||':'||coalesce(payload->>'deleted','false')||':'||coalesce(payload->>'keep','') from processing_work;")
        for terminal in ['completed','failed','cancelled']:
            sql(f"delete from processing_work;insert into processing_work(user_id,kind,task_id,source_id,state) values('{owner}','{kind}','task','source','{terminal}');")
            sql(cancel('true'));assert row()==terminal+':false:false:'
        # Hold the row in connection A; connection B cancellation must recheck
        # both WHERE and SET expressions after A commits a newer state/payload.
        for newer_state,expected in [('completed','completed:false:false:latest'),('running','running:true:true:latest'),('queued','cancelled:true:true:latest')]:
            sql(f"delete from processing_work;insert into processing_work(user_id,kind,task_id,source_id,state) values('{owner}','{kind}','task','source','queued');")
            p=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
            try:
                p.stdin.write("begin;update processing_work set state='"+newer_state+"',payload='{\"keep\":\"latest\"}' returning state;select pg_sleep(1);commit;\n");p.stdin.close()
                assert p.stdout.readline().strip()=='BEGIN';assert p.stdout.readline().strip()==newer_state
                sql(cancel('true'));assert p.wait(timeout=5)==0;assert row()==expected,(kind,newer_state,row())
            finally:
                if p.poll() is None:p.terminate();p.wait(timeout=5)
        sql("update processing_work set state='running',cancel_requested=false,payload='{}',worker_id='worker',lease_until=now()+interval '60 seconds';")
        sql(cancel(user=other));assert row()=='running:false:false:'
        sql(cancel());assert row()=='running:true:false:'
        assert sql("select finish_processing_work(id,'worker','completed','{}') from processing_work;")=='t'
        assert row()=='cancelled:true:false:'
        # A fresh queued retry remains cancellable; old completed attempts stay unchanged.
        sql("update processing_work set state='completed',cancel_requested=false;")
        sql(f"select enqueue_processing_work('{owner}','{kind}','task','source','{{}}');")
        sql(cancel());assert sql("select string_agg(state,',' order by state) from processing_work;")=='cancelled,completed'
        sql('delete from processing_work;')
    for role in ['anon','authenticated']:
        assert sql(f"select has_function_privilege('{role}','public.cancel_processing_work(uuid,text,text,boolean)','execute');")=='f'
    assert sql("select has_function_privilege('service_role','public.cancel_processing_work(uuid,text,text,boolean)','execute');")=='t'
    print('PostgreSQL video/podcast cancellation races, terminal states, retry, deletion payload and permissions passed')

if __name__=='__main__':main()
