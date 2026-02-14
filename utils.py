import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import pdfkit
import os
import platform
from flask import render_template, make_response
from urllib.parse import quote

# TEK KAYNAK: money/rate her zaman models.py (TR format + quantize standart)
from models import money, rate

# Başlangıç kurları - Sistem ayağa kalktığında ilk bu değerler kullanılır
GUNCEL_KURLAR = {"USD": 34.0, "EUR": 36.5, "GBP": 42.0, "tarih": "Henüz Güncellenmedi"}

def kurlari_sabitle():
    """Merkez Bankası üzerinden güncel kurları çeker ve sözlüğü günceller."""
    global GUNCEL_KURLAR
    try:
        response = requests.get("https://www.tcmb.gov.tr/kurlar/today.xml", timeout=5)
        tree = ET.fromstring(response.content)

        # XML içinden ilgili para birimlerini ayıklıyoruz (Decimal)
        usd_txt = tree.find(".//Currency[@Kod='USD']/BanknoteSelling").text
        eur_txt = tree.find(".//Currency[@Kod='EUR']/BanknoteSelling").text
        gbp_txt = tree.find(".//Currency[@Kod='GBP']/BanknoteSelling").text

        usd = rate(usd_txt)
        eur = rate(eur_txt)
        gbp = rate(gbp_txt)

        # Not: mevcut yapı bozulmasın diye GUNCEL_KURLAR içindeki sayıları aynı anahtarlarla güncelliyoruz.
        # value'lar Decimal olabilir; zaten tüm kullanım yerlerinde rate(...) ile normalize ediyorsun.
        GUNCEL_KURLAR.update({
            "USD": usd,
            "EUR": eur,
            "GBP": gbp,
            "tarih": datetime.now().strftime("%d.%m.%Y %H:%M")
        })
        return True
    except Exception as e:
        print(f"Kur güncelleme hatası: {e}")
        return False

def pdf_olustur(musteri, toplam_tl, toplam_usd):
    """Müşteri ekstresini PDF formatına dönüştürür."""
    logo_path = os.path.join(os.getcwd(), 'static', 'logo.png')

    # Decimal uyumlu yuvarlama (models.money ile)
    toplam_tl_d = money(toplam_tl)
    toplam_usd_d = money(toplam_usd)

    rendered = render_template(
        'pdf_sablonu.html',
        musteri=musteri,
        toplam_tl=float(toplam_tl_d),   # template sayısal bekliyorsa
        toplam_usd=float(toplam_usd_d), # template sayısal bekliyorsa
        bugun=datetime.now().strftime('%d.%m.%Y'),
        logo_url=logo_path
    )

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
