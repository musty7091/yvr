from flask import Blueprint, render_template, request, redirect, url_for, session
from sqlalchemy import or_
from models import db, Tedarikci, SatinAlma, TedarikciOdeme, BankaKasa
from utils import GUNCEL_KURLAR

tedarikci_bp = Blueprint('tedarikci', __name__)

@tedarikci_bp.route('/ticari_borclar')
def ticari_borclar():
    if 'logged_in' not in session: return redirect(url_for('genel.index'))
    q = request.args.get('q')
    tedarikciler = Tedarikci.query.filter(Tedarikci.durum == 'Aktif', or_(Tedarikci.firma_adi.contains(q), Tedarikci.yetkili_kisi.contains(q))).all() if q else Tedarikci.query.filter_by(durum='Aktif').all()
    for t in tedarikciler:
        t.guncel_bakiye = sum(alim.tutar * GUNCEL_KURLAR.get(alim.para_birimi, 1.0) for alim in t.satin_almalar) - sum(o.tutar * o.kur_degeri for o in t.odenenler)
    tedarikciler.sort(key=lambda x: x.guncel_bakiye, reverse=True)
    return render_template('ticari_borclar.html', tedarikciler=tedarikciler, arama_var=bool(q), terim=q)

@tedarikci_bp.route('/tedarikci_ekle', methods=['POST'])
def tedarikci_ekle():
    db.session.add(Tedarikci(firma_adi=request.form.get('firma_adi'), yetkili_kisi=request.form.get('yetkili_kisi'), telefon=request.form.get('telefon'), adres=request.form.get('adres'), durum='Aktif'))
    db.session.commit()
    return redirect(url_for('tedarikci.ticari_borclar'))

@tedarikci_bp.route('/tedarikci/<int:id>')
def tedarikci_detay(id):
    if 'logged_in' not in session: return redirect(url_for('genel.index'))
    t = Tedarikci.query.get_or_404(id)
    # Kasaları ödeme modalında listelemek için çekiyoruz
    kasalar = BankaKasa.query.all()
    
    net_tl = sum(alim.tutar * GUNCEL_KURLAR.get(alim.para_birimi, 1.0) for alim in t.satin_almalar) - \
             sum(o.tutar * o.kur_degeri for o in t.odenenler)
             
    return render_template('tedarikci_detay.html', 
                           tedarikci=t, 
                           toplam_tl=round(net_tl, 2), 
                           toplam_usd=round(net_tl / GUNCEL_KURLAR.get('USD', 1.0), 2), 
                           kurlar=GUNCEL_KURLAR, 
                           kasalar=kasalar)

@tedarikci_bp.route('/tedarikci_duzenle/<int:id>', methods=['GET', 'POST'])
def tedarikci_duzenle(id):
    if 'logged_in' not in session: return redirect(url_for('genel.index'))
    tedarikci = Tedarikci.query.get_or_404(id)
    if request.method == 'POST':
        tedarikci.firma_adi, tedarikci.yetkili_kisi, tedarikci.telefon, tedarikci.adres = request.form.get('firma_adi'), request.form.get('yetkili_kisi'), request.form.get('telefon'), request.form.get('adres')
        db.session.commit()
        return redirect(url_for('tedarikci.ticari_borclar'))
    return render_template('tedarikci_duzenle.html', tedarikci=tedarikci)

@tedarikci_bp.route('/tedarikci_sil/<int:id>', methods=['POST'])
def tedarikci_sil(id):
    if 'logged_in' not in session: return redirect(url_for('genel.index'))
    t = Tedarikci.query.get_or_404(id)
    if t.satin_almalar or t.odenenler: t.durum = 'Pasif'
    else: db.session.delete(t)
    db.session.commit()
    return redirect(url_for('tedarikci.ticari_borclar'))

@tedarikci_bp.route('/malzeme_alim_ekle', methods=['POST'])
def malzeme_alim_ekle():
    from datetime import datetime
    t_id = int(request.form.get('tedarikci_id'))
    db.session.add(SatinAlma(malzeme_tanimi=request.form.get('malzeme_tanimi'), tutar=float(request.form.get('tutar') or 0), para_birimi=request.form.get('para_birimi'), fatura_no=request.form.get('fatura_no'), tarih=datetime.now(), tedarikci_id=t_id))
    db.session.commit()
    return redirect(url_for('tedarikci.tedarikci_detay', id=t_id))

@tedarikci_bp.route('/alim_sil/<int:id>', methods=['POST'])
def alim_sil(id):
    if 'logged_in' not in session: return redirect(url_for('genel.index'))
    kayit = SatinAlma.query.get_or_404(id)
    t_id = kayit.tedarikci_id
    db.session.delete(kayit)
    db.session.commit()
    return redirect(url_for('tedarikci.tedarikci_detay', id=t_id))


@tedarikci_bp.route('/tedarikci_odeme_yap', methods=['POST'])
def tedarikci_odeme_yap():
    t_id = int(request.form.get('tedarikci_id'))
    birim = request.form.get('birim')
    kasa_id = request.form.get('banka_kasa_id') # Formdan gelen seçili kasa ID
    
    yeni_odeme = TedarikciOdeme(
        tutar=float(request.form.get('tutar') or 0), 
        birim=birim, 
        aciklama=request.form.get('aciklama'), 
        kur_degeri=GUNCEL_KURLAR.get(birim, 1.0) if birim != 'TL' else 1.0, 
        banka_kasa_id=kasa_id, # Ödeme seçilen kasadan düşer
        tedarikci_id=t_id
    )
    db.session.add(yeni_odeme)
    db.session.commit()
    return redirect(url_for('tedarikci.tedarikci_detay', id=t_id))

@tedarikci_bp.route('/tedarikci_odeme_sil/<int:id>', methods=['POST'])
def tedarikci_odeme_sil(id):
    if 'logged_in' not in session: return redirect(url_for('genel.index'))
    kayit = TedarikciOdeme.query.get_or_404(id)
    t_id = kayit.tedarikci_id
    db.session.delete(kayit)
    db.session.commit()
    return redirect(url_for('tedarikci.tedarikci_detay', id=t_id))
