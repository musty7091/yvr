# scripts/fetch_tcmb_rates.py
import json
import datetime as dt
import xml.etree.ElementTree as ET
from urllib.request import urlopen, Request

TCMB_URL = "https://www.tcmb.gov.tr/kurlar/today.xml"

# İhtiyacına göre genişletebilirsin
WANTED = ["USD", "EUR", "GBP"]

def fetch_xml(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=30) as r:
        return r.read()

def parse_rates(xml_bytes: bytes) -> dict:
    root = ET.fromstring(xml_bytes)
    tarih = root.attrib.get("Tarih")  # ör: "18.02.2026"
    bulten_no = root.attrib.get("Bulten_No")

    rates = {"TRY": 1.0}
    for cur in root.findall("Currency"):
        code = cur.attrib.get("CurrencyCode")
        if code not in WANTED:
            continue

        # TCMB: BanknoteSelling genelde pratikte kullanılan kur
        val = (cur.findtext("BanknoteSelling") or "").strip()
        if not val:
            # yedek: ForexSelling
            val = (cur.findtext("ForexSelling") or "").strip()

        if val:
            rates[code] = float(val.replace(",", "."))

    payload = {
        "source": "TCMB",
        "tcmb": {"tarih": tarih, "bulten_no": bulten_no},
        "generated_at_utc": dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "rates": rates,
    }
    return payload

def main():
    xml_bytes = fetch_xml(TCMB_URL)
    payload = parse_rates(xml_bytes)

    out_path = "kurlar.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # Basit kontrol: en az TRY + 1 döviz
    if len(payload["rates"]) < 2:
        raise SystemExit("Kurlar yetersiz geldi (XML parse sorunu olabilir).")

if __name__ == "__main__":
    main()
