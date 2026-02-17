import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import pdfkit
import os
import platform
from flask import render_template, make_response, current_app
from urllib.parse import quote

# TEK KAYNAK: money/rate her zaman models.py (TR format + quantize standart)
from models import money, rate

# Başlangıç kurları - Sistem ayağa kalktığında ilk bu değerler kullanılır
# Not: burada Decimal/float karışabilir; zaten kullanım yerlerinde rate(...) ile normalize ediliyor.
GUNCEL_KURLAR = {"USD": 34.0, "EUR": 36.5, "GBP": 42.0, "tarih": "Henüz Güncellenmedi"}


def kurlari_sabitle():
    """Merkez Bankası üzerinden güncel kurları çeker ve sözlüğü günceller."""
    global GUNCEL_KURLAR
    try:
        response = requests.get("https://www.tcmb.gov.tr/kurlar/today.xml", timeout=8)
        response.raise_for_status()
        tree = ET.fromstring(response.content)

        # XML içinden ilgili para birimlerini ayıklıyoruz
        usd_node = tree.find(".//Currency[@Kod='USD']/BanknoteSelling")
        eur_node = tree.find(".//Currency[@Kod='EUR']/BanknoteSelling")
        gbp_node = tree.find(".//Currency[@Kod='GBP']/BanknoteSelling")

        # Eğer XML beklenmedik gelirse (boş node) crash olmasın
        usd_txt = (usd_node.text if usd_node is not None else "") or ""
        eur_txt = (eur_node.text if eur_node is not None else "") or ""
        gbp_txt = (gbp_node.text if gbp_node is not None else "") or ""

        # Decimal standardına çevir
        usd = rate(usd_txt) if usd_txt.strip() else rate(GUNCEL_KURLAR.get("USD", 34.0))
        eur = rate(eur_txt) if eur_txt.strip() else rate(GUNCEL_KURLAR.get("EUR", 36.5))
        gbp = rate(gbp_txt) if gbp_txt.strip() else rate(GUNCEL_KURLAR.get("GBP", 42.0))

        # Mevcut yapı bozulmasın diye aynı anahtarlarla güncelliyoruz.
        GUNCEL_KURLAR.update({
            "USD": usd,
            "EUR": eur,
            "GBP": gbp,
            "tarih": datetime.now().strftime("%d.%m.%Y %H:%M")
        })
        return True

    except Exception as e:
        # Prod’da print yerine log görmek daha sağlıklı; ama basit tutuyoruz
        print(f"Kur güncelleme hatası: {e}")
        return False


def _wkhtmltopdf_path():
    """
    wkhtmltopdf yolunu bulmaya çalışır.
    - .env ile WKHTMLTOPDF_PATH verilmişse onu kullanır.
    - Windows/Linux varsayılanlarını dener.
    - Bulamazsa None döner.
    """
    # 1) Env/Config ile override
    env_path = os.getenv("WKHTMLTOPDF_PATH")
    if env_path and os.path.exists(env_path):
        return env_path

    # 2) Flask config ile override (varsa)
    try:
        cfg_path = current_app.config.get("WKHTMLTOPDF_PATH")
        if cfg_path and os.path.exists(cfg_path):
            return cfg_path
    except Exception:
        pass

    # 3) OS default denemeleri
    if platform.system() == "Windows":
        candidates = [
            r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe",
            r"C:\Program Files (x86)\wkhtmltopdf\bin\wkhtmltopdf.exe",
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        return None

    # Linux/Unix
    for c in ("/usr/bin/wkhtmltopdf", "/usr/local/bin/wkhtmltopdf"):
        if os.path.exists(c):
            return c
    return None


def pdf_olustur(musteri, toplam_tl, toplam_usd):
    """Müşteri ekstresini PDF formatına dönüştürür."""
    logo_path = os.path.join(os.getcwd(), "static", "logo.png")

    # Decimal uyumlu yuvarlama (models.money ile)
    toplam_tl_d = money(toplam_tl)
    toplam_usd_d = money(toplam_usd)

    rendered = render_template(
        "pdf_sablonu.html",
        musteri=musteri,
        toplam_tl=float(toplam_tl_d),     # template sayısal bekliyorsa
        toplam_usd=float(toplam_usd_d),   # template sayısal bekliyorsa
        bugun=datetime.now().strftime("%d.%m.%Y"),
        logo_url=logo_path
    )

    wk_path = _wkhtmltopdf_path()
    if not wk_path:
        # Kullanıcıya anlaşılır hata (sunucuda wkhtmltopdf yoksa en sık problem bu)
        raise RuntimeError(
            "PDF oluşturma için wkhtmltopdf bulunamadı. "
            "Sunucuya wkhtmltopdf kurun veya .env içine WKHTMLTOPDF_PATH ekleyin."
        )

    config = pdfkit.configuration(wkhtmltopdf=wk_path)

    # Local dosya erişimi logoyu/sabit dosyaları alabilsin diye gerekli
    options = {
        "encoding": "UTF-8",
        "quiet": "",
        "enable-local-file-access": None
    }

    pdf = pdfkit.from_string(rendered, False, configuration=config, options=options)

    response = make_response(pdf)
    response.headers["Content-Type"] = "application/pdf"

    filename = f"{musteri.ad_soyad}_ekstre.pdf"
    safe_filename = quote(filename)
    response.headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{safe_filename}"
    return response
