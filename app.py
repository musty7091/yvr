import requests
import xml.etree.ElementTree as ET
from flask import Flask, render_template, request, redirect, url_for, session, make_response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_
from datetime import datetime, timedelta
import pdfkit
import os
import platform  # YENİ: İşletim sistemi tespiti için
from urllib.parse import quote  # YENİ: Türkçe dosya ismi hatasını çözmek için

app = Flask(__name__)
app.secret_key = 'yvr_ozel_sifre_123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///yvr_veritabani.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# GÜVENLİK: 3 Dakika işlem yapılmazsa oturum kapanır
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=3)

db = SQLAlchemy(app)

# --- GLOBAL HAFIZA (Günün Sabit Kurları) ---
GUNCEL_KURLAR = {"USD": 34.0, "EUR": 36.5, "GBP": 42.0, "tarih": "Henüz Güncellenmedi"}

# --- VERİTABANI MODELLERİ ---

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

class Odeme(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tutar = db.Column(db.Float, nullable=False)
    birim = db.Column(db.String(5), default='TL')
    aciklama = db.Column(db.String(200))
    kur_degeri = db.Column(db.Float, default=1.0)
    odeme_tarihi = db.Column(db.DateTime, default=datetime.now)
    musteri_id = db.Column(db.Integer, db.ForeignKey('musteri.id'), nullable=False)

# --- KUR SABİTLEME FONKSİYONU ---

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

# --- ROTALAR ---

@app.route('/')
def index():
    if 'logged_in' not in session:
        return render_template('giris.html')
    
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

    toplam_musteri = Musteri.query.count()
    aktif_musteri_sayisi = len(aktif_musteriler)
    biten_isler = IsKaydi.query.filter_by(durum='Teslim Edildi').count()
    
    simdi = datetime.now()
    tum_odemeler = Odeme.query.all()
    bu_ayki_ciro = 0
    
    for o in tum_odemeler:
        if o.odeme_tarihi.month == simdi.month and o.odeme_tarihi.year == simdi.year:
            kur = GUNCEL_KURLAR.get(o.birim, 1.0)
            bu_ayki_ciro += (o.tutar * kur)

    tum_yaklasan = IsKaydi.query.filter(
        IsKaydi.teslim_tarihi != "", 
        IsKaydi.durum == 'Devam Ediyor'
    ).order_by(IsKaydi.teslim_tarihi.asc()).all()
    
    yaklasan_isler = [is_kaydi for is_kaydi in tum_yaklasan if is_kaydi.sahibi.durum == 'Aktif'][:5]
            
    return render_template('index.html', 
                           alacak=round(toplam_alacak_tl, 2), 
                           is_sayisi=devam_eden_is_sayisi, 
                           yaklasan_isler=yaklasan_isler,
                           kurlar=GUNCEL_KURLAR,
                           t_musteri=toplam_musteri,
                           a_musteri=aktif_musteri_sayisi,
                           biten_is=biten_isler,
                           ay_ciro=round(bu_ayki_ciro, 2))

@app.route('/kurlari_guncelle')
def kurlari_guncelle():
    kurlari_sabitle()
    return redirect(url_for('index'))

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

@app.route('/musteriler')
def musteriler():
    if 'logged_in' not in session: return redirect(url_for('index'))
    
    arama_terimi = request.args.get('q')
    
    if arama_terimi:
        bulunanlar = Musteri.query.filter(
            Musteri.durum == 'Aktif',
            or_(
                Musteri.ad_soyad.contains(arama_terimi),
                Musteri.isyeri_adi.contains(arama_terimi)
            )
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
    return redirect(url_for('musteriler'))

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
    return redirect(url_for('index'))

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
    
    return render_template('musteri_detay.html', 
                           musteri=musteri, 
                           toplam_tl=net_tl, 
                           toplam_usd=net_usd,
                           kurlar=GUNCEL_KURLAR)

@app.route('/pdf_indir/<int:id>')
def pdf_indir(id):
    musteri = Musteri.query.get_or_404(id)
    
    t_borc_tl = sum(i.toplam_bedel * GUNCEL_KURLAR.get(i.para_birimi, 1.0) for i in musteri.isler)
    t_odenen_tl = sum(o.tutar * o.kur_degeri for o in musteri.odemeler)
    net_tl = t_borc_tl - t_odenen_tl
    net_usd = net_tl / GUNCEL_KURLAR.get('USD', 1.0)

    logo_path = os.path.join(app.root_path, 'static', 'logo.png')

    rendered = render_template('pdf_sablonu.html', 
                               musteri=musteri, 
                               toplam_tl=round(net_tl, 2), 
                               toplam_usd=round(net_usd, 2),
                               bugun=datetime.now().strftime('%d.%m.%Y'),
                               logo_url=logo_path)

    # --- DÜZELTME 1: OTOMATİK PDF YOLU (Windows / Linux) ---
    if platform.system() == "Windows":
        # Senin bilgisayarındaki yol
        path_wkhtmltopdf = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'
        config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)
    else:
        # PythonAnywhere veya Linux Sunucu yolu
        config = pdfkit.configuration(wkhtmltopdf='/usr/bin/wkhtmltopdf')
    
    options = {
        'encoding': "UTF-8", 
        'quiet': '',
        'enable-local-file-access': None
    }
    
    pdf = pdfkit.from_string(rendered, False, configuration=config, options=options)
    
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    
    # --- DÜZELTME 2: TÜRKÇE DOSYA ADI HATASI ÇÖZÜMÜ ---
    filename = f"{musteri.ad_soyad}_ekstre.pdf"
    # Dosya ismini URL uyumlu hale getir (boşlukları %20 yapar, Türkçe karakterleri kodlar)
    safe_filename = quote(filename)
    
    # Modern tarayıcılar için UTF-8 destekli başlık formatı
    response.headers['Content-Disposition'] = f"attachment; filename*=UTF-8''{safe_filename}"
    
    return response

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        kurlari_sabitle()
    app.run(debug=True, host='0.0.0.0')