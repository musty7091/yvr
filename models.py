from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import Numeric

db = SQLAlchemy()

# -----------------------------
# Decimal / Numeric Ayarları
# -----------------------------
MONEY = Numeric(18, 2, asdecimal=True)   # Para: 2 hane (kuruş)
RATE  = Numeric(18, 6, asdecimal=True)   # Kur: 6 hane (fx için yeterli)

Q2 = Decimal("0.01")
Q6 = Decimal("0.000001")


# -----------------------------
# Para Birimi Normalizasyonu
# -----------------------------
def normalize_currency(pb: str) -> str:
    """
    Uygulama genelinde para birimini tek standarda çeker.
    TL, ₺, try gibi gelenleri TRY yapar.
    Boş/None gelirse TRY döner.
    """
    s = (pb or "").strip().upper()
    if s in ("", "NONE", "NULL"):
        return "TRY"
    if s in ("TL", "₺", "TRY"):
        return "TRY"
    return s


# -----------------------------
# Decimal dönüşüm yardımcıları
# -----------------------------
def clean_number_string(s: str) -> str:
    """
    Türkiye/Avrupa formatı dahil sayısal string temizliği.
    Örn:
      "1.234,56" -> "1234.56"
      "1,234.56" -> "1234.56"
      "1234"     -> "1234"
      " 1 234,56 "-> "1234.56"
    """
    s = (s or "").strip()
    if s == "":
        return ""

    # Boşlukları kaldır
    s = s.replace(" ", "")

    # Hem '.' hem ',' varsa: hangisi sondaysa o "ondalık ayırıcı" kabul edilir.
    if "." in s and "," in s:
        if s.rfind(",") > s.rfind("."):
            # "1.234,56" gibi: binlik '.' kaldır, ',' -> '.'
            s = s.replace(".", "")
            s = s.replace(",", ".")
        else:
            # "1,234.56" gibi: binlik ',' kaldır
            s = s.replace(",", "")
    else:
        # Sadece ',' varsa onu ondalık kabul et
        if "," in s and "." not in s:
            s = s.replace(",", ".")

    return s


def D(v, default="0"):
    """
    Güvenli Decimal dönüşümü.
    float -> Decimal(float) yapmıyoruz (hata biriktirir).
    Mutlaka string üzerinden çeviriyoruz.
    """
    if v is None or v == "":
        return Decimal(default)

    if isinstance(v, Decimal):
        return v

    if isinstance(v, (int, float)):
        return Decimal(str(v))

    s = clean_number_string(str(v))
    if s == "":
        return Decimal(default)

    return Decimal(s)


def money(v):
    return D(v).quantize(Q2, rounding=ROUND_HALF_UP)


def rate(v):
    return D(v, "1").quantize(Q6, rounding=ROUND_HALF_UP)


# -----------------------------
# MODELLER
# -----------------------------
class Kullanici(db.Model):
    __tablename__ = "kullanici"

    id = db.Column(db.Integer, primary_key=True)
    kullanici_adi = db.Column(db.String(50), unique=True, nullable=False)
    sifre_hash = db.Column(db.String(255), nullable=False)

    def sifre_belirle(self, sifre):
        sifre = (sifre or "").strip()
        if sifre == "":
            raise ValueError("Şifre boş olamaz.")
        self.sifre_hash = generate_password_hash(sifre)

    def sifre_kontrol(self, sifre):
        return check_password_hash(self.sifre_hash, sifre or "")


class Ayarlar(db.Model):
    __tablename__ = "ayarlar"

    id = db.Column(db.Integer, primary_key=True)
    ay_hedefi = db.Column(MONEY, default=Decimal("50000.00"))


class BankaKasa(db.Model):
    __tablename__ = "banka_kasa"

    id = db.Column(db.Integer, primary_key=True)
    ad = db.Column(db.String(100), nullable=False)
    tur = db.Column(db.String(50))  # Nakit, Banka, Kredi Kartı
    hesap_no = db.Column(db.String(50))

    # Başlangıç (setup) bakiyesi
    baslangic_bakiye = db.Column(MONEY, default=Decimal("0.00"))

    # ÇALIŞAN SİSTEM İÇİN: route'ların kullandığı güncel bakiye alanı
    bakiye = db.Column(MONEY, default=Decimal("0.00"))

    # backref adı: kasa_kaydi -> template’lerle uyumlu
    odemeler = db.relationship("Odeme", backref="kasa_kaydi", lazy=True)
    giderler = db.relationship("Gider", backref="kasa_kaydi", lazy=True)
    tedarikci_odemeleri = db.relationship("TedarikciOdeme", backref="kasa_kaydi", lazy=True)


class Musteri(db.Model):
    __tablename__ = "musteri"

    id = db.Column(db.Integer, primary_key=True)
    ad_soyad = db.Column(db.String(100), nullable=False)
    telefon = db.Column(db.String(20))
    isyeri_adi = db.Column(db.String(200))
    isyeri_adresi = db.Column(db.Text)
    durum = db.Column(db.String(20), default="Aktif")

    isler = db.relationship("IsKaydi", backref="sahibi", lazy=True)
    odemeler = db.relationship("Odeme", backref="musteri", lazy=True)


class IsKaydi(db.Model):
    __tablename__ = "is_kaydi"

    id = db.Column(db.Integer, primary_key=True)
    is_tanimi = db.Column(db.String(200), nullable=False)

    toplam_bedel = db.Column(MONEY, nullable=False, default=Decimal("0.00"))
    para_birimi = db.Column(db.String(5), default="TRY")
    maliyet = db.Column(MONEY, default=Decimal("0.00"))

    teslim_tarihi = db.Column(db.String(20))

    vade_gun = db.Column(db.Integer, default=0)
    teslim_edildi_tarihi = db.Column(db.DateTime, nullable=True)

    durum = db.Column(db.String(20), default="Devam Ediyor")
    kayit_tarihi = db.Column(db.DateTime, default=datetime.now)

    musteri_id = db.Column(db.Integer, db.ForeignKey("musteri.id"), nullable=False)

    odemeler = db.relationship("Odeme", backref="ait_oldugu_is", lazy=True)


class Odeme(db.Model):
    """Müşteriden gelen paralar (Gelirler)"""
    __tablename__ = "odeme"

    id = db.Column(db.Integer, primary_key=True)

    tutar = db.Column(MONEY, nullable=False, default=Decimal("0.00"))
    birim = db.Column(db.String(5), default="TRY")

    aciklama = db.Column(db.String(200))
    odeme_yontemi = db.Column(db.String(50), default="Havale/EFT")

    banka_kasa_id = db.Column(db.Integer, db.ForeignKey("banka_kasa.id"), nullable=True)

    kur_degeri = db.Column(RATE, default=Decimal("1.000000"))
    odeme_tarihi = db.Column(db.DateTime, default=datetime.now)

    musteri_id = db.Column(db.Integer, db.ForeignKey("musteri.id"), nullable=False)
    is_kaydi_id = db.Column(db.Integer, db.ForeignKey("is_kaydi.id"), nullable=True)


class Tedarikci(db.Model):
    __tablename__ = "tedarikci"

    id = db.Column(db.Integer, primary_key=True)
    firma_adi = db.Column(db.String(150), nullable=False)
    yetkili_kisi = db.Column(db.String(100))
    telefon = db.Column(db.String(20))
    adres = db.Column(db.Text)
    durum = db.Column(db.String(20), default="Aktif")

    satin_almalar = db.relationship("SatinAlma", backref="tedarikci", lazy=True)
    odenenler = db.relationship("TedarikciOdeme", backref="tedarikci", lazy=True)


class SatinAlma(db.Model):
    __tablename__ = "satin_alma"

    id = db.Column(db.Integer, primary_key=True)
    malzeme_tanimi = db.Column(db.String(200), nullable=False)

    tutar = db.Column(MONEY, nullable=False, default=Decimal("0.00"))
    para_birimi = db.Column(db.String(5), default="TRY")

    fatura_no = db.Column(db.String(50))
    tarih = db.Column(db.DateTime, default=datetime.now)

    tedarikci_id = db.Column(db.Integer, db.ForeignKey("tedarikci.id"), nullable=False)


class TedarikciOdeme(db.Model):
    """Tedarikçiye ödenen paralar (Giderler)"""
    __tablename__ = "tedarikci_odeme"

    id = db.Column(db.Integer, primary_key=True)

    tutar = db.Column(MONEY, nullable=False, default=Decimal("0.00"))
    birim = db.Column(db.String(5), default="TRY")

    aciklama = db.Column(db.String(200))

    banka_kasa_id = db.Column(db.Integer, db.ForeignKey("banka_kasa.id"), nullable=True)

    kur_degeri = db.Column(RATE, default=Decimal("1.000000"))
    odeme_tarihi = db.Column(db.DateTime, default=datetime.now)

    tedarikci_id = db.Column(db.Integer, db.ForeignKey("tedarikci.id"), nullable=False)


class Gider(db.Model):
    """Genel işletme giderleri (Kira, Fatura vb.)"""
    __tablename__ = "gider"

    id = db.Column(db.Integer, primary_key=True)

    kategori = db.Column(db.String(50))
    aciklama = db.Column(db.String(200))

    tutar = db.Column(MONEY, nullable=False, default=Decimal("0.00"))
    birim = db.Column(db.String(5), default="TRY")

    banka_kasa_id = db.Column(db.Integer, db.ForeignKey("banka_kasa.id"), nullable=True)

    kur_degeri = db.Column(RATE, default=Decimal("1.000000"))
    tarih = db.Column(db.DateTime, default=datetime.now)


class Transfer(db.Model):
    __tablename__ = "transfer"

    id = db.Column(db.Integer, primary_key=True)

    tutar = db.Column(MONEY, nullable=False, default=Decimal("0.00"))
    tarih = db.Column(db.DateTime, default=datetime.now)

    aciklama = db.Column(db.String(200))

    kaynak_hesap_id = db.Column(db.Integer, db.ForeignKey("banka_kasa.id"), nullable=False)
    hedef_hesap_id = db.Column(db.Integer, db.ForeignKey("banka_kasa.id"), nullable=False)

    kaynak = db.relationship("BankaKasa", foreign_keys=[kaynak_hesap_id])
    hedef = db.relationship("BankaKasa", foreign_keys=[hedef_hesap_id])
