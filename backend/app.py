# -*- coding: utf-8 -*-
"""
منصة إدارة وإنشاء العقود — تعاقد أجير
Flask app (Vercel-ready, Supabase / SQLite)
"""
import base64
import io
import os
import random
import re
import string
from datetime import date, datetime

from flask import (Flask, abort, flash, jsonify, redirect, render_template,
                   request, send_file, url_for)

from db import FIELDS, get_db
from pdfdoc import build_pdf

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__,
            template_folder=os.path.join(BASE_DIR, 'templates'),
            static_folder=os.path.join(BASE_DIR, 'static'))
app.secret_key = os.environ.get('SECRET_KEY', 'ajeer-contracts-2026-secret')
app.config['JSON_AS_ASCII'] = False
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024

PUBLIC_BASE = (os.environ.get('PUBLIC_BASE_URL') or '').rstrip('/')


# ---------------------------------------------------------------- helpers
def settings():
    return get_db().get_settings()


def gen_permit_no():
    for _ in range(60):
        no = 'TQ' + ''.join(random.choices(string.digits, k=9))
        if not get_db().permit_exists(no):
            return no
    return 'TQ' + str(int(datetime.now().timestamp()))[-9:]


def qr_bytes(text):
    import qrcode
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=0)
    qr.add_data(text)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def qr_data_uri(text):
    return 'data:image/png;base64,' + base64.b64encode(qr_bytes(text)).decode()


def base_url():
    return PUBLIC_BASE or request.url_root.rstrip('/')


def verify_link(permit_no, s=None):
    s = s or settings()
    return f"{(s.get('verify_domain') or 'https://ajeer.com.sa').rstrip('/')}/verify/{permit_no}"


def status_of(c):
    today = date.today()
    try:
        st = datetime.strptime(c['start_date'][:10], '%Y-%m-%d').date()
        en = datetime.strptime(c['end_date'][:10], '%Y-%m-%d').date()
    except Exception:
        return ('unknown', 'غير محدد')
    if today < st:
        return ('pending', 'لم يبدأ')
    if today > en:
        return ('expired', 'منتهي')
    if (en - today).days <= 30:
        return ('soon', 'ينتهي قريباً')
    return ('active', 'ساري')


def doc_context(c, s=None):
    s = s or settings()
    ctx = dict(c)
    ctx['qr'] = qr_data_uri(verify_link(c['permit_no'], s))
    ctx['verify_domain'] = s.get('verify_domain') or 'https://ajeer.com.sa'
    return ctx


def validate(form):
    errors = {}
    required = {
        'permit_no': 'رقم التصريح', 'worker_name': 'اسم العامل',
        'id_no': 'رقم الهوية / الإقامة', 'profession': 'المهنة',
        'nationality': 'الجنسية', 'provider_name': 'المنشأة المقدمة للخدمة',
        'provider_no': 'رقم المنشأة المقدمة للخدمة',
        'beneficiary_name': 'المنشأة المستفيدة من الخدمة',
        'beneficiary_no': 'رقم المنشأة المستفيدة من الخدمة',
        'description': 'نبذة عن التعاقد', 'start_date': 'تاريخ بداية التصريح',
        'end_date': 'تاريخ نهاية التصريح', 'site': 'مواقع العمل',
    }
    for k, label in required.items():
        if not (form.get(k) or '').strip():
            errors[k] = f'{label} مطلوب'
    for k in ('start_date', 'end_date'):
        v = (form.get(k) or '').strip()
        if v:
            try:
                datetime.strptime(v, '%Y-%m-%d')
            except ValueError:
                errors[k] = 'صيغة التاريخ يجب أن تكون YYYY-MM-DD'
    if not errors.get('start_date') and not errors.get('end_date'):
        if form['end_date'] < form['start_date']:
            errors['end_date'] = 'تاريخ النهاية يجب أن يكون بعد تاريخ البداية'
    if not re.match(r'^TQ\d{9}$', (form.get('permit_no') or '').strip()):
        errors['permit_no'] = 'رقم التصريح يجب أن يبدأ بـ TQ ثم 9 أرقام'
    return errors


def payload(src):
    return {k: (src.get(k) or '').strip() for k in FIELDS}


# ---------------------------------------------------------------- routes
@app.route('/')
def dashboard():
    db = get_db()
    q = (request.args.get('q') or '').strip()
    st = request.args.get('status') or 'all'
    try:
        contracts = db.list_contracts(q or None)
    except Exception as e:
        return render_template('error.html', page='', error=str(e)), 500
    for c in contracts:
        c['status'], c['status_label'] = status_of(c)
    stats = {
        'total': len(contracts),
        'active': sum(1 for c in contracts if c['status'] in ('active', 'soon')),
        'soon': sum(1 for c in contracts if c['status'] == 'soon'),
        'expired': sum(1 for c in contracts if c['status'] == 'expired'),
        'pending': sum(1 for c in contracts if c['status'] == 'pending'),
    }
    if st == 'active':
        contracts = [c for c in contracts if c['status'] in ('active', 'soon')]
    elif st != 'all':
        contracts = [c for c in contracts if c['status'] == st]
    return render_template('dashboard.html', page='dashboard', contracts=contracts,
                           stats=stats, settings=settings(), q=q, st=st,
                           backend=db.backend)


@app.route('/contracts/new', methods=['GET', 'POST'])
def new_contract():
    s = settings()
    db = get_db()
    if request.method == 'POST':
        data = payload(request.form)
        errors = validate(data)
        if not errors and db.permit_exists(data['permit_no']):
            errors['permit_no'] = 'رقم التصريح مستخدم مسبقاً'
        if errors:
            return render_template('form.html', page='new', c=data, errors=errors,
                                   settings=s, mode='new'), 422
        row = db.create_contract(data)
        flash('تم إنشاء التعاقد بنجاح — يمكنك الآن تحميل المستند', 'success')
        return redirect(url_for('view_contract', id_=row['id']))

    today = date.today()
    try:
        next_year = today.replace(year=today.year + 1)
    except ValueError:
        next_year = today.replace(year=today.year + 1, day=28)
    c = {
        'id': 0, 'permit_no': gen_permit_no(), 'worker_name': '', 'id_no': '',
        'profession': '', 'nationality': 'مصر',
        'provider_name': s['default_provider_name'], 'provider_no': s['default_provider_no'],
        'beneficiary_name': '', 'beneficiary_no': '', 'description': '',
        'start_date': today.isoformat(), 'end_date': next_year.isoformat(),
        'site': s['default_site'],
    }
    return render_template('form.html', page='new', c=c, errors={}, settings=s, mode='new')


@app.route('/contracts/<int:id_>/edit', methods=['GET', 'POST'])
def edit_contract(id_):
    db = get_db()
    c = db.get_contract(id_)
    if not c:
        abort(404)
    s = settings()
    if request.method == 'POST':
        data = payload(request.form)
        errors = validate(data)
        if not errors and db.permit_exists(data['permit_no'], exclude_id=id_):
            errors['permit_no'] = 'رقم التصريح مستخدم مسبقاً'
        if errors:
            data['id'] = id_
            return render_template('form.html', page='edit', c=data, errors=errors,
                                   settings=s, mode='edit'), 422
        db.update_contract(id_, data)
        flash('تم تحديث التعاقد بنجاح', 'success')
        return redirect(url_for('view_contract', id_=id_))
    return render_template('form.html', page='edit', c=c, errors={}, settings=s, mode='edit')


@app.route('/contracts/<int:id_>')
def view_contract(id_):
    c = get_db().get_contract(id_)
    if not c:
        abort(404)
    c['status'], c['status_label'] = status_of(c)
    return render_template('view.html', page='dashboard', c=c, settings=settings())


@app.route('/contracts/<int:id_>/delete', methods=['POST'])
def delete_contract(id_):
    db = get_db()
    c = db.get_contract(id_)
    if not c:
        abort(404)
    db.delete_contract(id_)
    flash(f'تم حذف التعاقد {c["permit_no"]}', 'success')
    return redirect(url_for('dashboard'))


@app.route('/contracts/<int:id_>/duplicate', methods=['POST'])
def duplicate_contract(id_):
    db = get_db()
    c = db.get_contract(id_)
    if not c:
        abort(404)
    data = {k: c[k] for k in FIELDS}
    data['permit_no'] = gen_permit_no()
    row = db.create_contract(data)
    flash('تم إنشاء نسخة جديدة من التعاقد', 'success')
    return redirect(url_for('edit_contract', id_=row['id']))


@app.route('/contracts/<int:id_>/print')
def print_contract(id_):
    c = get_db().get_contract(id_)
    if not c:
        abort(404)
    auto = request.args.get('auto', '1') != '0'
    return render_template('contract_doc.html', c=doc_context(c), mode='print',
                           auto_print=auto, assets=url_for('static', filename=''))


@app.route('/contracts/<int:id_>/embed')
def embed_contract(id_):
    c = get_db().get_contract(id_)
    if not c:
        abort(404)
    return render_template('contract_doc.html', c=doc_context(c), mode='embed',
                           auto_print=False, assets=url_for('static', filename=''))


@app.route('/contracts/<int:id_>/pdf')
def pdf_contract(id_):
    """توليد PDF مطابق للنموذج — fpdf2 + HarfBuzz (بدون أي مكتبات نظام)."""
    c = get_db().get_contract(id_)
    if not c:
        abort(404)
    ctx = doc_context(c)
    try:
        raw = build_pdf(ctx, qr_bytes(verify_link(c['permit_no'])))
    except Exception:
        return redirect(url_for('print_contract', id_=id_, auto=0))
    buf = io.BytesIO(raw)
    buf.seek(0)
    return send_file(buf, mimetype='application/pdf', as_attachment=True,
                     download_name=f'{c["permit_no"]}.pdf')


@app.route('/contracts/preview', methods=['POST'])
def preview():
    raw = request.get_json(silent=True) if request.is_json else request.form.to_dict()
    data = {k: (raw.get(k) or '').strip() for k in FIELDS}
    data.setdefault('id', 0)
    return render_template('contract_doc.html', c=doc_context(data), mode='embed',
                           auto_print=False, assets=url_for('static', filename=''))


@app.route('/verify/<permit_no>')
def verify(permit_no):
    c = get_db().get_by_permit(permit_no)
    status = status_of(c) if c else ('unknown', 'غير موجود')
    return render_template('verify.html', c=c, status=status, settings=settings())


@app.route('/settings', methods=['GET', 'POST'])
def settings_page():
    db = get_db()
    if request.method == 'POST':
        for k in ('org_name', 'verify_domain', 'default_provider_name',
                  'default_provider_no', 'default_site'):
            v = (request.form.get(k) or '').strip()
            if v:
                db.save_setting(k, v)
        flash('تم حفظ الإعدادات', 'success')
        return redirect(url_for('settings_page'))
    return render_template('settings.html', page='settings', settings=settings(),
                           backend=db.backend)


@app.route('/api/qr/<permit_no>.png')
def qr_png(permit_no):
    target = request.args.get('target') or verify_link(permit_no)
    buf = io.BytesIO(qr_bytes(target))
    buf.seek(0)
    return send_file(buf, mimetype='image/png')


@app.route('/api/health')
def health():
    db = get_db()
    try:
        n = db.count()
        return jsonify(status='ok', backend=db.backend, contracts=n,
                       time=datetime.utcnow().isoformat() + 'Z')
    except Exception as e:
        return jsonify(status='error', backend=db.backend, detail=str(e)), 500


@app.errorhandler(404)
def not_found(e):
    return render_template('404.html', page=''), 404


@app.errorhandler(500)
def server_error(e):
    return render_template('error.html', page='', error='حدث خطأ غير متوقع'), 500


@app.context_processor
def inject_globals():
    return dict(current_year=date.today().year, today=date.today())


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=bool(os.environ.get('DEBUG')))
