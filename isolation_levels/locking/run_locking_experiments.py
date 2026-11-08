"""Repeatable InnoDB locking experiments; all experimental writes roll back."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
import getpass
import hashlib
import json
import os
from pathlib import Path
import threading
import time

import mysql.connector

BASE = Path(__file__).resolve().parent
CASES = {
    'ru_dirty': ('READ UNCOMMITTED', 'Dirty read', 'FOR UPDATE'),
    'rc_repeatable': ('READ COMMITTED', 'Non-repeatable read', 'FOR SHARE'),
    'rr_phantom': ('REPEATABLE READ', 'Phantom read', 'Primary-key next-key locks'),
    'serial_table': ('SERIALIZABLE', 'Phantom read', 'LOCK TABLES READ'),
}


def load_script(path):
    statements = []
    pending = []
    for raw in path.read_text(encoding='utf-8-sig').splitlines():
        line = raw.strip()
        if line.startswith('-- @'):
            if pending:
                raise ValueError(f'Directive inside SQL in {path.name}')
            directive = line[4:]
            if directive not in {'ready', 'hold', 'released', 'wait', 'attempt'}:
                raise ValueError(f'Unknown directive: {directive}')
            statements.append(('sync', directive))
        elif line and not line.startswith('--'):
            pending.append(line)
            if line.endswith(';'):
                statements.append(('sql', ' '.join(pending).rstrip(';')))
                pending = []
    if pending:
        raise ValueError(f'Unterminated SQL in {path.name}')
    return statements


def connect(config, timeout):
    return mysql.connector.connect(**config, autocommit=True,
                                   connection_timeout=5,
                                   read_timeout=timeout + 5,
                                   write_timeout=timeout + 5)


def snapshot(conn):
    digest = hashlib.sha256()
    count = 0
    with conn.cursor() as cur:
        cur.execute('SELECT * FROM simplified_film ORDER BY film_id')
        for row in cur:
            digest.update(json.dumps(row, default=str, ensure_ascii=False).encode())
            digest.update(b'\n')
            count += 1
    return {'row_count': count, 'sha256': digest.hexdigest()}


def preflight(conn):
    with conn.cursor() as cur:
        cur.execute('SELECT VERSION(), DATABASE()')
        version, database = cur.fetchone()
        cur.execute("SELECT ENGINE FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='simplified_film'")
        if cur.fetchone() != ('InnoDB',):
            raise ValueError('Existing simplified_film must use InnoDB; no schema will be created.')
        cur.execute('SHOW COLUMNS FROM simplified_film')
        columns = cur.fetchall()
        if not {'film_id', 'title', 'release_year', 'length'} <= {row[0] for row in columns}:
            raise ValueError('Table columns do not match the existing baseline SQL.')
        cur.execute('SHOW INDEX FROM simplified_film WHERE Key_name = \'PRIMARY\'')
        indexes = cur.fetchall()
        if len(indexes) != 1 or indexes[0][4] != 'film_id':
            raise ValueError('A single-column primary key on film_id is required.')
        cur.execute('SELECT length FROM simplified_film WHERE film_id=1')
        if cur.fetchone() != (86,):
            raise ValueError('Expected film_id=1 with length=86. No data was reset or changed.')
        cur.execute('SELECT MIN(film_id), MAX(film_id) FROM simplified_film')
        minimum, maximum = cur.fetchone()
        if minimum < 1 or maximum >= 2147483647:
            raise ValueError('Positive film IDs and an available signed INT ID are required.')
        insert_id = max(1001, maximum + 1)
        cur.execute('SELECT COUNT(*) FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=DATABASE() AND EVENT_OBJECT_TABLE=\'simplified_film\'')
        if cur.fetchone()[0]:
            raise ValueError('Table has triggers; review their effects before running these experiments.')
    return {'version': version, 'database': database, 'columns': columns, 'insert_id': insert_id}


def run_case(config, key, hold, timeout, insert_id=1001):
    start = time.perf_counter()
    events = []
    guard = threading.Lock()
    signals = {name: threading.Event() for name in ('ready', 'attempt', 'abort')}
    state = {}

    def record(event):
        with guard:
            events.append(event)

    def wait(name):
        deadline = time.perf_counter() + timeout
        while not signals[name].wait(0.05):
            if signals['abort'].is_set():
                raise RuntimeError('Other worker failed')
            if time.perf_counter() >= deadline:
                raise TimeoutError(f'Timed out waiting for {name}')
        if signals['abort'].is_set():
            raise RuntimeError('Other worker failed')

    def worker(label):
        conn = None
        target = False
        try:
            conn = connect(config, timeout)
            with conn.cursor() as cur:
                cur.execute(f'SET SESSION innodb_lock_wait_timeout={timeout}')
                cur.execute(f'SET SESSION lock_wait_timeout={timeout}')
                cur.execute('SET @locking_film_id = %s', (insert_id,))
                for kind, value in load_script(BASE / f'{key}_{label}.sql'):
                    if signals['abort'].is_set():
                        raise RuntimeError('Other worker failed')
                    if kind == 'sync':
                        if value == 'wait':
                            wait('ready')
                        elif value == 'ready':
                            signals['ready'].set()
                        elif value == 'attempt':
                            target = True
                        elif value == 'hold':
                            wait('attempt')
                            if signals['abort'].wait(hold):
                                raise RuntimeError('Other worker failed during hold')
                            state['release_started_s'] = time.perf_counter() - start
                        elif value == 'released':
                            state['release_finished_s'] = time.perf_counter() - start
                        continue
                    event = {'transaction': label, 'sql': value,
                             'start_s': time.perf_counter() - start, 'target': target}
                    if target:
                        signals['attempt'].set()
                    try:
                        cur.execute(value)
                        event['rows'] = cur.fetchall() if cur.with_rows else None
                        event['affected_rows'] = cur.rowcount
                    except Exception as exc:
                        event['error'] = str(exc)
                        raise
                    finally:
                        event['end_s'] = time.perf_counter() - start
                        event['elapsed_s'] = event['end_s'] - event['start_s']
                        record(event)
                    target = False
        except Exception as exc:
            signals['abort'].set()
            record({'transaction': label, 'error': str(exc), 'start_s': time.perf_counter() - start})
        finally:
            if conn is not None:
                # Roll back before UNLOCK TABLES, which can implicitly commit.
                for sql in ('ROLLBACK', 'UNLOCK TABLES'):
                    try:
                        with conn.cursor() as cur:
                            cur.execute(sql)
                    except Exception as exc:
                        signals['abort'].set()
                        record({'transaction': label, 'sql': sql, 'cleanup_error': str(exc),
                                'start_s': time.perf_counter() - start})
                conn.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker, label) for label in ('A', 'B')]
        for future in futures:
            future.result()
    events.sort(key=lambda event: event['start_s'])
    errors = [e for e in events if 'error' in e or 'cleanup_error' in e]
    targets = [e for e in events if e.get('target')]
    target = targets[0] if len(targets) == 1 else {}
    blocking = (not errors and target.get('elapsed_s', 0) >= hold * 0.8
                and target.get('end_s', 0) >= state.get('release_started_s', float('inf')))
    reader = 'B' if key == 'ru_dirty' else 'A'
    reads = [e['rows'] for e in events if e.get('transaction') == reader
             and e.get('sql', '').startswith('SELECT') and e.get('rows') is not None]
    stable = len(reads) == 2 and reads[0] == reads[1]
    if key in {'ru_dirty', 'rc_repeatable'}:
        stable = stable and reads[0] == [(86,)]
    writer_checks = [e['rows'] for e in events if e.get('transaction') == 'B'
                     and e.get('sql', '').startswith('SELECT') and e.get('rows') is not None]
    if key == 'rc_repeatable':
        mutation_observed = writer_checks == [[(5,)]]
    elif key in {'rr_phantom', 'serial_table'}:
        original_count = len(reads[0]) if key == 'rr_phantom' and reads else (reads[0][0][0] if reads else -1)
        mutation_observed = writer_checks == [[(original_count + 1,)]]
    else:
        mutation_observed = any(e.get('affected_rows') == 1 and e.get('sql', '').startswith('UPDATE') for e in events)
    return {'case': key, 'isolation': CASES[key][0], 'anomaly': CASES[key][1],
            'mechanism': CASES[key][2], 'insert_id': insert_id, 'passed': bool(stable and blocking and mutation_observed and not errors),
            'stable_reads': stable, 'write_observed': mutation_observed,
            'blocking_inferred': bool(blocking), 'blocked_statement_elapsed_s': target.get('elapsed_s'),
            'exact_server_lock_wait_s': None, 'total_s': time.perf_counter() - start,
            **state, 'events': events}


def write_outputs(path, payload):
    path.mkdir(parents=True, exist_ok=True)
    json_path = path / 'locking.json'
    md_path = path / 'locking_results.md'
    started = datetime.fromisoformat(payload['started_utc']).astimezone(timezone(timedelta(hours=8)))
    timestamp = started.strftime('%Y-%m-%d %H:%M:%S') + ' UTC+08:00 (Asia/Manila)'
    json_path.write_text(json.dumps(payload, indent=2, default=str), encoding='utf-8')
    lines = ['# Measured locking results', '', f'Run started: {timestamp}', '',
             'Elapsed statement times include server execution, lock waiting, and client overhead.',
             'Blocking is inferred from controlled overlap and completion after lock release.',
             'Exact server lock-wait duration and throughput were not measured.', '',
             '| Case | Pass | Blocked statement (s) | Total (s) | Table unchanged |',
             '|---|---|---|---|---|']
    for result in payload['results']:
        duration = result['blocked_statement_elapsed_s']
        elapsed = f'{duration:.6f}' if duration is not None else 'Unavailable'
        lines.append(f"| {result['case']} | {result['passed']} | {elapsed} | {result['total_s']:.6f} | {result['table_unchanged']} |")
    for result in payload['results']:
        lines += ['', f"## {result['case']} (run {result['repetition']})", '',
                  '| Time | Transaction A | Transaction B |', '|---|---|---|']
        for i, event in enumerate(result['events'], 1):
            detail = event.get('sql', 'Worker')
            if event.get('rows') is not None:
                rows = event['rows']
                detail += f' -> {rows[:5]}' + (f' ({len(rows)} rows total)' if len(rows) > 5 else '')
            if 'elapsed_s' in event:
                detail += f" [{event['elapsed_s']:.6f}s]"
            detail += ' ' + event.get('error', event.get('cleanup_error', ''))
            detail = detail.replace('|', '\\|')
            cells = [detail, ''] if event['transaction'] == 'A' else ['', detail]
            lines.append(f"| t{i}, {event['start_s']:.6f}s | {cells[0]} | {cells[1]} |")
    if payload.get('error'):
        lines += ['', 'Run error: ' + payload['error']]
    md_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'Results: {json_path.name} and {md_path.name} in {path.name}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=['all', *CASES], default='all')
    parser.add_argument('--repeat', type=int, default=1)
    parser.add_argument('--hold-seconds', type=float, default=3)
    parser.add_argument('--timeout', type=int, default=15)
    parser.add_argument('--validate-only', action='store_true')
    parser.add_argument('--output-dir', type=Path, default=BASE)
    args = parser.parse_args()
    if args.repeat < 1 or not 0.25 <= args.hold_seconds < args.timeout / 2:
        parser.error('repeat must be positive; hold must be >=0.25 and less than half the timeout')
    for key in CASES:
        for label in ('A', 'B'):
            load_script(BASE / f'{key}_{label}.sql')
    if args.validate_only:
        print('All eight SQL scripts parsed. No database connection made.')
        return 0
    config = {'host': os.environ.get('MYSQL_HOST', '127.0.0.1'),
              'port': int(os.environ.get('MYSQL_PORT', '3306')),
              'user': os.environ.get('MYSQL_USER', 'root'),
              'database': os.environ.get('MYSQL_DATABASE', 'sakila'),
              'password': os.environ.get('MYSQL_PASSWORD')}
    if config['password'] is None:
        config['password'] = getpass.getpass('MySQL password: ')
    payload = {'started_utc': datetime.now(timezone.utc).isoformat(),
               'hold_seconds': args.hold_seconds, 'results': []}
    observer = None
    try:
        observer = connect(config, args.timeout)
        payload['server'] = preflight(observer)
        initial = snapshot(observer)
        payload['initial_table'] = initial
        for repetition in range(1, args.repeat + 1):
            for key in (CASES if args.case == 'all' else [args.case]):
                if snapshot(observer) != initial:
                    raise RuntimeError('Table changed before experiment; refusing to continue.')
                result = run_case(config, key, args.hold_seconds, args.timeout, payload['server']['insert_id'])
                result['repetition'] = repetition
                result['table_unchanged'] = snapshot(observer) == initial
                result['passed'] = result['passed'] and result['table_unchanged']
                payload['results'].append(result)
                print(f"{key}, run {repetition}: {'PASS' if result['passed'] else 'FAIL'}")
                if not result['passed']:
                    raise RuntimeError('Experiment failed; inspect the recorded trace before retrying.')
        payload['final_table'] = snapshot(observer)
    except (Exception, KeyboardInterrupt) as exc:
        payload['error'] = str(exc) or 'Interrupted'
        print(f"Stopped: {payload['error']}")
    finally:
        if observer is not None:
            observer.close()
        write_outputs(args.output_dir, payload)
    return int('error' in payload)


if __name__ == '__main__':
    raise SystemExit(main())
