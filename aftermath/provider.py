"""Simulated provider contracts, intentionally not production adapters."""
import json
from pathlib import Path
from .store import connect, fingerprint


class Conflict(ValueError):
    pass


class Provider:
    def __init__(self, root, contract):
        if contract not in {'keyed', 'searchable', 'opaque', 'eventual'}:
            raise ValueError('unknown provider contract')
        self.path = Path(root) / 'provider.sqlite'
        self.contract = contract

    def perform(self, operation_id, payload, before_commit=None):
        fp = fingerprint(payload)
        with connect(self.path) as db:
            # BEGIN IMMEDIATE serializes key admission and its side effect.
            db.execute('BEGIN IMMEDIATE')
            if self.contract == 'keyed':
                prior = db.execute('SELECT * FROM keys WHERE operation_id=?', (operation_id,)).fetchone()
                if prior:
                    if prior['fingerprint'] != fp:
                        raise Conflict('idempotency key reused with different payload')
                    return prior['receipt']
            cursor = db.execute('INSERT INTO effects(operation_id,fingerprint,payload) VALUES(?,?,?)',
                                (operation_id, fp, json.dumps(payload, sort_keys=True)))
            receipt = cursor.lastrowid
            if self.contract == 'keyed':
                db.execute('INSERT INTO keys VALUES(?,?,?)', (operation_id, fp, receipt))
            if before_commit:
                before_commit()
            return receipt

    def lookup(self, operation_id, payload):
        if self.contract == 'opaque':
            raise NotImplementedError('provider has no outcome query')
        with connect(self.path) as db:
            rows = db.execute('SELECT * FROM effects WHERE operation_id=?' + (' AND receipt IN (SELECT receipt FROM visible_receipts)' if self.contract == 'eventual' else ''), (operation_id,)).fetchall()
        if len(rows) > 1:
            raise Conflict('multiple provider effects for one operation')
        if rows and rows[0]['fingerprint'] != fingerprint(payload):
            raise Conflict('provider payload does not match intent')
        return rows[0]['receipt'] if rows else None

    def reveal(self):
        """Explicit fixture replication barrier, not elapsed-time certainty.

        Only the experiment driver uses this; workers cannot invoke it.
        This simulated provider exposes committed rows to its lagged lookup.
        """
        if self.contract != 'eventual':
            raise ValueError('replication barrier only applies to eventual contract')
        with connect(self.path) as db:
            db.execute('INSERT OR IGNORE INTO visible_receipts SELECT receipt FROM effects')
