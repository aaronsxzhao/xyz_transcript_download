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
                 'supabase/migrations/20261102142210_consistent_summary_actions.sql',
                 'tests/sql/summary_actions.sql'):
        sql((root / path).read_text())
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
    print('PostgreSQL ordering, terminal-state, retry, lease and permission checks passed')


if __name__ == '__main__':
    main()
