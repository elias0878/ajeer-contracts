# -*- coding: utf-8 -*-
"""
طبقة بيانات الحسابات والصلاحيات والجلسات وسجل النشاط.
تستخدم نفس واجهة db.py: Supabase (PostgREST) في الإنتاج، SQLite محلياً.
"""
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import db as _db

USE_SUPABASE = _db.USE_SUPABASE
SQLITE_PATH = _db.DB_PATH

AUTH_SCHEMA = """
CREATE TABLE IF NOT EXISTS app_users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'user',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_by INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_login_at TEXT,
    contract_limit INTEGER,
    expires_at TEXT
);
CREATE TABLE IF NOT EXISTS app_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    token_hash TEXT UNIQUE NOT NULL,
    expires_at TEXT NOT NULL,
    user_agent TEXT, ip TEXT,
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS app_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    permission TEXT NOT NULL,
    granted INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL,
    UNIQUE(user_id, permission)
);
CREATE TABLE IF NOT EXISTS app_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER,
    actor_email TEXT NOT NULL DEFAULT 'system',
    action TEXT NOT NULL,
    entity TEXT NOT NULL DEFAULT '',
    entity_id TEXT NOT NULL DEFAULT '',
    details TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS app_audit_created_idx ON app_audit_log(created_at DESC);
"""

_con = None


def _sql():
    global _con
    if _con is None:
        _con = sqlite3.connect(SQLITE_PATH, check_same_thread=False)
        _con.row_factory = sqlite3.Row
        _con.executescript(AUTH_SCHEMA)
        _con.commit()
    return _con


def _now():
    return datetime.now(timezone.utc).isoformat()


def _rows(cur):
    return [dict(r) for r in cur.fetchall()]


def _rest(*a, **kw):
    return _db._rest(*a, **kw)


# ======================================================================
#  المستخدمون
# ======================================================================
USER_FIELDS = ('email', 'password_hash', 'full_name', 'role', 'is_active',
               'created_by', 'last_login_at', 'contract_limit', 'expires_at')


def list_users():
    if USE_SUPABASE:
        return _rest('app_users', params={'select': '*', 'order': 'id.asc'}) or []
    cur = _sql().execute('SELECT * FROM app_users ORDER BY id ASC')
    return _rows(cur)


def get_user(uid):
    if uid is None:
        return None
    if USE_SUPABASE:
        r = _rest('app_users', params={'id': f'eq.{uid}', 'select': '*'}) or []
        return r[0] if r else None
    ren = _sql().execute('SELECT * FROM app_users WHERE id=?', (uid,)).fetchone()
    return dict(ren) if ren else None


def get_user_by_email(email):
    if not email:
        return None
    if USE_SUPABASE:
        r = _rest('app_users', params={'email': f'eq.{email}', 'select': '*'}) or []
        return r[0] if r else None
    ren = _sql().execute('SELECT * FROM app_users WHERE email=?', (email,)).fetchone()
    return dict(ren) if ren else None


def create_user(data):
    now = _now()
    payload = {k: data.get(k) for k in USER_FIELDS if k in data}
    payload['created_at'] = now
    payload['updated_at'] = now
    payload.setdefault('role', 'user')
    payload.setdefault('is_active', True)
    payload.setdefault('full_name', '')
    if USE_SUPABASE:
        rows = _rest('app_users', method='POST', body=payload,
                     prefer='return=representation') or []
        return rows[0] if rows else None
    cols = ', '.join(payload.keys())
    qs = ', '.join('?' * len(payload))
    cur = _sql().execute(f'INSERT INTO app_users ({cols}) VALUES ({qs})',
                         tuple(payload.values()))
    _sql().commit()
    return get_user(cur.lastrowid)


def update_user(uid, fields):
    if not fields:
        return get_user(uid)
    fields = dict(fields)
    fields['updated_at'] = _now()
    if USE_SUPABASE:
        rows = _rest('app_users', method='PATCH', params={'id': f'eq.{uid}'},
                     body=fields, prefer='return=representation') or []
        return rows[0] if rows else None
    sets = ', '.join(f'{k}=?' for k in fields)
    _sql().execute(f'UPDATE app_users SET {sets} WHERE id=?',
                   tuple(fields.values()) + (uid,))
    _sql().commit()
    return get_user(uid)


def delete_user(uid):
    if USE_SUPABASE:
        _rest('app_permissions', method='DELETE', params={'user_id': f'eq.{uid}'},
              prefer='return=minimal')
        _rest('app_sessions', method='DELETE', params={'user_id': f'eq.{uid}'},
              prefer='return=minimal')
        _rest('app_users', method='DELETE', params={'id': f'eq.{uid}'},
              prefer='return=minimal')
        return
    c = _sql()
    c.execute('DELETE FROM app_permissions WHERE user_id=?', (uid,))
    c.execute('DELETE FROM app_sessions WHERE user_id=?', (uid,))
    c.execute('DELETE FROM app_users WHERE id=?', (uid,))
    c.commit()


def count_users():
    if USE_SUPABASE:
        return len(_rest('app_users', params={'select': 'id'}) or [])
    return _sql().execute('SELECT COUNT(*) FROM app_users').fetchone()[0]


# ======================================================================
#  الصلاحيات
# ======================================================================
def get_permissions(uid):
    if USE_SUPABASE:
        rows = _rest('app_permissions', params={'user_id': f'eq.{uid}', 'select': 'permission,granted'}) or []
    else:
        rows = _rows(_sql().execute(
            'SELECT permission, granted FROM app_permissions WHERE user_id=?', (uid,)))
    return [r['permission'] for r in rows if r.get('granted')]


def all_permissions_map():
    """{user_id: [permission, ...]} — استعلام واحد لصفحة الإدارة"""
    if USE_SUPABASE:
        rows = _rest('app_permissions', params={'select': 'user_id,permission,granted'}) or []
    else:
        rows = _rows(_sql().execute('SELECT user_id, permission, granted FROM app_permissions'))
    out = {}
    for r in rows:
        if r.get('granted'):
            out.setdefault(int(r['user_id']), []).append(r['permission'])
    return out


def set_permissions(uid, permissions):
    """استبدال كامل لصلاحيات المستخدم."""
    permissions = list(dict.fromkeys(p for p in permissions if p))
    now = _now()
    if USE_SUPABASE:
        _rest('app_permissions', method='DELETE', params={'user_id': f'eq.{uid}'},
              prefer='return=minimal')
        if permissions:
            body = [{'user_id': uid, 'permission': p, 'granted': True,
                     'updated_at': now} for p in permissions]
            _rest('app_permissions', method='POST', body=body, prefer='return=minimal')
        return
    c = _sql()
    c.execute('DELETE FROM app_permissions WHERE user_id=?', (uid,))
    c.executemany('INSERT INTO app_permissions (user_id, permission, granted, updated_at) VALUES (?,?,?,?)',
                  [(uid, p, 1, now) for p in permissions])
    c.commit()


# ======================================================================
#  الجلسات
# ======================================================================
def create_session(uid, token_hash, expires_at, user_agent=None, ip=None):
    now = _now()
    payload = {'user_id': uid, 'token_hash': token_hash, 'expires_at': expires_at,
               'user_agent': (user_agent or '')[:250], 'ip': (ip or '')[:64],
               'created_at': now, 'last_seen_at': now}
    if USE_SUPABASE:
        rows = _rest('app_sessions', method='POST', body=payload,
                     prefer='return=representation') or []
        return rows[0] if rows else None
    c = _sql()
    cur = c.execute(
        'INSERT INTO app_sessions (user_id,token_hash,expires_at,user_agent,ip,created_at,last_seen_at)'
        ' VALUES (?,?,?,?,?,?,?)',
        (uid, token_hash, expires_at, payload['user_agent'], payload['ip'], now, now))
    c.commit()
    return cur.lastrowid


def get_session(token_hash):
    if USE_SUPABASE:
        r = _rest('app_sessions', params={'token_hash': f'eq.{token_hash}', 'select': '*'}) or []
        return r[0] if r else None
    ren = _sql().execute('SELECT * FROM app_sessions WHERE token_hash=?', (token_hash,)).fetchone()
    return dict(ren) if ren else None


def touch_session(token_hash):
    try:
        if USE_SUPABASE:
            _rest('app_sessions', method='PATCH', params={'token_hash': f'eq.{token_hash}'},
                  body={'last_seen_at': _now()}, prefer='return=minimal')
        else:
            _sql().execute('UPDATE app_sessions SET last_seen_at=? WHERE token_hash=?',
                           (_now(), token_hash))
            _sql().commit()
    except Exception:
        pass


def delete_session(token_hash):
    if USE_SUPABASE:
        _rest('app_sessions', method='DELETE', params={'token_hash': f'eq.{token_hash}'},
              prefer='return=minimal')
    else:
        _sql().execute('DELETE FROM app_sessions WHERE token_hash=?', (token_hash,))
        _sql().commit()


def delete_sessions_for_user(uid, keep_hash=None):
    if USE_SUPABASE:
        params = {'user_id': f'eq.{uid}'}
        if keep_hash:
            params['token_hash'] = f'neq.{keep_hash}'
        _rest('app_sessions', method='DELETE', params=params, prefer='return=minimal')
        return
    c = _sql()
    if keep_hash:
        c.execute('DELETE FROM app_sessions WHERE user_id=? AND token_hash<>?', (uid, keep_hash))
    else:
        c.execute('DELETE FROM app_sessions WHERE user_id=?', (uid,))
    c.commit()


def active_sessions_count(uid):
    if USE_SUPABASE:
        return len(_rest('app_sessions', params={'user_id': f'eq.{uid}', 'select': 'id'}) or [])
    return _sql().execute('SELECT COUNT(*) FROM app_sessions WHERE user_id=?', (uid,)).fetchone()[0]


def purge_expired_sessions():
    cutoff = datetime.now(timezone.utc).isoformat()
    try:
        if USE_SUPABASE:
            _rest('app_sessions', method='DELETE', params={'expires_at': f'lt.{cutoff}'},
                  prefer='return=minimal')
        else:
            _sql().execute('DELETE FROM app_sessions WHERE expires_at < ?', (cutoff,))
            _sql().commit()
    except Exception:
        pass


# ======================================================================
#  سجل النشاط
# ======================================================================
def add_audit(actor_id, actor_email, action, entity='', entity_id='', details=None):
    payload = {
        'actor_id': actor_id,
        'actor_email': actor_email or 'system',
        'action': action,
        'entity': entity or '',
        'entity_id': str(entity_id or ''),
        'details': details or {},
        'created_at': _now(),
    }
    if USE_SUPABASE:
        _rest('app_audit_log', method='POST', body=payload, prefer='return=minimal')
        return
    c = _sql()
    c.execute('INSERT INTO app_audit_log (actor_id,actor_email,action,entity,entity_id,details,created_at)'
              ' VALUES (?,?,?,?,?,?,?)',
              (actor_id, payload['actor_email'], action, payload['entity'],
               payload['entity_id'], json.dumps(details or {}, ensure_ascii=False),
               payload['created_at']))
    c.commit()


def list_audit(limit=200, actor=None, action=None, q=None):
    params = {'select': '*', 'order': 'id.desc', 'limit': str(limit)}
    if USE_SUPABASE:
        if actor:
            params['actor_email'] = f'ilike.*{actor}*'
        if action:
            params['action'] = f'like.{action}*'
        if q:
            safe = q.replace(',', ' ').replace('(', ' ').replace(')', ' ')
            params['or'] = f'(action.ilike.*{safe}*,entity.ilike.*{safe}*,entity_id.ilike.*{safe}*,actor_email.ilike.*{safe}*)'
        return _rest('app_audit_log', params=params) or []

    where, args = [], []
    if actor:
        where.append('actor_email LIKE ?'); args.append(f'%{actor}%')
    if action:
        where.append('action LIKE ?'); args.append(f'{action}%')
    if q:
        where.append('(action LIKE ? OR entity LIKE ? OR entity_id LIKE ? OR actor_email LIKE ?)')
        args += [f'%{q}%'] * 4
    sql = 'SELECT * FROM app_audit_log'
    if where:
        sql += ' WHERE ' + ' AND '.join(where)
    sql += ' ORDER BY id DESC LIMIT ?'
    args.append(limit)
    rows = _rows(_sql().execute(sql, tuple(args)))
    for r in rows:
        try:
            r['details'] = json.loads(r['details'] or '{}')
        except Exception:
            r['details'] = {}
    return rows


def count_audit():
    if USE_SUPABASE:
        return len(_rest('app_audit_log', params={'select': 'id'}) or [])
    return _sql().execute('SELECT COUNT(*) FROM app_audit_log').fetchone()[0]
