import os
from flask import Flask
from dotenv import load_dotenv # Yeni eklendi
from models import db
from routes.musteri_isleri import musteri_bp
from routes.tedarikci_isleri import tedarikci_bp
from routes.genel_isler import genel_bp
from routes.gider_isleri import gider_bp

# .env dosyasındaki değişkenleri yükle
load_dotenv()

app = Flask(__name__)

# GÜVENLİK: Secret key artık dışarıdan alınıyor, yoksa varsayılan atanıyor
app.secret_key = os.getenv('SECRET_KEY', 'cok_gizli_varsayilan_anahtar')

# VERİTABANI: Yol artık dışarıdan yönetilebilir
app.config['SQLALCHEMY_DATABASE_NAME'] = os.getenv('DATABASE_URL', 'sqlite:///instance/yvr_veritabani.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# Blueprint Kayıtları
app.register_blueprint(genel_bp)
app.register_blueprint(musteri_bp, url_prefix='/musteriler')
app.register_blueprint(tedarikci_bp, url_prefix='/tedarikciler')
app.register_blueprint(gider_bp, url_prefix='/giderler')

if __name__ == '__main__':
    # DEBUG modu artık .env dosyasından kontrol ediliyor
    debug_mode = os.getenv('DEBUG', 'False') == 'True'
    app.run(debug=debug_mode)