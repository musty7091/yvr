from flask import Flask
from datetime import timedelta
from models import db
from utils import kurlari_sabitle

# Blueprintleri içeri alıyoruz
from routes.genel_isler import genel_bp
from routes.musteri_isleri import musteri_bp
from routes.tedarikci_isleri import tedarikci_bp
from routes.gider_isleri import gider_bp

app = Flask(__name__)
app.secret_key = 'yvr_ozel_sifre_123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///yvr_veritabani.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

# Veritabanını uygulamaya bağlıyoruz
db.init_app(app)

# Parçaları ana makineye bağlıyoruz
app.register_blueprint(genel_bp)
app.register_blueprint(musteri_bp)
app.register_blueprint(tedarikci_bp)
app.register_blueprint(gider_bp)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        kurlari_sabitle()
    app.run(debug=True, host='0.0.0.0')