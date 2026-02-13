from app import app
from models import db, Musteri, IsKaydi, Odeme, BankaKasa, Tedarikci, SatinAlma, Gider, TedarikciOdeme, Kullanici
from datetime import datetime

def veri_tohumla():
    with app.app_context():
        # 1. Tabloları oluştur
        db.create_all()

        # 2. ÖNCE KULLANICIYI OLUŞTUR (Giriş yapabilmen için en kritiği bu)
        admin = Kullanici.query.filter_by(kullanici_adi='admin').first()
        if not admin:
            yeni_admin = Kullanici(kullanici_adi='admin')
            yeni_admin.sifre_belirle('1234') 
            db.session.add(yeni_admin)
            db.session.commit()
            print("Admin kullanıcısı başarıyla oluşturuldu!")
        else:
            print("Admin kullanıcısı zaten mevcut.")

        # 3. KASALARI KONTROL EDEREK EKLE
        if not BankaKasa.query.first():
            k1 = BankaKasa(ad="Ziraat Bankası Ticari", tur="Banka", durum="Aktif")
            k2 = BankaKasa(ad="Dükkan Nakit Kasa", tur="Kasa", durum="Aktif")
            db.session.add_all([k1, k2])
            db.session.commit()
            print("Kasalar oluşturuldu.")

        # 4. TEDARİKÇİLERİ KONTROL EDEREK EKLE
        if not Tedarikci.query.first():
            t1 = Tedarikci(firma_adi="Öz Alüminyum A.Ş.", yetkili_kisi="Murat Bey", telefon="0212 555 10 20", durum="Aktif")
            t2 = Tedarikci(firma_adi="Pleksi Dünyası", yetkili_kisi="Selin Hanım", telefon="0212 444 30 40", durum="Aktif")
            db.session.add_all([t1, t2])
            db.session.commit()
            print("Tedarikçiler eklendi.")

        # 5. MÜŞTERİ VE İŞ KAYITLARI (Sadece tablo boşsa ekle)
        if not Musteri.query.first():
            m1 = Musteri(ad_soyad="Hakan Aydın", isyeri_adi="Aydın Mobilya", telefon="0532 000 00 01")
            db.session.add(m1)
            db.session.commit()

            # Müşteri oluştuktan sonra ona bağlı işi ekle
            is1 = IsKaydi(is_tanimi="Dış Cephe Kompozit Kaplama", toplam_bedel=65000.0, para_birimi="TL", 
                          maliyet=32000.0, musteri_id=m1.id, durum="Devam Ediyor")
            db.session.add(is1)
            db.session.commit()
            print("Örnek müşteri ve iş kaydı eklendi.")

        print("Tohumlama işlemi başarıyla tamamlandı!")

if __name__ == "__main__":
    veri_tohumla()