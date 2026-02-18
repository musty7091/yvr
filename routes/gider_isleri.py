from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from sqlalchemy import extract, func
from models import db, Gider, BankaKasa, money, rate, normalize_currency
from utils import GUNCEL_KURLAR
from datetime import datetime
from decimal import Decimal

gider_bp = Blueprint('gider', __name__)


def _login_gerekli():
    return bool(session.get("logged_in"))


def _safe_decimal_one(v):
    try:
        if v is None:
            return Decimal("1")
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v))
    except Exception:
        return Decimal("1")


def _safe_kasa_bakiye(kasa):
    """
    kasa.bakiye None / boş ise 0 kabul et.
    """
    try:
        return money(getattr(kasa, "bakiye", Decimal("0")) or Decimal("0"))
    except Exception:
        return money("0")


@gider_bp.route('/giderler')
def giderler():
    if not _login_gerekli():
        return redirect(url_for('genel.index'))

    # Template için TRY’yi garanti et
    kurlar = dict(GUNCEL_KURLAR)
    kurlar.setdefault("TRY", 1)

    page = request.args.get('page', 1, type=int)

    # Gider listesini sayfalı al
    pagination = (
        Gider.query
        .order_by(Gider.tarih.desc())
        .paginate(page=page, per_page=25, error_out=False)
    )

    # Bu ay toplam gider (TRY karşılığı)
    bu_ay = datetime.now()
    bu_ay_toplam = db.session.query(
        func.coalesce(func.sum(Gider.tutar * func.coalesce(Gider.kur_degeri, Decimal("1"))), Decimal("0"))
    ).filter(
        extract('month', Gider.tarih) == bu_ay.month,
        extract('year', Gider.tarih) == bu_ay.year
    ).scalar()

    kasalar = BankaKasa.query.all()

    return render_template(
        'giderler.html',
        giderler=pagination.items,   # template geriye dönük uyum
        pagination=pagination,       # template pagination bar için
        bu_ay_toplam=money(bu_ay_toplam),
        kurlar=kurlar,
        kasalar=kasalar
    )


@gider_bp.route('/gider_ekle', methods=['POST'])
def gider_ekle():
    if not _login_gerekli():
        return redirect(url_for('genel.index'))

    kategori = (request.form.get('kategori') or '').strip()
    aciklama = (request.form.get('aciklama') or '').strip()

    # tarih alanı boş kalırsa bugünün tarihi
    tarih_raw = request.form.get('tarih')
    try:
        tarih = datetime.strptime(tarih_raw, '%Y-%m-%d') if tarih_raw else datetime.now()
    except Exception:
        tarih = datetime.now()

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
        return redirect(url_for('gider.giderler'))

    # Kur (TRY ise 1)
    try:
        kur_degeri = rate(request.form.get('kur_degeri') or 1)
    except Exception:
        kur_degeri = rate(1)

    if birim == "TRY":
        kur_degeri = rate(1)

    # Kasa seçimi (models.py kanonu: banka_kasa_id)
    # Template/HTML geriye dönük uyum: önce banka_kasa_id, yoksa kasa_id
    kasa_id_raw = request.form.get('banka_kasa_id') or request.form.get('kasa_id')
    kasa_id = int(kasa_id_raw) if (kasa_id_raw and str(kasa_id_raw).isdigit()) else None

    # Kasa bakiyesi güncelle (TRY karşılığı)
    try:
        try_tutar = money(tutar * (kur_degeri or Decimal("1")))
    except Exception:
        try_tutar = money("0")

    if kasa_id:
        kasa = BankaKasa.query.get(kasa_id)
        if kasa:
            mevcut_bakiye = _safe_kasa_bakiye(kasa)
            kasa.bakiye = money(mevcut_bakiye - try_tutar)

    db.session.add(Gider(
        kategori=kategori,
        aciklama=aciklama,
        tarih=tarih,
        tutar=tutar,
        birim=birim,
        kur_degeri=kur_degeri,
        banka_kasa_id=kasa_id
    ))

    db.session.commit()
    flash('Gider kaydı eklendi.', 'success')
    return redirect(url_for('gider.giderler'))


@gider_bp.route('/gider_sil/<int:id>', methods=['POST'])
def gider_sil(id):
    if not _login_gerekli():
        return redirect(url_for('genel.index'))

    g = Gider.query.get_or_404(id)

    # Silinen gider kasa bakiyesini geri alsın (TRY karşılığı)
    kur_d = _safe_decimal_one(getattr(g, "kur_degeri", None))
    try:
        try_tutar = money(g.tutar * kur_d)
    except Exception:
        try_tutar = money("0")

    if g.banka_kasa_id:
        kasa = BankaKasa.query.get(g.banka_kasa_id)
        if kasa:
            mevcut_bakiye = _safe_kasa_bakiye(kasa)
            kasa.bakiye = money(mevcut_bakiye + try_tutar)

    db.session.delete(g)
    db.session.commit()
    flash('Gider silindi.', 'info')
    return redirect(url_for('gider.giderler'))
