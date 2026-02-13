from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# Veritabanı bağlantısını başlatan ana nesne
db = SQLAlchemy()

class Musteri(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ad_soyad = db.Column(db.String(100), nullable=False)
    telefon = db.Column(db.String(20))
    isyeri_adi = db.Column(db.String(200)) 
    isyeri_adresi = db.Column(db.Text)
    durum = db.Column(db.String(20), default='Aktif') 
    # İlişkiler (Diğer tablolarla bağlantı)
    isler = db.relationship('IsKaydi', backref='sahibi', lazy=True)
    odemeler = db.relationship('Odeme', backref='musteri', lazy=True)

class IsKaydi(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    is_tanimi = db.Column(db.String(200), nullable=False)
    toplam_bedel = db.Column(db.Float, nullable=False, default=0.0)
    para_birimi = db.Column(db.String(5), default='TL')
    
    # --- YENİ EKLENEN KRİTİK ALANLAR ---
    # Madde 2 için: Bu işin karını hesaplamak için maliyet alanı
    maliyet = db.Column(db.Float, default=0.0) 
    # Madde 4 için: Ödeme alarmı sisteminde kullanılacak teslim tarihi
    teslim_tarihi = db.Column(db.String(20)) 
    
    durum = db.Column(db.String(20), default='Devam Ediyor')
    kayit_tarihi = db.Column(db.DateTime, default=datetime.now)
    musteri_id = db.Column(db.Integer, db.ForeignKey('musteri.id'), nullable=False)

class Odeme(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tutar = db.Column(db.Float, nullable=False)
    birim = db.Column(db.String(5), default='TL')
    aciklama = db.Column(db.String(200))
    
    # --- YENİ EKLENEN KRİTİK ALAN ---
    # Madde 1 için: Paranın nereye girdiğini takip eden Kasa Modülü
    kasa_turu = db.Column(db.String(20), default='Nakit') 
    
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
    # İlişkiler
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
    id = db.Column(db.Integer, primary_key=True)
    tutar = db.Column(db.Float, nullable=False)
    birim = db.Column(db.String(5), default='TL')
    aciklama = db.Column(db.String(200))
    kur_degeri = db.Column(db.Float, default=1.0)
    odeme_tarihi = db.Column(db.DateTime, default=datetime.now)
    tedarikci_id = db.Column(db.Integer, db.ForeignKey('tedarikci.id'), nullable=False)

class Gider(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kategori = db.Column(db.String(50))
    aciklama = db.Column(db.String(200))
    tutar = db.Column(db.Float, nullable=False)
    birim = db.Column(db.String(5), default='TL')
    kur_degeri = db.Column(db.Float, default=1.0)
    tarih = db.Column(db.DateTime, default=datetime.now)