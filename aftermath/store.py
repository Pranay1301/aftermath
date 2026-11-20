"""Two independent SQLite databases: the worker cannot atomically commit both.

This models a local tool ledger versus an external provider's durable state.
No network, accounts, payments or real messages are involved.
"""
import hashlib
import json
import sqlite3
from pathlib import Path


def fingerprint(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def connect(path):
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('PRAGMA synchronous=FULL')
    return db


def initialize(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with connect(root / 'ledger.sqlite') as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS operations (
            id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
            state TEXT NOT NULL CHECK(state IN ('prepared','dispatching','done','held')),
            receipt INTEGER, reason TEXT);
        CREATE TABLE IF NOT EXISTS events (
            seq INTEGER PRIMARY KEY AUTOINCREMENT, phase TEXT NOT NULL,
            detail TEXT NOT NULL);
        ''')
    with connect(root / 'provider.sqlite') as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS effects (
            receipt INTEGER PRIMARY KEY AUTOINCREMENT, operation_id TEXT NOT NULL,
            fingerprint TEXT NOT NULL, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS visible_receipts (receipt INTEGER PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS keys (
            operation_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
            receipt INTEGER NOT NULL REFERENCES effects(receipt));
        ''')


def event(root, phase, detail):
    with connect(Path(root) / 'ledger.sqlite') as db:
        db.execute('INSERT INTO events(phase,detail) VALUES(?,?)', (phase, detail))


def snapshot(root):
    with connect(Path(root) / 'ledger.sqlite') as db:
        operations = [dict(r) for r in db.execute('SELECT * FROM operations')]
        events = [dict(r) for r in db.execute('SELECT * FROM events ORDER BY seq')]
    with connect(Path(root) / 'provider.sqlite') as db:
        effects = [dict(r) for r in db.execute('SELECT * FROM effects ORDER BY receipt')]
    return {'operations': operations, 'events': events, 'effects': effects}
