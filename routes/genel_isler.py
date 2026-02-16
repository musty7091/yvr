from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from sqlalchemy import extract, func
from models import (
    db, IsKaydi, SatinAlma, Gider, Ayarlar, BankaKasa, Transfer,
    Kullanici, Odeme, TedarikciOdeme, Musteri,
    money, rate, normalize_currency
)
from utils import GUNCEL_KURLAR, kurlari_sabitle
from datetime import datetime
from decimal import Decimal
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import os

genel_bp = Blueprint('genel', __name__)

@genel_bp.route('/')
def index():
    if 'logged_in' not in session:
        return render_template('giris.html')

    bugun = datetime.now()
    bu_ay, bu_yil = bugun.month, bugun.year

    aylar_tr = {
        1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan", 5: "Mayıs", 6: "Haziran",
        7: "Temmuz", 8: "Ağustos", 9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık"
    }
    guncel_ay = aylar_tr[bu_ay]

    # 1) Aylık İş Hacmi (Ciro) - Decimal
    aylik_is_hacmi = Decimal("0")
    isler = IsKaydi.query.filter(
        extract('month', IsKaydi.kayit_tarihi) == bu_ay,
        extract('year', IsKaydi.kayit_tarihi) == bu_yil
    ).all()

    for i in isler:
        pb = normalize_currency(i.para_birimi)
        kur = rate(GUNCEL_KURLAR.get(pb, 1))
        aylik_is_hacmi += (i.toplam_bedel * kur)

    # 2) Aylık Ticari Alımlar - Decimal
    aylik_satinalma = Decimal("0")
    satin_almalar = SatinAlma.query.filter(
        extract('month', SatinAlma.tarih) == bu_ay,
        extract('year', SatinAlma.tarih) == bu_yil
    ).all()

    for s in satin_almalar:
        pb = normalize_currency(s.para_birimi)
        kur = rate(GUNCEL_KURLAR.get(pb, 1))
        aylik_satinalma += (s.tutar * kur)

    # 3) Aylık İşletme Giderleri - SQL SUM dönüşü Numeric/Decimal olabilir; money() ile normalize ediyoruz
    aylik_gider_sorgu = db.session.query(
        func.coalesce(func.sum(Gider.tutar * Gider.kur_degeri), Decimal("0"))
    ).filter(
        extract('month', Gider.tarih) == bu_ay,
        extract('year', Gider.tarih) == bu_yil
    ).scalar()

    aylik_gider_sorgu = money(aylik_gider_sorgu)

    # 4) Alarm
    alarm_listesi = IsKaydi.query.filter(IsKaydi.durum == 'Devam Ediyor').all()

    # 5) Hedef
    ayar = Ayarlar.query.first()
    if not ayar:
        ayar = Ayarlar(ay_hedefi=money("50000"))
        db.session.add(ayar)
        db.session.commit()

    aylik_hedef = money(ayar.ay_hedefi)

    if aylik_hedef > 0:
        hedef_yuzde = min((aylik_is_hacmi / aylik_hedef) * Decimal("100"), Decimal("100"))
    else:
        hedef_yuzde = Decimal("0")

    # Kâr
    kar = aylik_is_hacmi - (aylik_satinalma + aylik_gider_sorgu)

    musteriler = Musteri.query.all()
    kasalar = BankaKasa.query.all()

    return render_template(
        'index.html',
        ay_adi=guncel_ay,
        is_hacmi=float(money(aylik_is_hacmi)),
        ticari_alim=float(money(aylik_satinalma)),
        giderler=float(money(aylik_gider_sorgu)),
        kar=float(money(kar)),
        alarm_listesi=alarm_listesi,
        hedef_yuzde=float(hedef_yuzde),
        aylik_hedef=float(aylik_hedef),
        kurlar=GUNCEL_KURLAR,
        musteriler=musteriler,
        kasalar=kasalar
    )

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

            if kullanici and kullanici.sifre_kontrol(mevcut_sifre):
                kullanici.sifre_belirle(yeni_sifre)
                db.session.commit()
                flash('Şifreniz başarıyla güncellendi.', 'success')
            else:
                flash('Mevcut şifreniz hatalı!', 'danger')

        elif islem == 'hedef_guncelle':
            yeni_hedef = money(request.form.get('yeni_hedef'))
            if ayar:
                ayar.ay_hedefi = yeni_hedef
                db.session.commit()
                flash('Aylık hedef başarıyla güncellendi.', 'success')

        elif islem == 'kasa_baslangic_guncelle':
            kasa_id = request.form.get('kasa_id')
            yeni_baslangic = money(request.form.get('baslangic_tutar'))
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

    for k in kasalar:
        toplam_gelir = db.session.query(
            func.coalesce(func.sum(Odeme.tutar * func.coalesce(Odeme.kur_degeri, Decimal("1"))), Decimal("0"))
        ).filter(Odeme.banka_kasa_id == k.id).scalar()
        toplam_gelir = money(toplam_gelir)

        toplam_gider = db.session.query(
            func.coalesce(func.sum(Gider.tutar * Gider.kur_degeri), Decimal("0"))
        ).filter(Gider.banka_kasa_id == k.id).scalar()
        toplam_gider = money(toplam_gider)

        toplam_tedarikci = db.session.query(
            func.coalesce(func.sum(TedarikciOdeme.tutar * TedarikciOdeme.kur_degeri), Decimal("0"))
        ).filter(TedarikciOdeme.banka_kasa_id == k.id).scalar()
        toplam_tedarikci = money(toplam_tedarikci)

        gelen_transfer = db.session.query(
            func.coalesce(func.sum(Transfer.tutar), Decimal("0"))
        ).filter_by(hedef_hesap_id=k.id).scalar()
        gelen_transfer = money(gelen_transfer)

        giden_transfer = db.session.query(
            func.coalesce(func.sum(Transfer.tutar), Decimal("0"))
        ).filter_by(kaynak_hesap_id=k.id).scalar()
        giden_transfer = money(giden_transfer)

        baslangic = money(k.baslangic_bakiye)

        bakiye = (baslangic + toplam_gelir + gelen_transfer) - (toplam_gider + toplam_tedarikci + giden_transfer)

        kasa_ozetleri.append({
            'id': k.id,
            'ad': k.ad,
            'tur': k.tur,
            'hesap_no': k.hesap_no,
            'bakiye': float(money(bakiye))
        })

    return render_template('kasa_yonetimi.html', kasalar=kasa_ozetleri)

@genel_bp.route('/transfer_yap', methods=['POST'])
def transfer_yap():
    if 'logged_in' not in session:
        return redirect(url_for('genel.index'))

    tutar = money(request.form.get('tutar'))

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
    flash('Transfer kaydedildi.', 'success')
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
    flash('Kasa/Banka eklendi.', 'success')
    return redirect(url_for('genel.kasa_banka_yonetimi'))

@genel_bp.route('/kasa_banka_sil/<int:id>', methods=['POST'])
def kasa_banka_sil(id):
    if 'logged_in' not in session:
        return redirect(url_for('genel.index'))

    kasa = BankaKasa.query.get_or_404(id)
    db.session.delete(kasa)
    db.session.commit()
    flash('Kasa/Banka silindi.', 'warning')
    return redirect(url_for('genel.kasa_banka_yonetimi'))

@genel_bp.route('/hedef_guncelle', methods=['POST'])
def hedef_guncelle():
    if 'logged_in' not in session:
        return redirect(url_for('genel.index'))

    ayar = Ayarlar.query.first()
    if ayar:
        ayar.ay_hedefi = money(request.form.get('yeni_hedef'))
        db.session.commit()
        flash('Hedef güncellendi.', 'success')
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
    flash('Kurlar güncellendi.', 'success')
    return redirect(request.referrer or url_for('genel.index'))

@genel_bp.route('/yedekle_ve_mail_at')
def yedekle_ve_mail_at():
    if 'logged_in' not in session:
        return redirect(url_for('genel.index'))

    # SQLite dosyası yedekleme mantığı Postgres'te geçerli değil.
    # Postgres kullanırken güvenli yöntem pg_dump ile dump almaktır.
    # Bu route yanlış bir güven duygusu yaratmasın diye uyarıyoruz.
    db_uri = (os.getenv("DATABASE_URL") or "").lower()
    if "postgres" in db_uri:
        flash('PostgreSQL kullanıyorsun. Yedekleme için pg_dump ile dump alınmalı (bu ekrandaki SQLite yedeği geçerli değil).', 'warning')
        return redirect(url_for('genel.ayarlar'))

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
            part.add_header(
                "Content-Disposition",
                f"attachment; filename=yvr_yedek_{datetime.now().strftime('%Y%m%d')}.db"
            )
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
