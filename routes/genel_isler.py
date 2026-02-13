from flask import Blueprint, render_template, request, redirect, url_for, session
from sqlalchemy import extract
from models import IsKaydi, SatinAlma, Gider
from utils import GUNCEL_KURLAR, kurlari_sabitle

genel_bp = Blueprint('genel', __name__)

@genel_bp.route('/')
def index():
    if 'logged_in' not in session: 
        return render_template('giris.html')
    
    from datetime import datetime
    bugun = datetime.now()
    bu_ay, bu_yil = bugun.month, bugun.year

    # Ay isimlerini Türkçe eşleştiriyoruz
    aylar_tr = {
        1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan",
        5: "Mayıs", 6: "Haziran", 7: "Temmuz", 8: "Ağustos",
        9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık"
    }
    guncel_ay = aylar_tr[bu_ay]    

    # Aylık İş Hacmi Hesaplama
    aylik_is_hacmi = sum((i.toplam_bedel * GUNCEL_KURLAR.get(i.para_birimi, 1.0)) for i in IsKaydi.query.filter(extract('month', IsKaydi.kayit_tarihi) == bu_ay, extract('year', IsKaydi.kayit_tarihi) == bu_yil).all())
    
    # Aylık Satın Alma (Hammadde) Hesaplama
    aylik_satinalma = sum((s.tutar * GUNCEL_KURLAR.get(s.para_birimi, 1.0)) for s in SatinAlma.query.filter(extract('month', SatinAlma.tarih) == bu_ay, extract('year', SatinAlma.tarih) == bu_yil).all())
    
    # Aylık İşletme Giderleri Hesaplama
    aylik_gider = sum((g.tutar * g.kur_degeri) for g in Gider.query.filter(extract('month', Gider.tarih) == bu_ay, extract('year', Gider.tarih) == bu_yil).all())
    
    # Kâr Hesaplama
    hesaplanan_kar = aylik_is_hacmi - (aylik_satinalma + aylik_gider)

    return render_template('index.html', 
                           ay_adi=guncel_ay, 
                           is_hacmi=round(aylik_is_hacmi, 2), 
                           ticari_alim=round(aylik_satinalma, 2), 
                           giderler=round(aylik_gider, 2), 
                           kar=round(hesaplanan_kar, 2), 
                           kurlar=GUNCEL_KURLAR)

@genel_bp.route('/login', methods=['POST'])
def login():
    if request.form.get('username') == 'admin' and request.form.get('password') == '1234':
        session.permanent = True
        session['logged_in'] = True
    return redirect(url_for('genel.index'))

@genel_bp.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('genel.index'))

@genel_bp.route('/kurlari_guncelle')
def kurlari_guncelle():
    kurlari_sabitle()
    return redirect(request.referrer or url_for('genel.index'))