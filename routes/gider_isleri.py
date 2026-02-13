from flask import Blueprint, render_template, request, redirect, url_for, session
from models import db, Gider
from utils import GUNCEL_KURLAR

gider_bp = Blueprint('gider', __name__)

@gider_bp.route('/giderler')
def giderler():
    if 'logged_in' not in session: return redirect(url_for('genel.index'))
    gider_listesi = Gider.query.order_by(Gider.tarih.desc()).all()
    from datetime import datetime
    bu_ay = datetime.now()
    bu_ay_toplam = sum(g.tutar * g.kur_degeri for g in gider_listesi if g.tarih.month == bu_ay.month and g.tarih.year == bu_ay.year)
    return render_template('giderler.html', giderler=gider_listesi, bu_ay_toplam=bu_ay_toplam, kurlar=GUNCEL_KURLAR)

@gider_bp.route('/gider_ekle', methods=['POST'])
def gider_ekle():
    from datetime import datetime
    birim = request.form.get('birim')
    db.session.add(Gider(kategori=request.form.get('kategori'), aciklama=request.form.get('aciklama'), tutar=float(request.form.get('tutar') or 0), birim=birim, kur_degeri=GUNCEL_KURLAR.get(birim, 1.0) if birim != 'TL' else 1.0, tarih=datetime.now()))
    db.session.commit()
    return redirect(url_for('gider.giderler'))

@gider_bp.route('/gider_sil/<int:id>')
def gider_sil(id):
    if 'logged_in' not in session: return redirect(url_for('genel.index'))
    gider = Gider.query.get_or_404(id)
    db.session.delete(gider)
    db.session.commit()
    return redirect(url_for('gider.giderler'))