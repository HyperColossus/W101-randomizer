"""Transactional SQLite character/run state with a durable game-adapter outbox.

This is a bridge backend, NOT an authoritative Wizard101 server. An Imlight adapter
must apply all events idempotently to its own character saves and acknowledge each.
"""
from __future__ import annotations

import copy
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .core import RandomizerError, canonical, fingerprint, validate_catalog
from .progression import SpellProgression


def _json(data: Any) -> str:
    return canonical(data).decode('utf-8')


class RunStore:
    def __init__(self, db_path: str | Path, catalog: dict, manifest: dict):
        validate_catalog(catalog)
        if manifest.get('catalog_sha256') != fingerprint(catalog):
            raise RandomizerError('catalog SHA-256 does not match manifest')
        expected = fingerprint({k: v for k, v in manifest.items() if k != 'manifest_sha256'})
        if manifest.get('manifest_sha256') != expected:
            raise RandomizerError('manifest SHA-256 is incorrect or manifest was modified')
        self.catalog, self.manifest = copy.deepcopy(catalog), copy.deepcopy(manifest)
        self.db_path = str(db_path)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with self._transaction() as conn:
            schema = '''
                CREATE TABLE IF NOT EXISTS run (
                    id INTEGER PRIMARY KEY CHECK(id=1), manifest_sha TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS characters (
                    id TEXT PRIMARY KEY, data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS commands (
                    request_id TEXT PRIMARY KEY, actor TEXT NOT NULL,
                    action TEXT NOT NULL, payload_sha TEXT NOT NULL,
                    response_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor TEXT NOT NULL, request_id TEXT NOT NULL,
                    kind TEXT NOT NULL, payload_json TEXT NOT NULL,
                    acknowledged INTEGER NOT NULL DEFAULT 0 CHECK(acknowledged IN (0,1))
                );
                CREATE TABLE IF NOT EXISTS claims (
                    actor TEXT NOT NULL, claim_key TEXT NOT NULL,
                    reward_id TEXT NOT NULL,
                    PRIMARY KEY(actor, claim_key)
                );
                CREATE INDEX IF NOT EXISTS pending_events ON outbox(actor, acknowledged, id);
            '''
            for statement in schema.split(';'):
                if statement.strip():
                    conn.execute(statement)
            row = conn.execute('SELECT manifest_sha FROM run WHERE id=1').fetchone()
            if row and row['manifest_sha'] != manifest['manifest_sha256']:
                raise RandomizerError('database belongs to a different run; use a new database')
            if row is None:
                conn.execute('INSERT INTO run(id, manifest_sha) VALUES (1, ?)',
                             (manifest['manifest_sha256'],))

    @contextmanager
    def _transaction(self):
        conn = sqlite3.connect(self.db_path, timeout=20, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute('PRAGMA busy_timeout=20000')
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('PRAGMA synchronous=FULL')
            conn.execute('BEGIN IMMEDIATE')
            yield conn
            conn.execute('COMMIT')
        except Exception:
            if conn.in_transaction:
                conn.execute('ROLLBACK')
            raise
        finally:
            conn.close()

    def _progression(self, actor: str, old: dict | None) -> SpellProgression:
        state = {'manifest_sha256': self.manifest['manifest_sha256'],
                 'characters': {} if old is None else {actor: copy.deepcopy(old)}}
        return SpellProgression(self.catalog, self.manifest, state)

    def get_character(self, actor: str) -> dict | None:
        with self._transaction() as conn:
            row = conn.execute('SELECT data FROM characters WHERE id=?', (actor,)).fetchone()
            return json.loads(row['data']) if row else None

    def _add_event(self, conn, actor: str, request_id: str, kind: str, payload: dict):
        conn.execute('INSERT INTO outbox(actor,request_id,kind,payload_json) VALUES(?,?,?,?)',
                     (actor, request_id, kind, _json(payload)))

    def _emit_spell_differences(self, conn, actor: str, request_id: str, before: list, after: list):
        # Grant first, revoke second, to avoid leaving a wizard with no damage spell
        # if a bridge is interrupted during a reroll. The bridge must be idempotent.
        for spell in after:
            if spell not in before:
                self._add_event(conn, actor, request_id, 'spell.grant', {'spell_id': spell})
        for spell in before:
            if spell not in after:
                self._add_event(conn, actor, request_id, 'spell.revoke', {'spell_id': spell})

    def perform(self, actor: str, action: str, request_id: str, payload: dict | None = None) -> dict:
        """One idempotent command/transaction. A request_id must not be reused with new input."""
        if not isinstance(actor, str) or not actor or len(actor) > 128 or '/' in actor:
            raise RandomizerError('invalid actor')
        if not isinstance(request_id, str) or not request_id or len(request_id) > 160:
            raise RandomizerError('request_id required (max 160 characters)')
        if payload is None:
            payload = {}
        if not isinstance(payload, dict):
            raise RandomizerError('payload must be a JSON object')
        allowed = {'start', 'level', 'draft', 'reroll', 'lock', 'tokens',
                   'skill_card_grant', 'skill_card_equip', 'prestige', 'claim'}
        if action not in allowed:
            raise RandomizerError(f'unsupported action: {action}')
        payload_sha = fingerprint(payload)
        with self._transaction() as conn:
            prior = conn.execute('SELECT * FROM commands WHERE request_id=?', (request_id,)).fetchone()
            if prior:
                if (prior['actor'], prior['action'], prior['payload_sha']) != (actor, action, payload_sha):
                    raise RandomizerError('request_id already used for a different command')
                return json.loads(prior['response_json'])

            row = conn.execute('SELECT data FROM characters WHERE id=?', (actor,)).fetchone()
            old = json.loads(row['data']) if row else None
            before = list(old.get('spells', [])) if old else []
            if action == 'claim':
                check_id = str(payload.get('check_id', ''))
                check = next((x for x in self.catalog.get('reward_checks', []) if x['id'] == check_id), None)
                if check is None:
                    raise RandomizerError('unknown reward check')
                # Mob farming can be repeated across unique combat encounter IDs;
                # quest/boss one-time checks cannot be farmed via repeated requests.
                if check['kind'] == 'mob':
                    encounter_id = payload.get('encounter_id')
                    if not isinstance(encounter_id, str) or not 1 <= len(encounter_id) <= 128:
                        raise RandomizerError('mob claim requires a unique encounter_id')
                    claim_key = f'{check_id}:encounter:{encounter_id}'
                else:
                    claim_key = check_id
                claimed = conn.execute('SELECT reward_id FROM claims WHERE actor=? AND claim_key=?',
                                       (actor, claim_key)).fetchone()
                reward = str(claimed['reward_id']) if claimed else str(self.manifest['rewards'][check_id])
                if claimed is None:
                    conn.execute('INSERT INTO claims(actor,claim_key,reward_id) VALUES(?,?,?)',
                                 (actor, claim_key, reward))
                    self._add_event(conn, actor, request_id, 'item.grant',
                                    {'reward_id': reward, 'check_id': check_id, 'claim_key': claim_key})
                response = {'actor': actor, 'action': action, 'check_id': check_id,
                            'reward_id': reward, 'new_claim': claimed is None}
            else:
                engine = self._progression(actor, old)
                if action == 'start':
                    result = engine.create_character(actor)
                elif action == 'level':
                    result = engine.level_to(actor, payload['level'])
                elif action == 'draft':
                    result = engine.choose_draft(actor, payload['level'], payload['spell_id'])
                elif action == 'reroll':
                    result = engine.reroll(actor, payload['spell_id'])
                elif action == 'lock':
                    result = engine.lock_spell(actor, payload['spell_id'])
                elif action == 'tokens':
                    result = engine.grant_tokens(actor, payload['count'], request_id)
                elif action == 'skill_card_grant':
                    result = engine.grant_skill_card(actor, payload['spell_id'], request_id)
                elif action == 'skill_card_equip':
                    result = engine.equip_skill_card(actor, payload['spell_id'])
                else:
                    result = engine.prestige(actor, request_id)
                conn.execute('INSERT OR REPLACE INTO characters(id,data) VALUES(?,?)',
                             (actor, _json(result)))
                self._emit_spell_differences(conn, actor, request_id, before, result['spells'])
                response = {'actor': actor, 'action': action, 'character': copy.deepcopy(result)}
            conn.execute('INSERT INTO commands(request_id,actor,action,payload_sha,response_json) VALUES(?,?,?,?,?)',
                         (request_id, actor, action, payload_sha, _json(response)))
            return response

    def pending(self, actor: str, limit: int = 100) -> list[dict]:
        if not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise RandomizerError('pending event limit must be 1..1000')
        with self._transaction() as conn:
            rows = conn.execute('''SELECT id,request_id,kind,payload_json
                FROM outbox WHERE actor=? AND acknowledged=0 ORDER BY id LIMIT ?''',
                                (actor, limit)).fetchall()
            return [dict(id=r['id'], request_id=r['request_id'], kind=r['kind'],
                         payload=json.loads(r['payload_json'])) for r in rows]

    def ack(self, actor: str, event_id: int) -> bool:
        if not isinstance(event_id, int) or event_id < 1:
            raise RandomizerError('invalid event ID')
        with self._transaction() as conn:
            row = conn.execute('SELECT acknowledged FROM outbox WHERE id=? AND actor=?',
                               (event_id, actor)).fetchone()
            if row is None:
                raise RandomizerError('event unknown or belongs to another character')
            if row['acknowledged']:
                return False
            conn.execute('UPDATE outbox SET acknowledged=1 WHERE id=? AND actor=?', (event_id, actor))
            return True

    def lookup(self, kind: str, slot: str) -> str:
        if kind not in {'npc_identity', 'npc_roles', 'npc_locations',
                        'creatures', 'bosses', 'rewards', 'portals'}:
            raise RandomizerError('invalid mapping category')
        result = self.manifest[kind].get(slot)
        if result is None:
            raise RandomizerError('unknown mapping slot')
        return str(result)

    def status(self) -> dict:
        with self._transaction() as conn:
            characters = conn.execute('SELECT COUNT(*) FROM characters').fetchone()[0]
            pending = conn.execute('SELECT COUNT(*) FROM outbox WHERE acknowledged=0').fetchone()[0]
            claims = conn.execute('SELECT COUNT(*) FROM claims').fetchone()[0]
        return {'schema': 1, 'manifest_sha256': self.manifest['manifest_sha256'],
                'characters': characters, 'pending_events': pending, 'claims': claims}
