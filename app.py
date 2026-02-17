import os
from datetime import timedelta
from flask_wtf.csrf import CSRFProtect
from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix
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

def _env_int(name: str, default: int) -> int:
    v = os.getenv(name)
    if v is None or str(v).strip() == "":
        return default
    try:
        return int(str(v).strip())
    except Exception:
        return default


app = Flask(__name__)
csrf = CSRFProtect(app)

# Proxy/HTTPS arkasında (Cloudflare/Nginx vb.) doğru çalışması için.
# Varsayılan kapalı: sadece TRUST_PROXY=1 ise aktif olur.
if _env_bool("TRUST_PROXY", False):
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=_env_int("PROXY_FIX_X_FOR", 1),
        x_proto=_env_int("PROXY_FIX_X_PROTO", 1),
        x_host=_env_int("PROXY_FIX_X_HOST", 1),
        x_port=_env_int("PROXY_FIX_X_PORT", 1),
    )

# --- GÜVENLİK ---
secret = os.getenv("SECRET_KEY")
if not secret:
    raise RuntimeError("SECRET_KEY .env içinde tanımlı olmalı (boş olamaz).")
app.secret_key = secret

# Cookie güvenlik ayarları (prod için önemli)
app.config["SESSION_COOKIE_HTTPONLY"] = _env_bool("SESSION_COOKIE_HTTPONLY", True)
app.config["SESSION_COOKIE_SAMESITE"] = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
# HTTPS kullanıyorsan prod’da True olmalı (PythonAnywhere'de True)
app.config["SESSION_COOKIE_SECURE"] = _env_bool("SESSION_COOKIE_SECURE", True)

# Oturum süresi (saat)
session_hours = _env_int("SESSION_LIFETIME_HOURS", 12)
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=session_hours)

# --- VERİTABANI AYARLARI ---
basedir = os.path.abspath(os.path.dirname(__file__))
instance_path = os.path.join(basedir, "instance")

if not os.path.exists(instance_path):
    os.makedirs(instance_path)

db_path = os.path.join(instance_path, "yvr_veritabani.db")

# Öncelik: PostgreSQL (DATABASE_URL varsa)
database_url = os.getenv("DATABASE_URL")
if database_url:
    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
else:
    # Fallback: SQLite (lokal/test için)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + db_path

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ECHO"] = _env_bool("SQLALCHEMY_ECHO", False)

db.init_app(app)

# --- İLK ÇALIŞTIRMA: DB OLUŞTUR + MINIMUM KAYITLAR ---
from models import Kullanici, Ayarlar, BankaKasa, money

def bootstrap_db(app):
    """
    İlk çalıştırmada tabloları oluşturur ve minimum gerekli kayıtları (admin/ayarlar/kasa) ekler.
    Sadece AUTO_CREATE_DB=1 ise çalışır.
    """
    auto = _env_bool("AUTO_CREATE_DB", False)
    if not auto:
        return

    with app.app_context():
        # 1) Tablolar
        db.create_all()

        # 2) Admin kullanıcı (yoksa)
        admin_username = (os.getenv("ADMIN_USERNAME") or "admin").strip()
        admin_password = os.getenv("ADMIN_PASSWORD")

        if not admin_password:
            raise RuntimeError("AUTO_CREATE_DB=1 iken ADMIN_PASSWORD zorunlu (default şifre yok).")

        admin = Kullanici.query.filter_by(kullanici_adi=admin_username).first()
        if not admin:
            admin = Kullanici(kullanici_adi=admin_username)
            admin.sifre_belirle(admin_password)
            db.session.add(admin)

        # 3) Ayarlar (yoksa)
        if not Ayarlar.query.first():
            default_target = os.getenv("DEFAULT_MONTH_TARGET", "50000")
            db.session.add(Ayarlar(ay_hedefi=money(default_target)))

        # 4) Varsayılan kasalar (hiç yoksa)
        if BankaKasa.query.count() == 0:
            db.session.add(BankaKasa(ad="Dükkan Kasa", tur="Nakit", hesap_no="NAKIT", baslangic_bakiye=money("0")))
            db.session.add(BankaKasa(ad="Ziraat Bankası", tur="Banka", hesap_no="TR01", baslangic_bakiye=money("0")))

        db.session.commit()

bootstrap_db(app)
# -----------------------------------------------------

# Blueprint Kayıtları
app.register_blueprint(genel_bp)
app.register_blueprint(musteri_bp, url_prefix="/musteri")
app.register_blueprint(tedarikci_bp, url_prefix="/ticari")
app.register_blueprint(gider_bp, url_prefix="/gider")

if __name__ == "__main__":
    debug = _env_bool("DEBUG", False)
    # Prod’da debug False olmalı
    app.run(debug=debug, port=5000)
