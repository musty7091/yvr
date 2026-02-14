import os
from flask import Flask
from dotenv import load_dotenv
from models import db
from routes.musteri_isleri import musteri_bp
from routes.tedarikci_isleri import tedarikci_bp
from routes.genel_isler import genel_bp
from routes.gider_isleri import gider_bp

# .env yükle
load_dotenv()

app = Flask(__name__)

# GÜVENLİK
app.secret_key = os.getenv('SECRET_KEY', 'cok_gizli_anahtar_123')

# --- VERİTABANI YOLU DÜZELTMESİ ---
# Mevcut klasörü bul ve 'instance' klasörünün tam yolunu oluştur
basedir = os.path.abspath(os.path.dirname(__file__))
instance_path = os.path.join(basedir, 'instance')

# Eğer 'instance' klasörü yoksa kod hata vermesin, otomatik oluştursun
if not os.path.exists(instance_path):
    os.makedirs(instance_path)

# Veritabanı yolunu tam (absolute) yol olarak ayarla
db_path = os.path.join(instance_path, 'yvr_veritabani.db')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# ----------------------------------

db.init_app(app)

# Blueprint Kayıtları
app.register_blueprint(genel_bp) # Ön ek yok (/, /login, /ayarlar)
app.register_blueprint(musteri_bp, url_prefix='/musteri') # /musteri/satislar, /musteri/liste
app.register_blueprint(tedarikci_bp, url_prefix='/ticari') # /ticari/borclar
app.register_blueprint(gider_bp, url_prefix='/gider') # /gider/giderler

if __name__ == '__main__':
    app.run(debug=True, port=5000)