import requests
import xml.etree.ElementTree as ET
from flask import Flask, render_template, request, redirect, url_for, session, make_response, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import pdfkit
import os

app = Flask(__name__)
app.secret_key = 'yvr_ozel_sifre_123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///yvr_veritabani.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
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
    isler = db.relationship('IsKaydi', backref='sahibi', lazy=True)
    odemeler = db.relationship('Odeme', backref='musteri', lazy=True)

class IsKaydi(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    is_tanimi = db.Column(db.String(200), nullable=False)
    toplam_bedel = db.Column(db.Float, nullable=False, default=0.0)
    para_birimi = db.Column(db.String(5), default='TL')
    teslim_tarihi = db.Column(db.String(20))
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
    
    isler = IsKaydi.query.all()
    toplam_alacak_tl = 0
    
    musteriler = Musteri.query.all()
    for m in musteriler:
        for i in m.isler:
            kur = GUNCEL_KURLAR.get(i.para_birimi, 1.0)
            toplam_alacak_tl += (i.toplam_bedel * kur)
        for o in m.odemeler:
            kur = GUNCEL_KURLAR.get(o.birim, 1.0)
            toplam_alacak_tl -= (o.tutar * kur)
            
    yaklasan_isler = IsKaydi.query.filter(IsKaydi.teslim_tarihi != "").order_by(IsKaydi.teslim_tarihi.asc()).limit(5).all()
            
    return render_template('index.html', 
                           alacak=round(toplam_alacak_tl, 2), 
                           is_sayisi=len(isler), 
                           yaklasan_isler=yaklasan_isler,
                           kurlar=GUNCEL_KURLAR)

@app.route('/kurlari_guncelle')
def kurlari_guncelle():
    kurlari_sabitle()
    return redirect(url_for('index'))

@app.route('/login', methods=['POST'])
def login():
    if request.form.get('username') == 'admin' and request.form.get('password') == '1234':
        session['logged_in'] = True
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('index'))

@app.route('/musteriler')
def musteriler():
    if 'logged_in' not in session: return redirect(url_for('index'))
    return render_template('musteriler.html', musteriler=Musteri.query.all())

@app.route('/musteri_ekle', methods=['POST'])
def musteri_ekle():
    db.session.add(Musteri(
        ad_soyad=request.form.get('ad_soyad'), 
        telefon=request.form.get('telefon'),
        isyeri_adi=request.form.get('isyeri_adi'),
        isyeri_adresi=request.form.get('isyeri_adresi')
    ))
    db.session.commit()
    return redirect(url_for('musteriler'))

# --- YENİ EKLENEN: MÜŞTERİ DÜZENLEME ROTASI ---
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

# --- YENİ EKLENEN: MÜŞTERİ SİLME ROTASI ---
@app.route('/musteri_sil/<int:id>')
def musteri_sil(id):
    if 'logged_in' not in session: return redirect(url_for('index'))
    musteri = Musteri.query.get_or_404(id)
    
    # Müşteriyi silmeden önce ona bağlı işleri ve ödemeleri siliyoruz
    # Bu işlem veritabanı hatası almamak için önemlidir.
    try:
        for is_kaydi in musteri.isler:
            db.session.delete(is_kaydi)
        for odeme in musteri.odemeler:
            db.session.delete(odeme)
            
        db.session.delete(musteri)
        db.session.commit()
    except Exception as e:
        print(f"Hata oluştu: {e}")
        
    return redirect(url_for('musteriler'))

@app.route('/is_ekle')
def is_ekle():
    if 'logged_in' not in session: return redirect(url_for('index'))
    return render_template('is_ekle.html', musteriler=Musteri.query.all())

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

# --- YENİ EKLENEN: İŞ SİLME ROTASI ---
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

# --- YENİ EKLENEN: ÖDEME SİLME ROTASI ---
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

    # NOT: Bu yol kendi bilgisayarına göredir. Hata alırsan kontrol et.
    path_wkhtmltopdf = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'
    config = pdfkit.configuration(wkhtmltopdf=path_wkhtmltopdf)
    
    options = {
        'encoding': "UTF-8", 
        'quiet': '',
        'enable-local-file-access': None
    }
    
    pdf = pdfkit.from_string(rendered, False, configuration=config, options=options)
    
    response = make_response(pdf)
    response.headers['Content-Type'] = 'application/pdf'
    response.headers['Content-Disposition'] = f'attachment; filename={musteri.ad_soyad}_ekstre.pdf'
    return response

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        kurlari_sabitle()
    app.run(debug=True, host='0.0.0.0')