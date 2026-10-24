# -*- coding: utf-8 -*-
"""
طبقة البيانات — تعمل بواجهتين:
  • Supabase (PostgREST عبر HTTPS) عند وجود SUPABASE_URL + SUPABASE_SERVICE_KEY
  • SQLite محلياً عند التطوير (FALLBACK تلقائي)
"""
import json
import os
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

SUPABASE_URL = (os.environ.get('SUPABASE_URL') or '').rstrip('/')
SUPABASE_KEY = os.environ.get('SUPABASE_SERVICE_KEY') or ''
USE_SUPABASE = bool(SUPABASE_URL and SUPABASE_KEY)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.environ.get('SQLITE_PATH') or os.path.join(BASE_DIR, 'data', 'ajeer.db')

FIELDS = ['permit_no', 'worker_name', 'id_no', 'profession', 'nationality', 'provider_name',
          'provider_no', 'beneficiary_name', 'beneficiary_no', 'description',
          'start_date', 'end_date', 'site']

DEFAULT_SETTINGS = {
    'org_name': 'إدارة العقود',
    'verify_domain': '',  # فارغ = يُستخدم نطاق التطبيق الحالي تلقائياً
    'verify_path': '/agiar/index.php',
    'default_provider_name': 'مؤسسة مكعب العربية للمقاولات العامة',
    'default_provider_no': '1970887-6',
    'default_site': 'الرياض',
}

SEED = [
    ('TQ101515442', 'احمد صبحى عبد الواحد على', '2572542054', 'عامل تحميل وتنزيل', 'مصر',
     'مؤسسة مكعب العربية للمقاولات العامة', '1970887-6',
     'شركة أسيند جلوبال إينوفاتيف سلوشنز', '1-4624381',
     'مشاريع تركيب المصاعد الخاصة بالشركة', '2026-10-15', '2027-10-15', 'الرياض'),
    ('TQ101515443', 'محمد عبد الرحمن سعيد الحريري', '2411873306', 'فني كهرباء', 'السودان',
     'مؤسسة مكعب العربية للمقاولات العامة', '1970887-6',
     'شركة أسيند جلوبال إينوفاتيف سلوشنز', '1-4624381',
     'أعمال الصيانة الكهربائية للمشروع', '2026-09-01', '2027-09-01', 'الرياض'),
    ('TQ101515444', 'راجيش كومار ناير', '2338765120', 'عامل بناء', 'الهند',
     'مؤسسة مكعب العربية للمقاولات العامة', '1970887-6',
     'شركة تطوير المشاريع العمرانية', '2-1157234',
     'أعمال البناء والتشييد في موقع جدة', '2026-01-10', '2026-07-10', 'جدة'),
]


# ----------------------------------------------------------------------
#  Supabase REST
# ----------------------------------------------------------------------
def _rest(path, method='GET', params=None, body=None, prefer=None):
    url = f'{SUPABASE_URL}/rest/v1/{path}'
    if params:
        url += '?' + urllib.parse.urlencode(params, safe='*,():.%')
    data = json.dumps(body).encode() if body is not None else None
    headers = {
        'apikey': SUPABASE_KEY,
        'Authorization': 'Bearer ' + SUPABASE_KEY,
        'Content-Type': 'application/json',
    }
    if prefer:
        headers['Prefer'] = prefer
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'Supabase {e.code}: {e.read().decode()[:300]}')


class SupabaseDB:
    backend = 'supabase'

    # ---- contracts ----
    def list_contracts(self, q=None, created_by=None):
        params = {'select': '*', 'order': 'id.desc'}
        if created_by is not None:
            params['created_by'] = f'eq.{created_by}'
        if q:
            safe = q.replace(',', ' ').replace('(', ' ').replace(')', ' ')
            params['or'] = (f'(permit_no.ilike.*{safe}*,worker_name.ilike.*{safe}*,'
                            f'id_no.ilike.*{safe}*,beneficiary_name.ilike.*{safe}*,'
                            f'profession.ilike.*{safe}*)')
        rows = _rest('contracts', params=params) or []
        return [self._norm(r) for r in rows]

    def get_contract(self, cid):
        rows = _rest('contracts', params={'id': f'eq.{cid}', 'select': '*'}) or []
        return self._norm(rows[0]) if rows else None

    def get_by_permit(self, permit_no):
        rows = _rest('contracts', params={'permit_no': f'eq.{permit_no}', 'select': '*'}) or []
        return self._norm(rows[0]) if rows else None

    def get_by_token(self, token):
        rows = _rest('contracts', params={'verify_token': f'eq.{token}', 'select': '*'}) or []
        return self._norm(rows[0]) if rows else None

    def permit_exists(self, permit_no, exclude_id=None):
        params = {'permit_no': f'eq.{permit_no}', 'select': 'id'}
        if exclude_id:
            params['id'] = f'neq.{exclude_id}'
        return bool(_rest('contracts', params=params))

    def create_contract(self, data):
        now = datetime.utcnow().isoformat()
        payload = {k: data[k] for k in FIELDS}
        for k in ('created_by', 'created_by_name', 'created_by_email', 'verify_token'):
            if data.get(k) is not None:
                payload[k] = data[k]
        payload['created_at'] = now
        payload['updated_at'] = now
        rows = _rest('contracts', method='POST', body=payload,
                     prefer='return=representation') or []
        return self._norm(rows[0]) if rows else None

    def update_contract(self, cid, data):
        payload = {k: data[k] for k in FIELDS}
        payload['updated_at'] = datetime.utcnow().isoformat()
        rows = _rest('contracts', method='PATCH', params={'id': f'eq.{cid}'},
                     body=payload, prefer='return=representation') or []
        return self._norm(rows[0]) if rows else None

    def delete_contract(self, cid):
        _rest('contracts', method='DELETE', params={'id': f'eq.{cid}'},
              prefer='return=minimal')

    def count(self):
        rows = _rest('contracts', params={'select': 'id'}) or []
        return len(rows)

    def count_by_user(self, uid):
        rows = _rest('contracts', params={'select': 'id', 'created_by': f'eq.{uid}'}) or []
        return len(rows)

    def counts_by_user(self):
        rows = _rest('contracts', params={'select': 'created_by'}) or []
        out = {}
        for r in rows:
            k = r.get('created_by')
            if k is not None:
                out[int(k)] = out.get(int(k), 0) + 1
        return out

    def bulk_update_user_contracts(self, uid, fields):
        payload = dict(fields)
        payload['updated_at'] = datetime.utcnow().isoformat()
        return _rest('contracts', method='PATCH', params={'created_by': f'eq.{uid}'},
                     body=payload, prefer='return=minimal')

    def bulk_delete_user_contracts(self, uid):
        return _rest('contracts', method='DELETE', params={'created_by': f'eq.{uid}'},
                     prefer='return=minimal')

    def missing_tokens(self):
        rows = _rest('contracts', params={'select': 'id,permit_no,verify_token'}) or []
        return [r for r in rows if not r.get('verify_token')]

    def set_token(self, cid, token):
        return _rest('contracts', method='PATCH', params={'id': f'eq.{cid}'},
                     body={'verify_token': token}, prefer='return=minimal')

    # ---- settings ----
    def get_settings(self):
        rows = _rest('settings', params={'select': 'key,value'}) or []
        s = dict(DEFAULT_SETTINGS)
        s.update({r['key']: r['value'] for r in rows if r.get('value')})
        return s

    def save_setting(self, key, value):
        _rest('settings', method='POST', body={'key': key, 'value': value},
              prefer='resolution=merge-duplicates,return=minimal')

    @staticmethod
    def _norm(row):
        if not row:
            return row
        out = dict(row)
        out['id'] = int(out['id'])
        for k in ('start_date', 'end_date'):
            v = out.get(k)
            if isinstance(v, str):
                out[k] = v[:10]
        return out


# ----------------------------------------------------------------------
#  SQLite (تطوير محلي / احتياطي)
# ----------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    permit_no TEXT UNIQUE NOT NULL, worker_name TEXT NOT NULL, id_no TEXT NOT NULL,
    profession TEXT NOT NULL, nationality TEXT NOT NULL, provider_name TEXT NOT NULL,
    provider_no TEXT NOT NULL, beneficiary_name TEXT NOT NULL, beneficiary_no TEXT NOT NULL,
    description TEXT NOT NULL, start_date TEXT NOT NULL, end_date TEXT NOT NULL,
    site TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    created_by INTEGER, created_by_name TEXT, created_by_email TEXT, verify_token TEXT);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
"""


class SqliteDB:
    backend = 'sqlite'

    def __init__(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        self.con = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.executescript(SCHEMA)
        cols = {r[1] for r in self.con.execute('PRAGMA table_info(contracts)').fetchall()}
        for col, typ in (('created_by', 'INTEGER'), ('created_by_name', 'TEXT'),
                         ('created_by_email', 'TEXT'), ('verify_token', 'TEXT')):
            if col not in cols:
                self.con.execute(f'ALTER TABLE contracts ADD COLUMN {col} {typ}')
        for k, v in DEFAULT_SETTINGS.items():
            self.con.execute('INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)', (k, v))
        if self.con.execute('SELECT COUNT(*) FROM contracts').fetchone()[0] == 0:
            now = datetime.now().strftime('%Y-%m-%d %H:%M')
            self.con.executemany(
                'INSERT INTO contracts (permit_no,worker_name,id_no,profession,nationality,'
                'provider_name,provider_no,beneficiary_name,beneficiary_no,description,'
                'start_date,end_date,site,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                [r + (now, now) for r in SEED])
        self.con.commit()

    def list_contracts(self, q=None, created_by=None):
        sql = 'SELECT * FROM contracts'
        where, params = [], []
        if q:
            where.append('(permit_no LIKE ? OR worker_name LIKE ? OR id_no LIKE ?'
                         ' OR beneficiary_name LIKE ? OR profession LIKE ?)')
            params = [f'%{q}%'] * 5
        if created_by is not None:
            where.append('created_by IS ?')
            params.append(created_by)
        if where:
            sql += ' WHERE ' + ' AND '.join(where)
        sql += ' ORDER BY id DESC'
        return [dict(r) for r in self.con.execute(sql, params).fetchall()]

    def get_contract(self, cid):
        r = self.con.execute('SELECT * FROM contracts WHERE id=?', (cid,)).fetchone()
        return dict(r) if r else None

    def get_by_permit(self, permit_no):
        r = self.con.execute('SELECT * FROM contracts WHERE permit_no=?', (permit_no,)).fetchone()
        return dict(r) if r else None

    def get_by_token(self, token):
        r = self.con.execute('SELECT * FROM contracts WHERE verify_token=?', (token,)).fetchone()
        return dict(r) if r else None

    def missing_tokens(self):
        rows = self.con.execute('SELECT id,permit_no,verify_token FROM contracts').fetchall()
        return [dict(r) for r in rows if not r['verify_token']]

    def set_token(self, cid, token):
        self.con.execute('UPDATE contracts SET verify_token=? WHERE id=?', (token, cid))
        self.con.commit()

    def permit_exists(self, permit_no, exclude_id=None):
        if exclude_id:
            return bool(self.con.execute('SELECT 1 FROM contracts WHERE permit_no=? AND id<>?',
                                         (permit_no, exclude_id)).fetchone())
        return bool(self.con.execute('SELECT 1 FROM contracts WHERE permit_no=?',
                                     (permit_no,)).fetchone())

    def create_contract(self, data):
        now = datetime.now().strftime('%Y-%m-%d %H:%M')
        cur = self.con.execute(
            'INSERT INTO contracts (permit_no,worker_name,id_no,profession,nationality,'
            'provider_name,provider_no,beneficiary_name,beneficiary_no,description,'
            'start_date,end_date,site,created_at,updated_at,created_by,created_by_name,'
            'created_by_email,verify_token) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            tuple(data[k] for k in FIELDS) + (now, now, data.get('created_by'),
                                               data.get('created_by_name'),
                                               data.get('created_by_email'),
                                               data.get('verify_token')))
        self.con.commit()
        return self.get_contract(cur.lastrowid)

    def update_contract(self, cid, data):
        self.con.execute(
            'UPDATE contracts SET permit_no=?,worker_name=?,id_no=?,profession=?,nationality=?,'
            'provider_name=?,provider_no=?,beneficiary_name=?,beneficiary_no=?,description=?,'
            'start_date=?,end_date=?,site=?,updated_at=? WHERE id=?',
            tuple(data[k] for k in FIELDS) + (datetime.now().strftime('%Y-%m-%d %H:%M'), cid))
        self.con.commit()
        return self.get_contract(cid)

    def delete_contract(self, cid):
        self.con.execute('DELETE FROM contracts WHERE id=?', (cid,))
        self.con.commit()

    def count(self):
        return self.con.execute('SELECT COUNT(*) FROM contracts').fetchone()[0]

    def count_by_user(self, uid):
        return self.con.execute('SELECT COUNT(*) FROM contracts WHERE created_by IS ?',
                                (uid,)).fetchone()[0]

    def counts_by_user(self):
        rows = self.con.execute('SELECT created_by, COUNT(*) c FROM contracts '
                                'WHERE created_by IS NOT NULL GROUP BY created_by').fetchall()
        return {int(r['created_by']): r['c'] for r in rows}

    def bulk_update_user_contracts(self, uid, fields):
        if not fields:
            return
        sets = ', '.join(f'{k}=?' for k in fields)
        self.con.execute(f'UPDATE contracts SET {sets} WHERE created_by IS ?',
                         tuple(fields.values()) + (uid,))
        self.con.commit()

    def bulk_delete_user_contracts(self, uid):
        self.con.execute('DELETE FROM contracts WHERE created_by IS ?', (uid,))
        self.con.commit()

    def get_settings(self):
        s = dict(DEFAULT_SETTINGS)
        s.update({r['key']: r['value'] for r in
                  self.con.execute('SELECT key,value FROM settings').fetchall() if r['value']})
        return s

    def save_setting(self, key, value):
        self.con.execute('INSERT INTO settings(key,value) VALUES(?,?) '
                         'ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, value))
        self.con.commit()


_db = None


def get_db():
    global _db
    if _db is None:
        _db = SupabaseDB() if USE_SUPABASE else SqliteDB()
    return _db
