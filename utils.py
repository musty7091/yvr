import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import pdfkit
import os
import platform
from flask import render_template, make_response
from urllib.parse import quote

# Başlangıç kurları
GUNCEL_KURLAR = {"USD": 34.0, "EUR": 36.5, "GBP": 42.0, "tarih": "Henüz Güncellenmedi"}

def kurlari_sabitle():
    """Merkez Bankası üzerinden güncel kurları çeker."""
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

def pdf_olustur(musteri, toplam_tl, toplam_usd):
    """Müşteri ekstresini PDF formatına dönüştürür."""
    logo_path = os.path.join(os.getcwd(), 'static', 'logo.png')
    
    rendered = render_template('pdf_sablonu.html', 
                               musteri=musteri, 
                               toplam_tl=round(toplam_tl, 2), 
                               toplam_usd=round(toplam_usd, 2),
                               bugun=datetime.now().strftime('%d.%m.%Y'),
                               logo_url=logo_path)

    # İşletim sistemine göre wkhtmltopdf yolunu ayarla
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