from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from sqlalchemy import extract
from models import db, IsKaydi, SatinAlma, Gider, Ayarlar, BankaKasa, Transfer, Kullanici
from utils import GUNCEL_KURLAR, kurlari_sabitle
from datetime import datetime

genel_bp = Blueprint('genel', __name__)

@genel_bp.route('/')
def index():
    # Oturum kontrolü
    if 'logged_in' not in session: 
        return render_template('giris.html')
    
    bugun = datetime.now()
    bu_ay, bu_yil = bugun.month, bugun.year

    # Türkçe Ay İsimleri
    aylar_tr = {1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan", 5: "Mayıs", 6: "Haziran", 
                7: "Temmuz", 8: "Ağustos", 9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık"}
    guncel_ay = aylar_tr[bu_ay]    

    # 1. Aylık İş Hacmi (Ciro) Hesaplama
    aylik_is_hacmi = sum((i.toplam_bedel * GUNCEL_KURLAR.get(i.para_birimi, 1.0)) 
                         for i in IsKaydi.query.filter(extract('month', IsKaydi.kayit_tarihi) == bu_ay, 
                                                       extract('year', IsKaydi.kayit_tarihi) == bu_yil).all())
    
    # 2. Aylık Ticari Alımlar (Hammadde Borçları) Hesaplama
    aylik_satinalma = sum((s.tutar * GUNCEL_KURLAR.get(s.para_birimi, 1.0)) 
                          for s in SatinAlma.query.filter(extract('month', SatinAlma.tarih) == bu_ay, 
                                                          extract('year', SatinAlma.tarih) == bu_yil).all())
    
    # 3. Aylık İşletme Giderleri Hesaplama
    aylik_gider = sum((g.tutar * g.kur_degeri) 
                      for g in Gider.query.filter(extract('month', Gider.tarih) == bu_ay, 
                                                  extract('year', Gider.tarih) == bu_yil).all())
    
    # 4. Kırmızı Alarm Listesi
    alarm_listesi = IsKaydi.query.filter(IsKaydi.durum == 'Devam Ediyor').all()

    # 5. Hedef Kontrolü
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

@genel_bp.route('/ayarlar', methods=['GET', 'POST'])
def ayarlar():
    if 'logged_in' not in session: 
        return redirect(url_for('genel.index'))
    
    # Şu anki kullanıcıyı al (Örnekte tek admin olduğu için direkt çekiyoruz)
    kullanici = Kullanici.query.filter_by(kullanici_adi='admin').first()
    ayar = Ayarlar.query.first()

    if request.method == 'POST':
        islem = request.form.get('islem')

        # 1. Şifre Güncelleme İşlemi
        if islem == 'sifre_degistir':
            mevcut_sifre = request.form.get('mevcut_sifre')
            yeni_sifre = request.form.get('yeni_sifre')

            if kullanici.sifre_kontrol(mevcut_sifre):
                kullanici.sifre_belirle(yeni_sifre)
                db.session.commit()
                flash('Şifreniz başarıyla güncellendi.', 'success')
            else:
                flash('Mevcut şifreniz hatalı!', 'danger')
        
        # 2. Genel Hedef Güncelleme İşlemi
        elif islem == 'hedef_guncelle':
            yeni_hedef = float(request.form.get('yeni_hedef') or 0)
            if ayar:
                ayar.ay_hedefi = yeni_hedef
                db.session.commit()
                flash('Aylık hedef başarıyla güncellendi.', 'success')

        return redirect(url_for('genel.ayarlar'))

    return render_template('ayarlar.html', kullanici=kullanici, ayar=ayar)

@genel_bp.route('/kasa_banka_yonetimi')
def kasa_banka_yonetimi():
    if 'logged_in' not in session: 
        return redirect(url_for('genel.index'))
    
    kasalar = BankaKasa.query.all()
    kasa_ozetleri = []

    for k in kasalar:
        # Gelirler: Müşteri Tahsilatları
        toplam_gelir = sum(o.tutar for o in k.musteri_odemeleri)
        
        # Giderler: İşletme Giderleri + Tedarikçi Ödemeleri
        toplam_gider = sum(g.tutar for g in k.isletme_giderleri)
        toplam_tedarikci = sum(t.tutar for t in k.tedarikci_odemeleri)
        
        # Transferler: Gelen (+) ve Giden (-)
        gelen_transfer = sum(tr.tutar for tr in Transfer.query.filter_by(hedef_hesap_id=k.id).all())
        giden_transfer = sum(tr.tutar for tr in Transfer.query.filter_by(kaynak_hesap_id=k.id).all())
        
        # NET BAKİYE HESAPLAMA
        bakiye = (toplam_gelir + gelen_transfer) - (toplam_gider + toplam_tedarikci + giden_transfer)
        
        kasa_ozetleri.append({
            'id': k.id,
            'ad': k.ad,
            'tur': k.tur,
            'hesap_no': k.hesap_no,
            'bakiye': round(bakiye, 2)
        })

    return render_template('kasa_yonetimi.html', kasalar=kasa_ozetleri)

@genel_bp.route('/transfer_yap', methods=['POST'])
def transfer_yap():
    if 'logged_in' not in session: 
        return redirect(url_for('genel.index'))
    
    tutar = float(request.form.get('tutar') or 0)
    kaynak_id = int(request.form.get('kaynak_hesap_id'))
    hedef_id = int(request.form.get('hedef_hesap_id'))
    
    if kaynak_id == hedef_id:
        return redirect(url_for('genel.kasa_banka_yonetimi'))

    yeni_transfer = Transfer(
        tutar=tutar,
        kaynak_hesap_id=kaynak_id,
        hedef_hesap_id=hedef_id,
        aciklama=request.form.get('aciklama')
    )
    db.session.add(yeni_transfer)
    db.session.commit()
    return redirect(url_for('genel.kasa_banka_yonetimi'))

@genel_bp.route('/kasa_banka_ekle', methods=['POST'])
def kasa_banka_ekle():
    if 'logged_in' not in session: 
        return redirect(url_for('genel.index'))
    
    yeni_kasa = BankaKasa(
        ad=request.form.get('ad'), 
        tur=request.form.get('tur'), 
        hesap_no=request.form.get('hesap_no')
    )
    db.session.add(yeni_kasa)
    db.session.commit()
    return redirect(url_for('genel.kasa_banka_yonetimi'))

@genel_bp.route('/kasa_banka_sil/<int:id>')
def kasa_banka_sil(id):
    if 'logged_in' not in session: 
        return redirect(url_for('genel.index'))
    
    kasa = BankaKasa.query.get_or_404(id)
    db.session.delete(kasa)
    db.session.commit()
    return redirect(url_for('genel.kasa_banka_yonetimi'))

@genel_bp.route('/hedef_guncelle', methods=['POST'])
def hedef_guncelle():
    if 'logged_in' not in session: 
        return redirect(url_for('genel.index'))
    
    ayar = Ayarlar.query.first()
    if ayar:
        ayar.ay_hedefi = float(request.form.get('yeni_hedef') or 0)
        db.session.commit()
    return redirect(url_for('genel.index'))

@genel_bp.route('/login', methods=['POST'])
def login():
    k_adi = request.form.get('username')
    sifre = request.form.get('password')
    
    # Veritabanında kullanıcıyı sorgula
    kullanici = Kullanici.query.filter_by(kullanici_adi=k_adi).first()
    
    # Kullanıcı varsa ve şifre hash kontrolü doğruysa
    if kullanici and kullanici.sifre_kontrol(sifre):
        session.permanent = True
        session['logged_in'] = True
        return redirect(url_for('genel.index'))
    else:
        # Hatalı girişte kullanıcıya mesaj göster
        flash('Geçersiz kullanıcı adı veya şifre!', 'danger')
        return redirect(url_for('genel.index'))

@genel_bp.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('genel.index'))

@genel_bp.route('/kurlari_guncelle')
def kurlari_guncelle():
    if 'logged_in' not in session: 
        return redirect(url_for('genel.index'))
    
    kurlari_sabitle()
    return redirect(request.referrer or url_for('genel.index'))