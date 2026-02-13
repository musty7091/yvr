from app import app
from models import db, Musteri, IsKaydi, Odeme, BankaKasa, Tedarikci, SatinAlma, Gider, TedarikciOdeme
from datetime import datetime, timedelta

def veri_tohumla():
    with app.app_context():
        # Veritabanı tablolarını oluştur
        db.create_all()

        # 1. KASALAR VE BANKALAR
        k1 = BankaKasa(ad="Ziraat Bankası Ticari", tur="Banka", durum="Aktif")
        k2 = BankaKasa(ad="Dükkan Nakit Kasa", tur="Kasa", durum="Aktif")
        db.session.add_all([k1, k2])
        db.session.commit()

        # 2. TEDARİKÇİLER (Malzeme Aldığın Yerler)
        t1 = Tedarikci(firma_adi="Öz Alüminyum A.Ş.", yetkili_kisi="Murat Bey", telefon="0212 555 10 20", durum="Aktif")
        t2 = Tedarikci(firma_adi="Pleksi Dünyası", yetkili_kisi="Selin Hanım", telefon="0212 444 30 40", durum="Aktif")
        t3 = Tedarikci(firma_adi="Folyo Market", yetkili_kisi="Ahmet Bey", telefon="0216 333 50 60", durum="Aktif")
        db.session.add_all([t1, t2, t3])
        db.session.commit()

        # 3. HAMMADDE ALIMLARI (Satın Almalar)
        # Bu kayıtlar senin "Borçlar" sayfanda görünecek
        s1 = SatinAlma(malzeme_tanimi="10 Adet Alüminyum Profil", tutar=12500.0, para_birimi="TL", fatura_no="FT-001", tedarikci_id=t1.id)
        s2 = SatinAlma(malzeme_tanimi="5 Plaka Şeffaf Pleksi", tutar=8500.0, para_birimi="TL", fatura_no="FT-002", tedarikci_id=t2.id)
        s3 = SatinAlma(malzeme_tanimi="3 Rulo Cast Folyo", tutar=450.0, para_birimi="USD", fatura_no="FT-003", tedarikci_id=t3.id)
        db.session.add_all([s1, s2, s3])
        db.session.commit()

        # 4. TEDARİKÇİ ÖDEMELERİ (Borçtan Düşülenler)
        # Alüminyumcuya bir miktar ödeme yapalım
        to1 = TedarikciOdeme(tutar=5000.0, birim="TL", aciklama="Profil alımı 1. taksit", banka_kasa_id=k1.id, tedarikci_id=t1.id)
        db.session.add(to1)

        # 5. GENEL İŞLETME GİDERLERİ
        # Kira, Personel, Elektrik gibi kalemler
        g1 = Gider(kategori="Kira", aciklama="Dükkan Ocak Ayı Kirası", tutar=15000.0, birim="TL", banka_kasa_id=k1.id)
        g2 = Gider(kategori="Personel", aciklama="Usta Maaşı - Ocak", tutar=25000.0, birim="TL", banka_kasa_id=k1.id)
        g3 = Gider(kategori="Enerji", aciklama="Elektrik Faturası", tutar=2450.0, birim="TL", banka_kasa_id=k2.id)
        db.session.add_all([g1, g2, g3])

        # 6. MÜŞTERİLER VE İŞLER (Önceki Örnekleri de Koruyoruz)
        m1 = Musteri(ad_soyad="Hakan Aydın", isyeri_adi="Aydın Mobilya", telefon="0532 000 00 01")
        db.session.add(m1)
        db.session.commit()

        is1 = IsKaydi(is_tanimi="Dış Cephe Kompozit Kaplama", toplam_bedel=65000.0, para_birimi="TL", 
                      maliyet=32000.0, musteri_id=m1.id, durum="Devam Ediyor")
        db.session.add(is1)
        
        # Müşteriden kapora alalım
        o1 = Odeme(tutar=20000.0, birim="TL", aciklama="İş başı kapora", banka_kasa_id=k1.id, musteri_id=m1.id)
        db.session.add(o1)
        
        db.session.commit()
        print("Tüm örnek veriler (Tedarikçi, Alım, Gider, Müşteri) başarıyla yüklendi!")

if __name__ == "__main__":
    veri_tohumla()