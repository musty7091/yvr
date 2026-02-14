from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from sqlalchemy import extract, func
from models import db, IsKaydi, SatinAlma, Gider, Ayarlar, BankaKasa, Transfer, Kullanici, Odeme, TedarikciOdeme, Musteri
from utils import GUNCEL_KURLAR, kurlari_sabitle
from datetime import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import os

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

    # N+1 Problemi Çözümü: Toplu hesaplamalar Python döngüsü yerine SQL SUM ile yapılıyor
    # 1. Aylık İş Hacmi (Ciro) Hesaplama
    aylik_is_hacmi = sum((i.toplam_bedel * GUNCEL_KURLAR.get(i.para_birimi, 1.0)) 
                         for i in IsKaydi.query.filter(extract('month', IsKaydi.kayit_tarihi) == bu_ay, 
                                                       extract('year', IsKaydi.kayit_tarihi) == bu_yil).all())
    
    # 2. Aylık Ticari Alımlar Hesaplama
    aylik_satinalma = sum((s.tutar * GUNCEL_KURLAR.get(s.para_birimi, 1.0)) 
                          for s in SatinAlma.query.filter(extract('month', SatinAlma.tarih) == bu_ay, 
                                                          extract('year', SatinAlma.tarih) == bu_yil).all())
    
    # 3. Aylık İşletme Giderleri Hesaplama (SQL üzerinde SUM ile daha hızlı)
    aylik_gider_sorgu = db.session.query(func.sum(Gider.tutar * Gider.kur_degeri)).filter(
        extract('month', Gider.tarih) == bu_ay,
        extract('year', Gider.tarih) == bu_yil
    ).scalar() or 0.0
    
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

    musteriler = Musteri.query.all()
    kasalar = BankaKasa.query.all()

    return render_template('index.html', 
                           ay_adi=guncel_ay, 
                           is_hacmi=round(aylik_is_hacmi, 2), 
                           ticari_alim=round(aylik_satinalma, 2), 
                           giderler=round(aylik_gider_sorgu, 2), 
                           kar=round(aylik_is_hacmi - (aylik_satinalma + aylik_gider_sorgu), 2), 
                           alarm_listesi=alarm_listesi,
                           hedef_yuzde=round(hedef_yuzde, 0),
                           aylik_hedef=aylik_hedef,
                           kurlar=GUNCEL_KURLAR,
                           musteriler=musteriler,
                           kasalar=kasalar)

@genel_bp.route('/ayarlar', methods=['GET', 'POST'])
def ayarlar():
    if 'logged_in' not in session: 
        return redirect(url_for('genel.index'))
    
    kullanici = Kullanici.query.filter_by(kullanici_adi='admin').first()
    ayar = Ayarlar.query.first()
    kasalar = BankaKasa.query.all() 

    if request.method == 'POST':
        islem = request.form.get('islem')

        if islem == 'sifre_degistir':
            mevcut_sifre = request.form.get('mevcut_sifre')
            yeni_sifre = request.form.get('yeni_sifre')

            if kullanici.sifre_kontrol(mevcut_sifre):
                kullanici.sifre_belirle(yeni_sifre)
                db.session.commit()
                flash('Şifreniz başarıyla güncellendi.', 'success')
            else:
                flash('Mevcut şifreniz hatalı!', 'danger')
        
        elif islem == 'hedef_guncelle':
            yeni_hedef = float(request.form.get('yeni_hedef') or 0)
            if ayar:
                ayar.ay_hedefi = yeni_hedef
                db.session.commit()
                flash('Aylık hedef başarıyla güncellendi.', 'success')

        # YENİ: Başlangıç bakiyesi güncelleme mantığı
        elif islem == 'kasa_baslangic_guncelle':
            kasa_id = request.form.get('kasa_id')
            yeni_baslangic = float(request.form.get('baslangic_tutar') or 0)
            kasa = BankaKasa.query.get(kasa_id)
            if kasa:
                kasa.baslangic_bakiye = yeni_baslangic
                db.session.commit()
                flash(f'{kasa.ad} başlangıç bakiyesi güncellendi.', 'success')

        return redirect(url_for('genel.ayarlar'))

    return render_template('ayarlar.html', kullanici=kullanici, ayar=ayar, kasalar=kasalar)

@genel_bp.route('/kasa_banka_yonetimi')
def kasa_banka_yonetimi():
    if 'logged_in' not in session: 
        return redirect(url_for('genel.index'))
    
    db.session.expire_all()
    
    kasalar = BankaKasa.query.all()
    kasa_ozetleri = []

    # N+1 Problemi Çözümü: Toplu bakiye hesaplamaları SQL query ile yapılıyor
    for k in kasalar:
        # Gelirler: Müşteri Tahsilatları
        toplam_gelir = db.session.query(
            func.coalesce(func.sum(Odeme.tutar * func.coalesce(Odeme.kur_degeri, 1.0)), 0.0)
        ).filter(Odeme.banka_kasa_id == k.id).scalar()
        
        # İşletme Giderleri
        toplam_gider = db.session.query(
            func.coalesce(func.sum(Gider.tutar * Gider.kur_degeri), 0.0)
        ).filter(Gider.banka_kasa_id == k.id).scalar()

        # Tedarikçi Ödemeleri
        toplam_tedarikci = db.session.query(
            func.coalesce(func.sum(TedarikciOdeme.tutar * TedarikciOdeme.kur_degeri), 0.0)
        ).filter(TedarikciOdeme.banka_kasa_id == k.id).scalar()
        
        # Transferler
        gelen_transfer = db.session.query(func.coalesce(func.sum(Transfer.tutar), 0.0)).filter_by(hedef_hesap_id=k.id).scalar()
        giden_transfer = db.session.query(func.coalesce(func.sum(Transfer.tutar), 0.0)).filter_by(kaynak_hesap_id=k.id).scalar()
        
        # NET BAKİYE HESAPLAMA (Başlangıç Bakiyesi + Girişler - Çıkışlar)
        bakiye = (k.baslangic_bakiye + toplam_gelir + gelen_transfer) - (toplam_gider + toplam_tedarikci + giden_transfer)
        
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

@genel_bp.route('/kasa_banka_sil/<int:id>', methods=['POST'])
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
    
    kullanici = Kullanici.query.filter_by(kullanici_adi=k_adi).first()
    
    if kullanici and kullanici.sifre_kontrol(sifre):
        session.permanent = True
        session['logged_in'] = True
        return redirect(url_for('genel.index'))
    else:
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

@genel_bp.route('/yedekle_ve_mail_at')
def yedekle_ve_mail_at():
    if 'logged_in' not in session: 
        return redirect(url_for('genel.index'))

    basedir = os.path.abspath(os.path.dirname(__file__))
    db_path = os.path.join(os.path.dirname(basedir), 'instance', 'yvr_veritabani.db')
    
    mail_server = os.getenv('MAIL_SERVER')
    mail_port = os.getenv('MAIL_PORT', '587')
    mail_user = os.getenv('MAIL_USERNAME')
    mail_pass = os.getenv('MAIL_PASSWORD')
    
    if not all([mail_server, mail_user, mail_pass]):
        flash('E-posta yapılandırma bilgileri eksik. Lütfen .env dosyasını kontrol edin.', 'danger')
        return redirect(url_for('genel.ayarlar'))
    
    try:
        mesaj = MIMEMultipart()
        mesaj['From'] = mail_user
        mesaj['To'] = mail_user
        mesaj['Subject'] = f"YVR Sistem Yedek - {datetime.now().strftime('%d.%m.%Y')}"
        
        with open(db_path, "rb") as attachment:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f"attachment; filename=yvr_yedek_{datetime.now().strftime('%Y%m%d')}.db")
            mesaj.attach(part)
        
        server = smtplib.SMTP(mail_server, int(mail_port))
        server.starttls()
        server.login(mail_user, mail_pass)
        server.send_message(mesaj)
        server.quit()
        
        flash('Yedekleme başarılı! Dosya e-posta adresinize gönderildi.', 'success')
    except Exception as e:
        flash(f'Yedekleme sırasında bir hata oluştu: {str(e)}', 'danger')
        
    return redirect(url_for('genel.ayarlar'))
