"""Real PostgreSQL transaction checks, restricted to a disposable test database."""
import argparse
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--docker-container')
    args = parser.parse_args()
    command = (['docker', '--host=unix:///var/run/docker.sock', 'exec', '-i', args.docker_container]
               if args.docker_container else []) + ['psql', '-U', 'postgres', '-d', 'video_order_test',
                                                   '-At', '-v', 'ON_ERROR_STOP=1']
    def sql(value):
        return subprocess.check_output(command, input=value, text=True, timeout=30).strip()
    if sql('select current_database();') != 'video_order_test':
        raise RuntimeError('Refusing a non-test database')
    root = Path(__file__).resolve().parents[1]
    for path in ('tests/sql/video_write_order_schema.sql',
                 'supabase/migrations/20261102133402_ordered_video_task_writes.sql',
                 'tests/sql/video_write_order.sql',
                 'supabase/migrations/20261103041517_consistent_summary_actions.sql',
                 'tests/sql/summary_actions.sql'):
        sql((root / path).read_text())
    original = (root / 'supabase/migrations/20261019163814_durable_processing_and_indexes.sql').read_text()
    sql(original[original.index('CREATE OR REPLACE FUNCTION'):])
    sql((root / 'supabase/migrations/20261103041536_ordered_note_recovery.sql').read_text())
    sql((root / 'tests/sql/ordered_note_recovery.sql').read_text())
    sql("insert into video_tasks(id,status,updated_at) values ('race','pending','2026-01-01');")
    newer = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        newer.stdin.write("begin; select update_video_task_ordered('race',"
                          "'{\"status\":\"cancelled\",\"updated_at\":\"2026-01-03Z\"}'); "
                          "select pg_sleep(1); commit;\n")
        newer.stdin.close()
        assert newer.stdout.readline().strip() == 'BEGIN'
        assert newer.stdout.readline().strip() == 'applied'
        # The old request begins while the newer transaction holds the row lock.
        assert sql("select update_video_task_ordered('race',"
                   "'{\"status\":\"summarizing\",\"updated_at\":\"2026-01-02Z\"}');") == 'stale'
        assert newer.wait(timeout=5) == 0
        assert sql("select status from video_tasks where id='race';") == 'cancelled'
    finally:
        if newer.poll() is None:
            newer.terminate()
            newer.wait(timeout=5)
    owner = '10000000-0000-0000-0000-000000000001'
    def checkpoint(status, revision):
        rows = [{'id':'podcast-race','user_id':owner,'payload':{'job_id':'podcast-race',
                 'user_id':owner,'status':status,'revision':revision}}]
        return "select save_processing_jobs_ordered('" + json.dumps(rows) + "',null,null,true)->0->>'outcome';"
    assert sql(checkpoint('pending',1)) == 'applied'
    newer = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    try:
        newer.stdin.write('begin;' + checkpoint('completed',3) + 'select pg_sleep(1); commit;\n')
        newer.stdin.close()
        assert newer.stdout.readline().strip() == 'BEGIN'
        assert newer.stdout.readline().strip() == 'applied'
        assert sql(checkpoint('transcribing',2)) == 'stale'
        assert newer.wait(timeout=5) == 0
        assert sql("select payload->>'status' from processing_jobs where id='podcast-race';") == 'completed'
    finally:
        if newer.poll() is None:
            newer.terminate()
            newer.wait(timeout=5)
    payload = json.dumps({'task_id':'recovery-race','user_id':owner,'version_id':'old-backup',
                          'content':'old synthetic backup','style':'detailed','model':'test',
                          'recovery_order':{'base_versions':[],'work_id':None}})
    sql("insert into video_tasks(id,user_id,status,updated_at) values ('recovery-race','"+owner+"','failed','2026-01-01');")
    for action, expected in [(
        "select complete_user_video_note('"+owner+"','recovery-race','new-output','new synthetic output','detailed','test','');", 'changed'), (
        "insert into processing_work(id,user_id,kind,task_id,state,created_at) values ('40000000-0000-0000-0000-000000000001','"+owner+"','video','recovery-race','queued',now());", 'busy')]:
        newer = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        try:
            # Queue admission and recovery share this admission lock. A normal
            # final commit holds the task row; recovery must compare after it.
            lock = "select pg_advisory_xact_lock(hashtextextended('"+owner+":video:recovery-race',0));" if expected=='busy' else ''
            newer.stdin.write('begin;' + lock + action + 'select pg_sleep(1); commit;\n')
            newer.stdin.close()
            assert newer.stdout.readline().strip() == 'BEGIN'
            if lock: newer.stdout.readline()
            newer.stdout.readline()  # The conflicting mutation holds its lock.
            assert sql("select recover_video_note_ordered('"+owner+"','recovery-race','2026-01-01','"+payload+"');") == expected
            assert newer.wait(timeout=5) == 0
            assert sql("select markdown from video_tasks where id='recovery-race';") == 'new synthetic output'
            assert sql("select count(*) from video_task_versions where id='old-backup';") == '0'
        finally:
            if newer.poll() is None:
                newer.terminate()
                newer.wait(timeout=5)
    print('PostgreSQL ordering, terminal-state, retry, lease and permission checks passed')


if __name__ == '__main__':
    main()
