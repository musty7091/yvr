from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# Veritabanı bağlantısını başlatan ana nesne
db = SQLAlchemy()

class Ayarlar(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ay_hedefi = db.Column(db.Float, default=50000.0)

class BankaKasa(db.Model):
    """Sistemdeki tüm banka hesapları ve nakit kasaların tanımlandığı yer"""
    id = db.Column(db.Integer, primary_key=True)
    ad = db.Column(db.String(100), nullable=False) # Örn: Ziraat Bankası, Merkez Kasa
    tur = db.Column(db.String(50), default='Banka') # Banka, Kasa, POS
    hesap_no = db.Column(db.String(50)) # İsteğe bağlı hesap numarası
    durum = db.Column(db.String(20), default='Aktif')
    
    # İlişkiler (Bu kasaya giren ve çıkan paralar)
    musteri_odemeleri = db.relationship('Odeme', backref='kasa_kaydi', lazy=True)
    tedarikci_odemeleri = db.relationship('TedarikciOdeme', backref='kasa_kaydi', lazy=True)
    isletme_giderleri = db.relationship('Gider', backref='kasa_kaydi', lazy=True)

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
    maliyet = db.Column(db.Float, default=0.0) 
    teslim_tarihi = db.Column(db.String(20))
    # --- YENİ EKLENEN ALANLAR ---
    vade_gun = db.Column(db.Integer, default=0) # İş tesliminden kaç gün sonra ödeme beklendiği
    teslim_edildi_tarihi = db.Column(db.DateTime, nullable=True) # İşin gerçekten teslim edildiği tarih
    # ----------------------------
    durum = db.Column(db.String(20), default='Devam Ediyor')
    kayit_tarihi = db.Column(db.DateTime, default=datetime.now)
    musteri_id = db.Column(db.Integer, db.ForeignKey('musteri.id'), nullable=False)

class Odeme(db.Model):
    """Müşteriden gelen paralar (Gelirler)"""
    id = db.Column(db.Integer, primary_key=True)
    tutar = db.Column(db.Float, nullable=False)
    birim = db.Column(db.String(5), default='TL')
    aciklama = db.Column(db.String(200))
    odeme_yontemi = db.Column(db.String(50), default='Havale/EFT') # Nakit, POS, Çek vb.
    
    # Kasa bağlantısı
    banka_kasa_id = db.Column(db.Integer, db.ForeignKey('banka_kasa.id'), nullable=True)
    
    kur_degeri = db.Column(db.Float, default=1.0)
    odeme_tarihi = db.Column(db.DateTime, default=datetime.now)
    musteri_id = db.Column(db.Integer, db.ForeignKey('musteri.id'), nullable=False)

class Tedarikci(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    firma_adi = db.Column(db.String(150), nullable=False)
    yetkili_kisi = db.Column(db.String(100))
    telefon = db.Column(db.String(20))
    adres = db.Column(db.Text)
    durum = db.Column(db.String(20), default='Aktif')
    satin_almalar = db.relationship('SatinAlma', backref='tedarikci', lazy=True)
    odenenler = db.relationship('TedarikciOdeme', backref='tedarikci', lazy=True)

class SatinAlma(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    malzeme_tanimi = db.Column(db.String(200), nullable=False)
    tutar = db.Column(db.Float, nullable=False)
    para_birimi = db.Column(db.String(5), default='TL')
    fatura_no = db.Column(db.String(50))
    tarih = db.Column(db.DateTime, default=datetime.now)
    tedarikci_id = db.Column(db.Integer, db.ForeignKey('tedarikci.id'), nullable=False)

class TedarikciOdeme(db.Model):
    """Tedarikçiye ödenen paralar (Giderler)"""
    id = db.Column(db.Integer, primary_key=True)
    tutar = db.Column(db.Float, nullable=False)
    birim = db.Column(db.String(5), default='TL')
    aciklama = db.Column(db.String(200))
    
    # Kasa bağlantısı
    banka_kasa_id = db.Column(db.Integer, db.ForeignKey('banka_kasa.id'), nullable=True)
    
    kur_degeri = db.Column(db.Float, default=1.0)
    odeme_tarihi = db.Column(db.DateTime, default=datetime.now)
    tedarikci_id = db.Column(db.Integer, db.ForeignKey('tedarikci.id'), nullable=False)

class Gider(db.Model):
    """Genel işletme giderleri (Kira, Fatura vb.)"""
    id = db.Column(db.Integer, primary_key=True)
    kategori = db.Column(db.String(50))
    aciklama = db.Column(db.String(200))
    tutar = db.Column(db.Float, nullable=False)
    birim = db.Column(db.String(5), default='TL')
    
    # Kasa bağlantısı
    banka_kasa_id = db.Column(db.Integer, db.ForeignKey('banka_kasa.id'), nullable=True)
    
    kur_degeri = db.Column(db.Float, default=1.0)
    tarih = db.Column(db.DateTime, default=datetime.now)

class Transfer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tutar = db.Column(db.Float, nullable=False)
    tarih = db.Column(db.DateTime, default=datetime.now)
    aciklama = db.Column(db.String(200))
    
    # Paranın çıktığı hesap
    kaynak_hesap_id = db.Column(db.Integer, db.ForeignKey('banka_kasa.id'), nullable=False)
    # Paranın girdiği hesap
    hedef_hesap_id = db.Column(db.Integer, db.ForeignKey('banka_kasa.id'), nullable=False)

    # İlişkiler (Karışmaması için özel isimlerle)
    kaynak = db.relationship('BankaKasa', foreign_keys=[kaynak_hesap_id])
    hedef = db.relationship('BankaKasa', foreign_keys=[hedef_hesap_id])