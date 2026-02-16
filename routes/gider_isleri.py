from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from sqlalchemy import extract, func
from models import db, Gider, BankaKasa, money, rate, normalize_currency
from utils import GUNCEL_KURLAR
from datetime import datetime
from decimal import Decimal

gider_bp = Blueprint('gider', __name__)

@gider_bp.route('/giderler')
def giderler():
    if 'logged_in' not in session:
        return redirect(url_for('genel.index'))

    # --- PAGINATION ---
    page = request.args.get('page', 1, type=int)
    per_page = 25

    pagination = (
        Gider.query
        .order_by(Gider.tarih.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    # Bu ayki toplam gider (sayfaya bağlı olmasın diye SQL ile hesapla)
    bu_ay = datetime.now()
    bu_ay_toplam = db.session.query(
        func.coalesce(func.sum(Gider.tutar * Gider.kur_degeri), Decimal("0"))
    ).filter(
        extract('month', Gider.tarih) == bu_ay.month,
        extract('year', Gider.tarih) == bu_ay.year
    ).scalar()

    bu_ay_toplam = money(bu_ay_toplam)

    kasalar = BankaKasa.query.all()

    return render_template(
        'giderler.html',
        giderler=pagination.items,   # template geriye dönük uyum
        pagination=pagination,       # template pagination bar için
        bu_ay_toplam=float(bu_ay_toplam),
        kurlar=GUNCEL_KURLAR,
        kasalar=kasalar
    )

@gider_bp.route('/gider_ekle', methods=['POST'])
def gider_ekle():
    if 'logged_in' not in session:
        return redirect(url_for('genel.index'))

    kategori = request.form.get('kategori')
    aciklama = request.form.get('aciklama')

    # TRY standardı
    birim_raw = request.form.get('birim') or 'TRY'
    birim = normalize_currency(birim_raw)

    # tutar -> Decimal (money)
    tutar_raw = request.form.get('tutar')
    try:
        tutar = money(tutar_raw or 0)
    except Exception:
        tutar = money("0")

    # Basit güvenlik: 0 veya negatif gider kaydı eklemeyelim
    if tutar <= Decimal("0"):
        flash('Gider tutarı 0 olamaz. Lütfen tutar girin.', 'warning')
        return redirect(request.referrer or url_for('gider.giderler'))

    # kur -> Decimal (rate)
    islem_kuru = rate(GUNCEL_KURLAR.get(birim, 1)) if birim != 'TRY' else rate(1)

    banka_kasa_id_raw = request.form.get('banka_kasa_id')
    try:
        banka_kasa_id = int(banka_kasa_id_raw) if banka_kasa_id_raw else None
    except (ValueError, TypeError):
        banka_kasa_id = None

    yeni_gider = Gider(
        kategori=kategori,
        aciklama=aciklama,
        tutar=tutar,
        birim=birim,
        kur_degeri=islem_kuru,
        banka_kasa_id=banka_kasa_id,
        tarih=datetime.now()
    )

    db.session.add(yeni_gider)
    db.session.commit()

    flash('Gider kaydı eklendi.', 'success')
    return redirect(url_for('gider.giderler'))

@gider_bp.route('/gider_sil/<int:id>', methods=['POST'])
def gider_sil(id):
    if 'logged_in' not in session:
        return redirect(url_for('genel.index'))

    gider = Gider.query.get_or_404(id)
    db.session.delete(gider)
    db.session.commit()

    flash('Gider kaydı silindi.', 'success')
    return redirect(url_for('gider.giderler'))
