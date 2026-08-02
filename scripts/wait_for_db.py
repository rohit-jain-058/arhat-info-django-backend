#!/usr/bin/env python
"""
Pure Python DB wait script — no netcat needed.
Tries to open a TCP connection to the DB every second until it succeeds.
"""
import os, sys, time, socket

host    = os.environ.get('DB_HOST', 'db')
port    = int(os.environ.get('DB_PORT', '5432'))
timeout = int(os.environ.get('DB_WAIT_TIMEOUT', '60'))

print(f'Waiting for database at {host}:{port}...', flush=True)
start = time.time()

while True:
    try:
        with socket.create_connection((host, port), timeout=2):
            print(f'Database ready ({int(time.time()-start)}s)', flush=True)
            sys.exit(0)
    except OSError:
        if time.time() - start >= timeout:
            print(f'Database not ready after {timeout}s — aborting', flush=True)
            sys.exit(1)
        time.sleep(1)