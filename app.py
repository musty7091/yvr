import os
from flask_wtf.csrf import CSRFProtect
from flask import Flask
from dotenv import load_dotenv
from models import db
from routes.musteri_isleri import musteri_bp
from routes.tedarikci_isleri import tedarikci_bp
from routes.genel_isler import genel_bp
from routes.gider_isleri import gider_bp

# .env yükle
load_dotenv()

def _env_bool(name: str, default: bool = False) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")

app = Flask(__name__)
csrf = CSRFProtect(app)


# --- GÜVENLİK ---
secret = os.getenv("SECRET_KEY")
if not secret:
    raise RuntimeError("SECRET_KEY .env içinde tanımlı olmalı (boş olamaz).")
app.secret_key = secret

# Cookie güvenlik ayarları (prod için önemli)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
# HTTPS kullanıyorsan prod’da True yap (lokalde False kalabilir)
app.config["SESSION_COOKIE_SECURE"] = _env_bool("SESSION_COOKIE_SECURE", False)

# --- VERİTABANI YOLU DÜZELTMESİ ---
basedir = os.path.abspath(os.path.dirname(__file__))
instance_path = os.path.join(basedir, "instance")

if not os.path.exists(instance_path):
    os.makedirs(instance_path)

db_path = os.path.join(instance_path, "yvr_veritabani.db")
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + db_path
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
# ----------------------------------

db.init_app(app)

# Blueprint Kayıtları
app.register_blueprint(genel_bp)
app.register_blueprint(musteri_bp, url_prefix="/musteri")
app.register_blueprint(tedarikci_bp, url_prefix="/ticari")
app.register_blueprint(gider_bp, url_prefix="/gider")

if __name__ == "__main__":
    debug = _env_bool("DEBUG", False)
    app.run(debug=debug, port=5000)
