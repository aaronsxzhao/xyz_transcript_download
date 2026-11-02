"""Real PostgreSQL transaction checks, restricted to a disposable test database."""
import argparse
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
                 'tests/sql/video_write_order.sql'):
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
    print('PostgreSQL ordering, terminal-state, retry, lease and permission checks passed')


if __name__ == '__main__':
    main()
