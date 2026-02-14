from app import app
from models import db, Musteri, IsKaydi, Odeme, BankaKasa, Tedarikci, SatinAlma, Gider, TedarikciOdeme, Kullanici, Ayarlar
from datetime import datetime, timedelta
import random

def veri_tohumla():
    with app.app_context():
        # 1. Tabloları oluştur
        db.create_all()
        print("--- Tohumlama ve Test İşlemi Başladı ---")

        # 2. Kullanıcı Oluşturma
        admin = Kullanici.query.filter_by(kullanici_adi='admin').first()
        if not admin:
            yeni_admin = Kullanici(kullanici_adi='admin')
            yeni_admin.sifre_belirle('1234') 
            db.session.add(yeni_admin)
            db.session.commit()
            print("Admin kullanıcısı oluşturuldu.")

        # 3. Ayarlar
        if not Ayarlar.query.first():
            ayar = Ayarlar(ay_hedefi=100000.0)
            db.session.add(ayar)

        # 4. Kasalar
        if not BankaKasa.query.first():
            k1 = BankaKasa(ad="Ziraat Bankası", tur="Banka", hesap_no="TR01", baslangic_bakiye=10000.0)
            k2 = BankaKasa(ad="Dükkan Kasa", tur="Nakit", hesap_no="NAKİT", baslangic_bakiye=2500.0)
            db.session.add_all([k1, k2])
            db.session.commit()
            print("Kasalar oluşturuldu.")

        kasalar = BankaKasa.query.all()

        # 5. Tedarikçiler
        if not Tedarikci.query.first():
            t1 = Tedarikci(firma_adi="Öz Alüminyum A.Ş.", yetkili_kisi="Murat Bey", telefon="0212 555 10 20")
            t2 = Tedarikci(firma_adi="Pleksi Dünyası", yetkili_kisi="Selin Hanım", telefon="0212 444 30 40")
            db.session.add_all([t1, t2])
            db.session.commit()
            print("Tedarikçiler eklendi.")

        # 6. Müşteriler ve İşler
        if not Musteri.query.first():
            isimler = ["Ahmet Yılmaz", "Mehmet Demir", "Ayşe Kaya", "Fatma Çetin"]
            is_turleri = ["Tabela Yapımı", "Cephe Kaplama", "Dijital Baskı", "CNC Kesim"]
            
            for isim in isimler:
                yeni_musteri = Musteri(ad_soyad=isim, telefon="0500 000 00 00", isyeri_adi=isim + " Ltd.")
                db.session.add(yeni_musteri)
                db.session.commit()

                for _ in range(random.randint(1, 2)):
                    bedel = random.randint(5000, 15000)
                    # HATA DÜZELTİLDİ: Sütun isimleri models.py ile birebir eşlendi
                    yeni_is = IsKaydi(
                        is_tanimi=random.choice(is_turleri),
                        toplam_bedel=float(bedel),
                        para_birimi="TL",
                        maliyet=float(bedel * 0.4),
                        teslim_tarihi=(datetime.now() + timedelta(days=10)).strftime('%Y-%m-%d'),
                        vade_gun=random.randint(7, 30),
                        teslim_edildi_tarihi=None,
                        durum='Devam Ediyor',
                        musteri_id=yeni_musteri.id
                    )
                    db.session.add(yeni_is)
                    db.session.commit()

                    # Ödeme simülasyonu
                    if random.choice([True, False]):
                        odeme_tutari = yeni_is.toplam_bedel * 0.5
                        yeni_odeme = Odeme(
                            tutar=round(odeme_tutari, 2),
                            birim="TL",
                            aciklama="Kapora",
                            odeme_yontemi="Havale/EFT",
                            kur_degeri=1.0,
                            odeme_tarihi=datetime.now(),
                            banka_kasa_id=random.choice(kasalar).id,
                            musteri_id=yeni_musteri.id,
                            is_kaydi_id=yeni_is.id
                        )
                        db.session.add(yeni_odeme)

            print("Müşteriler, işler ve örnek ödemeler eklendi.")

        # 7. Giderler
        if Gider.query.count() < 3:
            gider_tipleri = ["Kira", "Elektrik", "Yemek"]
            for tip in gider_tipleri:
                db.session.add(Gider(
                    kategori=tip,
                    aciklama=tip + " ödemesi",
                    tutar=float(random.randint(500, 2000)),
                    birim="TL",
                    kur_degeri=1.0,
                    banka_kasa_id=random.choice(kasalar).id,
                    tarih=datetime.now()
                ))
            print("Giderler eklendi.")

        db.session.commit()
        print("\n--- İşlem Tamam! Tüm butonları test edebilirsin. ---")

if __name__ == "__main__":
    veri_tohumla()