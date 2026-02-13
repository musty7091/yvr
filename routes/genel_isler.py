from flask import Blueprint, render_template, request, redirect, url_for, session
from sqlalchemy import extract
from models import db, IsKaydi, SatinAlma, Gider, Ayarlar
from utils import GUNCEL_KURLAR, kurlari_sabitle

genel_bp = Blueprint('genel', __name__)

@genel_bp.route('/')
def index():
    if 'logged_in' not in session: 
        return render_template('giris.html')
    
    from datetime import datetime
    bugun = datetime.now()
    bu_ay, bu_yil = bugun.month, bugun.year

    # Türkçe Ay İsimleri
    aylar_tr = {1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan", 5: "Mayıs", 6: "Haziran", 
                7: "Temmuz", 8: "Ağustos", 9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık"}
    guncel_ay = aylar_tr[bu_ay]    

    # Hesaplamalar
    aylik_is_hacmi = sum((i.toplam_bedel * GUNCEL_KURLAR.get(i.para_birimi, 1.0)) for i in IsKaydi.query.filter(extract('month', IsKaydi.kayit_tarihi) == bu_ay, extract('year', IsKaydi.kayit_tarihi) == bu_yil).all())
    aylik_satinalma = sum((s.tutar * GUNCEL_KURLAR.get(s.para_birimi, 1.0)) for s in SatinAlma.query.filter(extract('month', SatinAlma.tarih) == bu_ay, extract('year', SatinAlma.tarih) == bu_yil).all())
    aylik_gider = sum((g.tutar * g.kur_degeri) for g in Gider.query.filter(extract('month', Gider.tarih) == bu_ay, extract('year', Gider.tarih) == bu_yil).all())
    
    # Kırmızı Alarm Listesi
    alarm_listesi = IsKaydi.query.filter(IsKaydi.durum == 'Devam Ediyor').all()

    # Veritabanından Hedefi Oku (Eğer kayıt yoksa varsayılan oluştur)
    ayar = Ayarlar.query.first()
    if not ayar:
        ayar = Ayarlar(ay_hedefi=50000.0)
        db.session.add(ayar)
        db.session.commit()
    
    aylik_hedef = ayar.ay_hedefi
    hedef_yuzde = min((aylik_is_hacmi / aylik_hedef) * 100, 100) if aylik_hedef > 0 else 0

    return render_template('index.html', 
                           ay_adi=guncel_ay, 
                           is_hacmi=round(aylik_is_hacmi, 2), 
                           ticari_alim=round(aylik_satinalma, 2), 
                           giderler=round(aylik_gider, 2), 
                           kar=round(aylik_is_hacmi - (aylik_satinalma + aylik_gider), 2), 
                           alarm_listesi=alarm_listesi,
                           hedef_yuzde=round(hedef_yuzde, 0),
                           aylik_hedef=aylik_hedef,
                           kurlar=GUNCEL_KURLAR)

@genel_bp.route('/hedef_guncelle', methods=['POST'])
def hedef_guncelle():
    if 'logged_in' not in session: return redirect(url_for('genel.index'))
    yeni_hedef = float(request.form.get('yeni_hedef') or 0)
    ayar = Ayarlar.query.first()
    if ayar:
        ayar.ay_hedefi = yeni_hedef
        db.session.commit()
    return redirect(url_for('genel.index'))

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