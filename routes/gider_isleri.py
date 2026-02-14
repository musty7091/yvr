from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from models import db, Gider, BankaKasa
from utils import GUNCEL_KURLAR
from datetime import datetime

gider_bp = Blueprint('gider', __name__)

@gider_bp.route('/giderler')
def giderler():
    if 'logged_in' not in session:
        return redirect(url_for('genel.index'))

    # Tüm giderleri tarihe göre en yeni üstte olacak şekilde çekiyoruz
    gider_listesi = Gider.query.order_by(Gider.tarih.desc()).all()

    # Bu ayki toplam gideri döviz kurlarını TL'ye çevirerek hesapla
    bu_ay = datetime.now()
    bu_ay_toplam = sum(
        (g.tutar * g.kur_degeri) for g in gider_listesi
        if g.tarih and g.tarih.month == bu_ay.month and g.tarih.year == bu_ay.year
    )

    kasalar = BankaKasa.query.all()

    return render_template(
        'giderler.html',
        giderler=gider_listesi,
        bu_ay_toplam=round(bu_ay_toplam, 2),
        kurlar=GUNCEL_KURLAR,
        kasalar=kasalar
    )

@gider_bp.route('/gider_ekle', methods=['POST'])
def gider_ekle():
    if 'logged_in' not in session:
        return redirect(url_for('genel.index'))

    kategori = request.form.get('kategori')
    aciklama = request.form.get('aciklama')
    birim = request.form.get('birim') or 'TL'

    tutar_raw = request.form.get('tutar')
    try:
        tutar = float(tutar_raw or 0)
    except ValueError:
        tutar = 0

    # Basit güvenlik: 0 veya negatif gider kaydı eklemeyelim (yanlışlıkla boş gönderim çok oluyor)
    if tutar <= 0:
        flash('Gider tutarı 0 olamaz. Lütfen tutar girin.', 'warning')
        return redirect(request.referrer or url_for('genel.index'))

    islem_kuru = GUNCEL_KURLAR.get(birim, 1.0) if birim != 'TL' else 1.0

    banka_kasa_id_raw = request.form.get('banka_kasa_id')
    try:
        banka_kasa_id = int(banka_kasa_id_raw) if banka_kasa_id_raw else None
    except ValueError:
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
