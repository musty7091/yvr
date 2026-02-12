import requests
import xml.etree.ElementTree as ET
from flask import Flask, render_template, request, redirect, url_for, session, make_response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_, extract, func
from datetime import datetime, timedelta
import pdfkit
import os
import platform
from urllib.parse import quote

app = Flask(__name__)
app.secret_key = 'yvr_ozel_sifre_123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///yvr_veritabani.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# GÜVENLİK: 30 Dakika işlem yapılmazsa oturum kapanır
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

db = SQLAlchemy(app)

# --- GLOBAL HAFIZA (Günün Sabit Kurları) ---
GUNCEL_KURLAR = {"USD": 34.0, "EUR": 36.5, "GBP": 42.0, "tarih": "Henüz Güncellenmedi"}

# ==========================================
# 1. BÖLÜM: VERİTABANI MODELLERİ
# ==========================================

# --- MEVCUT MODÜLLER (SATIŞ & MÜŞTERİ) ---
class Musteri(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ad_soyad = db.Column(db.String(100), nullable=False)
    telefon = db.Column(db.String(20))
    isyeri_adi = db.Column(db.String(200)) 
    isyeri_adresi = db.Column(db.Text)
    durum = db.Column(db.String(20), default='Aktif') 
    isler = db.relationship('IsKaydi', backref='sahibi', lazy=True)
    odemeler = db.relationship('Odeme', backref='musteri', lazy=True)

class IsKaydi(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    is_tanimi = db.Column(db.String(200), nullable=False)
    toplam_bedel = db.Column(db.Float, nullable=False, default=0.0)
    para_birimi = db.Column(db.String(5), default='TL')
    teslim_tarihi = db.Column(db.String(20))
    durum = db.Column(db.String(20), default='Devam Ediyor')
    kayit_tarihi = db.Column(db.DateTime, default=datetime.now)
    musteri_id = db.Column(db.Integer, db.ForeignKey('musteri.id'), nullable=False)

class Odeme(db.Model): # Müşteriden gelen para (GELİR)
    id = db.Column(db.Integer, primary_key=True)
    tutar = db.Column(db.Float, nullable=False)
    birim = db.Column(db.String(5), default='TL')
    aciklama = db.Column(db.String(200))
    kur_degeri = db.Column(db.Float, default=1.0)
    odeme_tarihi = db.Column(db.DateTime, default=datetime.now)
    musteri_id = db.Column(db.Integer, db.ForeignKey('musteri.id'), nullable=False)

# --- YENİ MODÜLLER (TİCARİ BORÇLAR & GİDERLER) ---
class Tedarikci(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    firma_adi = db.Column(db.String(150), nullable=False)
    yetkili_kisi = db.Column(db.String(100))
    telefon = db.Column(db.String(20))
    adres = db.Column(db.Text)
    durum = db.Column(db.String(20), default='Aktif')
    satin_almalar = db.relationship('SatinAlma', backref='tedarikci', lazy=True)
    odenenler = db.relationship('TedarikciOdeme', backref='tedarikci', lazy=True)

class SatinAlma(db.Model): # Hammadde alımı (BORÇLANMA)
    id = db.Column(db.Integer, primary_key=True)
    malzeme_tanimi = db.Column(db.String(200), nullable=False)
    tutar = db.Column(db.Float, nullable=False)
    para_birimi = db.Column(db.String(5), default='TL')
    fatura_no = db.Column(db.String(50))
    tarih = db.Column(db.DateTime, default=datetime.now)
    tedarikci_id = db.Column(db.Integer, db.ForeignKey('tedarikci.id'), nullable=False)

class TedarikciOdeme(db.Model): # Tedarikçiye ödenen para (NAKİT ÇIKIŞI)
    id = db.Column(db.Integer, primary_key=True)
    tutar = db.Column(db.Float, nullable=False)
    birim = db.Column(db.String(5), default='TL')
    aciklama = db.Column(db.String(200))
    kur_degeri = db.Column(db.Float, default=1.0)
    odeme_tarihi = db.Column(db.DateTime, default=datetime.now)
    tedarikci_id = db.Column(db.Integer, db.ForeignKey('tedarikci.id'), nullable=False)

class Gider(db.Model): # İşletme Giderleri (Kira, Personel, Elektrik)
    id = db.Column(db.Integer, primary_key=True)
    kategori = db.Column(db.String(50)) # Örn: Kira, Maaş, Yemek
    aciklama = db.Column(db.String(200))
    tutar = db.Column(db.Float, nullable=False)
    birim = db.Column(db.String(5), default='TL')
    kur_degeri = db.Column(db.Float, default=1.0)
    tarih = db.Column(db.DateTime, default=datetime.now)

# --- KUR SABİTLEME ---
def kurlari_sabitle():
    global GUNCEL_KURLAR
    try:
        response = requests.get("https://www.tcmb.gov.tr/kurlar/today.xml", timeout=5)
        tree = ET.fromstring(response.content)
        usd = float(tree.find(".//Currency[@Kod='USD']/BanknoteSelling").text)
        eur = float(tree.find(".//Currency[@Kod='EUR']/BanknoteSelling").text)
        gbp = float(tree.find(".//Currency[@Kod='GBP']/BanknoteSelling").text)
        
        GUNCEL_KURLAR = {
            "USD": round(usd, 4),
            "EUR": round(eur, 4),
            "GBP": round(gbp, 4),
            "tarih": datetime.now().strftime("%d.%m.%Y %H:%M")
        }
        return True
    except:
        return False

# ==========================================
# 2. BÖLÜM: ROTALAR (SAYFALAR)
# ==========================================

# --- ANA DASHBOARD (GİRİŞ EKRANI) ---
@app.route('/')
def index():
    if 'logged_in' not in session:
        return render_template('giris.html')
    
    # BU AYIN VERİLERİNİ HESAPLA (Dashboard Özeti İçin)
    bugun = datetime.now()
    bu_ay = bugun.month
    bu_yil = bugun.year
    
    # 1. Alınan İş Hacmi (Ciro Potansiyeli)
    # Bu ay eklenen işlerin toplam bedeli
    aylik_is_hacmi = 0
    bu_ayki_isler = IsKaydi.query.filter(
        extract('month', IsKaydi.kayit_tarihi) == bu_ay,
        extract('year', IsKaydi.kayit_tarihi) == bu_yil
    ).all()
    for is_kaydi in bu_ayki_isler:
        kur = GUNCEL_KURLAR.get(is_kaydi.para_birimi, 1.0)
        aylik_is_hacmi += (is_kaydi.toplam_bedel * kur)

    # 2. Ticari Alımlar (Hammadde Maliyeti)
    aylik_satinalma = 0
    satinalmalar = SatinAlma.query.filter(
        extract('month', SatinAlma.tarih) == bu_ay,
        extract('year', SatinAlma.tarih) == bu_yil
    ).all()
    for s in satinalmalar:
        kur = GUNCEL_KURLAR.get(s.para_birimi, 1.0)
        aylik_satinalma += (s.tutar * kur)

    # 3. İşletme Giderleri (Sabit Giderler)
    aylik_gider = 0
    giderler = Gider.query.filter(
        extract('month', Gider.tarih) == bu_ay,
        extract('year', Gider.tarih) == bu_yil
    ).all()
    for g in giderler:
        aylik_gider += (g.tutar * g.kur_degeri)

    # 4. Tahmini Karlılık (Basit Hesap: İş Hacmi - Maliyetler)
    tahmini_kar = aylik_is_hacmi - (aylik_satinalma + aylik_gider)

    return render_template('index.html', 
                           ay_adi=bugun.strftime("%B"),
                           is_hacmi=round(aylik_is_hacmi, 2),
                           ticari_alim=round(aylik_satinalma, 2),
                           giderler=round(aylik_gider, 2),
                           kar=round(tahmini_kar, 2),
                           kurlar=GUNCEL_KURLAR)

# --- SATIŞLAR MODÜLÜ (Eski Ana Sayfa) ---
@app.route('/satislar')
def satislar():
    if 'logged_in' not in session: return redirect(url_for('index'))
    
    # Eski index fonksiyonundaki mantığın aynısı
    aktif_musteriler = Musteri.query.filter_by(durum='Aktif').all()
    toplam_alacak_tl = 0
    devam_eden_is_sayisi = 0
    
    for m in aktif_musteriler:
        for i in m.isler:
            if i.durum == 'Devam Ediyor':
                devam_eden_is_sayisi += 1
            kur = GUNCEL_KURLAR.get(i.para_birimi, 1.0)
            toplam_alacak_tl += (i.toplam_bedel * kur)
        for o in m.odemeler:
            kur = GUNCEL_KURLAR.get(o.birim, 1.0)
            toplam_alacak_tl -= (o.tutar * kur)

    tum_yaklasan = IsKaydi.query.filter(
        IsKaydi.teslim_tarihi != "", 
        IsKaydi.durum == 'Devam Ediyor'
    ).order_by(IsKaydi.teslim_tarihi.asc()).all()
    
    yaklasan_isler = [is_kaydi for is_kaydi in tum_yaklasan if is_kaydi.sahibi.durum == 'Aktif'][:5]
    
    # İstatistikler
    t_musteri = Musteri.query.count()
    a_musteri = len(aktif_musteriler)
    biten_is = IsKaydi.query.filter_by(durum='Teslim Edildi').count()
    
    # Bu ayki ciro (Nakit Girişi)
    simdi = datetime.now()
    tum_odemeler = Odeme.query.all()
    bu_ayki_ciro = 0
    for o in tum_odemeler:
        if o.odeme_tarihi.month == simdi.month and o.odeme_tarihi.year == simdi.year:
            kur = GUNCEL_KURLAR.get(o.birim, 1.0)
            bu_ayki_ciro += (o.tutar * kur)

    return render_template('satislar.html', 
                           alacak=round(toplam_alacak_tl, 2), 
                           is_sayisi=devam_eden_is_sayisi, 
                           yaklasan_isler=yaklasan_isler,
                           kurlar=GUNCEL_KURLAR,
                           t_musteri=t_musteri, 
                           a_musteri=a_musteri, 
                           biten_is=biten_is, 
                           ay_ciro=bu_ayki_ciro)

# --- YENİ EKLENECEK MODÜLLER İÇİN (Şimdilik Boş) ---
@app.route('/ticari_borclar')
def ticari_borclar():
    if 'logged_in' not in session: return redirect(url_for('index'))
    return render_template('base.html', content="<div class='alert alert-info m-5 text-center'><h3>Ticari Borçlar Modülü</h3><p>Yapım Aşamasında...</p><a href='/' class='btn btn-primary'>Ana Ekrana Dön</a></div>")

@app.route('/giderler')
def giderler():
    if 'logged_in' not in session: return redirect(url_for('index'))
    return render_template('base.html', content="<div class='alert alert-info m-5 text-center'><h3>Giderler Modülü</h3><p>Yapım Aşamasında...</p><a href='/' class='btn btn-primary'>Ana Ekrana Dön</a></div>")


# --- LOGIN & SİSTEM ---
@app.route('/kurlari_guncelle')
def kurlari_guncelle():
    kurlari_sabitle()
    # Gelinen sayfaya geri dön
    return redirect(request.referrer or url_for('index'))

@app.route('/login', methods=['POST'])
def login():
    if request.form.get('username') == 'admin' and request.form.get('password') == '1234':
        session.permanent = True 
        session['logged_in'] = True
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('index'))

# --- MÜŞTERİ İŞLEMLERİ (Aynen Korundu) ---
@app.route('/musteriler')
def musteriler():
    if 'logged_in' not in session: return redirect(url_for('index'))
    arama_terimi = request.args.get('q')
    if arama_terimi:
        bulunanlar = Musteri.query.filter(
            Musteri.durum == 'Aktif',
            or_(Musteri.ad_soyad.contains(arama_terimi), Musteri.isyeri_adi.contains(arama_terimi))
        ).all()
        return render_template('musteriler.html', musteriler=bulunanlar, arama_var=True, terim=arama_terimi)
    return render_template('musteriler.html', musteriler=Musteri.query.filter_by(durum='Aktif').all(), arama_var=False)

@app.route('/pasif_musteriler')
def pasif_musteriler():
    if 'logged_in' not in session: return redirect(url_for('index'))
    return render_template('pasif_musteriler.html', musteriler=Musteri.query.filter_by(durum='Pasif').all())

@app.route('/musteri_aktif_et/<int:id>')
def musteri_aktif_et(id):
    if 'logged_in' not in session: return redirect(url_for('index'))
    musteri = Musteri.query.get_or_404(id)
    musteri.durum = 'Aktif'
    db.session.commit()
    return redirect(url_for('musteriler'))

@app.route('/musteri_ekle', methods=['POST'])
def musteri_ekle():
    db.session.add(Musteri(
        ad_soyad=request.form.get('ad_soyad'), 
        telefon=request.form.get('telefon'),
        isyeri_adi=request.form.get('isyeri_adi'),
        isyeri_adresi=request.form.get('isyeri_adresi'),
        durum='Aktif'
    ))
    db.session.commit()
    # İşlem bitince Satışlar sayfasına dön
    return redirect(url_for('satislar'))

@app.route('/musteri_duzenle/<int:id>', methods=['GET', 'POST'])
def musteri_duzenle(id):
    if 'logged_in' not in session: return redirect(url_for('index'))
    musteri = Musteri.query.get_or_404(id)
    if request.method == 'POST':
        musteri.ad_soyad = request.form.get('ad_soyad')
        musteri.telefon = request.form.get('telefon')
        musteri.isyeri_adi = request.form.get('isyeri_adi')
        musteri.isyeri_adresi = request.form.get('isyeri_adresi')
        db.session.commit()
        return redirect(url_for('musteriler'))
    return render_template('musteri_duzenle.html', musteri=musteri)

@app.route('/musteri_sil/<int:id>')
def musteri_sil(id):
    if 'logged_in' not in session: return redirect(url_for('index'))
    musteri = Musteri.query.get_or_404(id)
    if musteri.isler or musteri.odemeler:
        musteri.durum = 'Pasif'
        db.session.commit()
    else:
        db.session.delete(musteri)
        db.session.commit()
    return redirect(url_for('musteriler'))

# --- İŞ VE ÖDEME İŞLEMLERİ (Aynen Korundu) ---
@app.route('/is_ekle')
def is_ekle():
    if 'logged_in' not in session: return redirect(url_for('index'))
    return render_template('is_ekle.html', musteriler=Musteri.query.filter_by(durum='Aktif').all())

@app.route('/is_kaydet', methods=['POST'])
def is_kaydet():
    m_id = int(request.form.get('musteri_id'))
    is_adi = request.form.get('is_tanimi')
    t_bedel = float(request.form.get('toplam_bedel') or 0)
    p_birimi = request.form.get('para_birimi')
    
    yeni_is = IsKaydi(
        is_tanimi=is_adi,
        toplam_bedel=round(t_bedel, 2),
        para_birimi=p_birimi,
        teslim_tarihi=request.form.get('teslim_tarihi'),
        durum='Devam Ediyor',
        musteri_id=m_id
    )
    db.session.add(yeni_is)
    
    a_kapora = float(request.form.get('alinan_kapora') or 0)
    if a_kapora > 0:
        k_birimi = request.form.get('kapora_birimi')
        islem_kuru = GUNCEL_KURLAR.get(k_birimi, 1.0) if k_birimi != 'TL' else 1.0
        yeni_odeme = Odeme(
            tutar=round(a_kapora, 2),
            birim=k_birimi,
            aciklama=f"Kapora ({is_adi})", 
            kur_degeri=islem_kuru,
            musteri_id=m_id
        )
        db.session.add(yeni_odeme)
    
    db.session.commit()
    return redirect(url_for('satislar')) # Yönlendirme güncellendi

@app.route('/is_teslim_et/<int:id>')
def is_teslim_et(id):
    if 'logged_in' not in session: return redirect(url_for('index'))
    is_kaydi = IsKaydi.query.get_or_404(id)
    is_kaydi.durum = 'Teslim Edildi'
    db.session.commit()
    return redirect(url_for('musteri_detay', id=is_kaydi.musteri_id))

@app.route('/is_durum_geri_al/<int:id>')
def is_durum_geri_al(id):
    if 'logged_in' not in session: return redirect(url_for('index'))
    is_kaydi = IsKaydi.query.get_or_404(id)
    is_kaydi.durum = 'Devam Ediyor'
    db.session.commit()
    return redirect(url_for('musteri_detay', id=is_kaydi.musteri_id))

@app.route('/is_sil/<int:id>')
def is_sil(id):
    if 'logged_in' not in session: return redirect(url_for('index'))
    is_kaydi = IsKaydi.query.get_or_404(id)
    musteri_id = is_kaydi.musteri_id
    db.session.delete(is_kaydi)
    db.session.commit()
    return redirect(url_for('musteri_detay', id=musteri_id))

@app.route('/musteri_odeme_ekle/<int:m_id>', methods=['POST'])
def musteri_odeme_ekle(m_id):
    birim = request.form.get('birim')
    islem_kuru = GUNCEL_KURLAR.get(birim, 1.0) if birim != 'TL' else 1.0
    yeni_odeme = Odeme(
        tutar=round(float(request.form.get('tutar') or 0), 2),
        birim=birim,
        aciklama=request.form.get('aciklama'),
        kur_degeri=islem_kuru,
        musteri_id=m_id
    )
    db.session.add(yeni_odeme)
    db.session.commit()
    return redirect(url_for('musteri_detay', id=m_id))

@app.route('/odeme_sil/<int:id>')
def odeme_sil(id):
    if 'logged_in' not in session: return redirect(url_for('index'))
    odeme = Odeme.query.get_or_404(id)
    musteri_id = odeme.musteri_id
    db.session.delete(odeme)
    db.session.commit()
    return redirect(url_for('musteri_detay', id=musteri_id))

@app.route('/musteri/<int:id>')
def musteri_detay(id):
    if 'logged_in' not in session: return redirect(url_for('index'))
    musteri = Musteri.query.get_or_404(id)
    toplam_borc_tl = 0
    toplam_odenen_tl = 0
    for i in musteri.isler:
        toplam_borc_tl += (i.toplam_bedel * GUNCEL_KURLAR.get(i.para_birimi, 1.0))
    for o in musteri.odemeler:
        toplam_odenen_tl += (o.tutar * o.kur_degeri)
    net_tl = round(toplam_borc_tl - toplam_odenen_tl, 2)
    net_usd = round(net_tl / GUNCEL_KURLAR.get('USD', 1.0), 2)
    return render_template('musteri_detay.html', musteri=musteri, toplam_tl=net_tl, toplam_usd=net_usd, kurlar=GUNCEL_KURLAR)

@app.route('/pdf_indir/<int:id>')
def pdf_indir(id):
    musteri = Musteri.query.get_or_404(id)
    t_borc_tl = sum(i.toplam_bedel * GUNCEL_KURLAR.get(i.para_birimi, 1.0) for i in musteri.isler)
    t_odenen_tl = sum(o.tutar * o.kur_degeri for o in musteri.odemeler)
    net_tl = t_borc_tl - t_odenen_tl
    net_usd = net_tl / GUNCEL_KURLAR.get('USD', 1.0)

    logo_path = os.path.join(app.root_path, 'static', 'logo.png')
    rendered = render_template('pdf_sablonu.html', musteri=musteri, toplam_tl=round(net_tl, 2), toplam_usd=round(net_usd, 2), bugun=datetime.now().strftime('%d.%m.%Y'), logo_url=logo_path)

    if platform.system() == "Windows":
        path_wkhtmltopdf = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'
        config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)
    else:
        config = pdfkit.configuration(wkhtmltopdf='/usr/bin/wkhtmltopdf')
    
    options = {'encoding': "UTF-8", 'quiet': '', 'enable-local-file-access': None}
    pdf = pdfkit.from_string(rendered, False, configuration=config, options=options)
    
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    filename = f"{musteri.ad_soyad}_ekstre.pdf"
    safe_filename = quote(filename)
    response.headers['Content-Disposition'] = f"attachment; filename*=UTF-8''{safe_filename}"
    return response

@app.route('/ticari_borclar')
def ticari_borclar():
    if 'logged_in' not in session: return redirect(url_for('index'))
    
    # Arama var mı?
    arama_terimi = request.args.get('q')
    if arama_terimi:
        bulunanlar = Tedarikci.query.filter(
            Tedarikci.durum == 'Aktif',
            or_(
                Tedarikci.firma_adi.contains(arama_terimi),
                Tedarikci.yetkili_kisi.contains(arama_terimi)
            )
        ).all()
        return render_template('ticari_borclar.html', tedarikciler=bulunanlar, arama_var=True, terim=arama_terimi)
    
    return render_template('ticari_borclar.html', tedarikciler=Tedarikci.query.filter_by(durum='Aktif').all(), arama_var=False)

@app.route('/tedarikci_ekle', methods=['POST'])
def tedarikci_ekle():
    if 'logged_in' not in session: return redirect(url_for('index'))
    db.session.add(Tedarikci(
        firma_adi=request.form.get('firma_adi'),
        yetkili_kisi=request.form.get('yetkili_kisi'),
        telefon=request.form.get('telefon'),
        adres=request.form.get('adres'),
        durum='Aktif'
    ))
    db.session.commit()
    return redirect(url_for('ticari_borclar'))

@app.route('/tedarikci/<int:id>')
def tedarikci_detay(id):
    if 'logged_in' not in session: return redirect(url_for('index'))
    tedarikci = Tedarikci.query.get_or_404(id)
    
    toplam_borc_tl = 0
    toplam_odenen_tl = 0
    
    # 1. Malzeme Alımları (Borçlanma)
    for alim in tedarikci.satin_almalar:
        kur = GUNCEL_KURLAR.get(alim.para_birimi, 1.0)
        toplam_borc_tl += (alim.tutar * kur)
        
    # 2. Tedarikçiye Yapılan Ödemeler (Borç Düşme)
    for odeme in tedarikci.odenenler:
        # Ödeme anındaki kur (veritabanında kayıtlı olan)
        toplam_odenen_tl += (odeme.tutar * odeme.kur_degeri)
        
    net_borc_tl = round(toplam_borc_tl - toplam_odenen_tl, 2)
    net_borc_usd = round(net_borc_tl / GUNCEL_KURLAR.get('USD', 1.0), 2)
    
    return render_template('tedarikci_detay.html', 
                           tedarikci=tedarikci, 
                           toplam_tl=net_borc_tl, 
                           toplam_usd=net_borc_usd,
                           kurlar=GUNCEL_KURLAR)

@app.route('/malzeme_alim_ekle', methods=['POST'])
def malzeme_alim_ekle():
    if 'logged_in' not in session: return redirect(url_for('index'))
    t_id = int(request.form.get('tedarikci_id'))
    
    yeni_alim = SatinAlma(
        malzeme_tanimi=request.form.get('malzeme_tanimi'),
        tutar=float(request.form.get('tutar') or 0),
        para_birimi=request.form.get('para_birimi'),
        fatura_no=request.form.get('fatura_no'), # FATURA NO EKLENDİ
        tarih=datetime.now(), # Otomatik şimdiki zaman
        tedarikci_id=t_id
    )
    db.session.add(yeni_alim)
    db.session.commit()
    return redirect(url_for('tedarikci_detay', id=t_id))

@app.route('/tedarikci_odeme_yap', methods=['POST'])
def tedarikci_odeme_yap():
    if 'logged_in' not in session: return redirect(url_for('index'))
    t_id = int(request.form.get('tedarikci_id'))
    birim = request.form.get('birim')
    
    # İşlem anındaki kur
    islem_kuru = GUNCEL_KURLAR.get(birim, 1.0) if birim != 'TL' else 1.0
    
    yeni_odeme = TedarikciOdeme(
        tutar=float(request.form.get('tutar') or 0),
        birim=birim,
        aciklama=request.form.get('aciklama'),
        kur_degeri=islem_kuru,
        tedarikci_id=t_id
    )
    db.session.add(yeni_odeme)
    db.session.commit()
    return redirect(url_for('tedarikci_detay', id=t_id))

@app.route('/alim_sil/<int:id>')
def alim_sil(id):
    if 'logged_in' not in session: return redirect(url_for('index'))
    kayit = SatinAlma.query.get_or_404(id)
    t_id = kayit.tedarikci_id
    db.session.delete(kayit)
    db.session.commit()
    return redirect(url_for('tedarikci_detay', id=t_id))

@app.route('/tedarikci_odeme_sil/<int:id>')
def tedarikci_odeme_sil(id):
    if 'logged_in' not in session: return redirect(url_for('index'))
    kayit = TedarikciOdeme.query.get_or_404(id)
    t_id = kayit.tedarikci_id
    db.session.delete(kayit)
    db.session.commit()
    return redirect(url_for('tedarikci_detay', id=t_id))

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        kurlari_sabitle()
    app.run(debug=True, host='0.0.0.0')