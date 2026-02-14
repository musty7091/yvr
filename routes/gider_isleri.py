from flask import Blueprint, render_template, request, redirect, url_for, session
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
    bu_ay_toplam = sum(g.tutar * g.kur_degeri for g in gider_listesi 
                       if g.tarih.month == bu_ay.month and g.tarih.year == bu_ay.year)
    
    # HATA DÜZELTİLDİ: Modelde 'durum' sütunu olmadığı için filtre kaldırıldı.
    kasalar = BankaKasa.query.all()
    
    return render_template('giderler.html', 
                           giderler=gider_listesi, 
                           bu_ay_toplam=round(bu_ay_toplam, 2), 
                           kurlar=GUNCEL_KURLAR,
                           kasalar=kasalar)

@gider_bp.route('/gider_ekle', methods=['POST'])
def gider_ekle():
    if 'logged_in' not in session: 
        return redirect(url_for('genel.index'))
    
    birim = request.form.get('birim')
    islem_kuru = GUNCEL_KURLAR.get(birim, 1.0) if birim != 'TL' else 1.0
    
    # Paranın eksilmesini sağlayan gider kaydı
    yeni_gider = Gider(
        kategori=request.form.get('kategori'),
        baslik=request.form.get('aciklama'), # Modelindeki sütun adı 'baslik'
        tutar=float(request.form.get('tutar') or 0),
        para_birimi=birim, # Modelindeki sütun adı 'para_birimi'
        kur_degeri=islem_kuru,
        banka_kasa_id=request.form.get('banka_kasa_id'),
        tarih=datetime.now()
    )
    
    db.session.add(yeni_gider)
    db.session.commit()
    return redirect(url_for('gider.giderler'))

@gider_bp.route('/gider_sil/<int:id>', methods=['POST'])
def gider_sil(id):
    if 'logged_in' not in session: 
        return redirect(url_for('genel.index'))
    
    gider = Gider.query.get_or_404(id)
    db.session.delete(gider)
    db.session.commit()
    return redirect(url_for('gider.giderler'))