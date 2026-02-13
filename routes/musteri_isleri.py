from flask import Blueprint, render_template, request, redirect, url_for, session
from sqlalchemy import or_
from models import db, Musteri, IsKaydi, Odeme, BankaKasa
from utils import GUNCEL_KURLAR, pdf_olustur
from datetime import datetime

musteri_bp = Blueprint('musteri', __name__)

@musteri_bp.route('/satislar')
def satislar():
    if 'logged_in' not in session: 
        return redirect(url_for('genel.index'))
    
    aktif_musteriler = Musteri.query.filter_by(durum='Aktif').all()
    toplam_alacak_tl = 0
    devam_eden_is_sayisi = 0
    
    for m in aktif_musteriler:
        for i in m.isler:
            if i.durum == 'Devam Ediyor': 
                devam_eden_is_sayisi += 1
            toplam_alacak_tl += (i.toplam_bedel * GUNCEL_KURLAR.get(i.para_birimi, 1.0))
        for o in m.odemeler:
            toplam_alacak_tl -= (o.tutar * o.kur_degeri)

    yaklasan_isler = [is_k for is_k in IsKaydi.query.filter(IsKaydi.teslim_tarihi != "", IsKaydi.durum == 'Devam Ediyor').order_by(IsKaydi.teslim_tarihi.asc()).all() if is_k.sahibi.durum == 'Aktif'][:5]
    
    simdi = datetime.now()
    bu_ayki_ciro = sum((o.tutar * o.kur_degeri) for o in Odeme.query.all() if o.odeme_tarihi.month == simdi.month and o.odeme_tarihi.year == simdi.year)

    return render_template('satislar.html', 
                           alacak=round(toplam_alacak_tl, 2), 
                           is_sayisi=devam_eden_is_sayisi, 
                           yaklasan_isler=yaklasan_isler, 
                           kurlar=GUNCEL_KURLAR, 
                           t_musteri=Musteri.query.count(), 
                           a_musteri=len(aktif_musteriler), 
                           biten_is=IsKaydi.query.filter_by(durum='Teslim Edildi').count(), 
                           ay_ciro=bu_ayki_ciro)

@musteri_bp.route('/musteriler')
def musteriler():
    if 'logged_in' not in session: 
        return redirect(url_for('genel.index'))
    q = request.args.get('q')
    if q:
        bulunanlar = Musteri.query.filter(Musteri.durum == 'Aktif', or_(Musteri.ad_soyad.contains(q), Musteri.isyeri_adi.contains(q))).all()
        return render_template('musteriler.html', musteriler=bulunanlar, arama_var=True, terim=q)
    return render_template('musteriler.html', musteriler=Musteri.query.filter_by(durum='Aktif').all(), arama_var=False)

@musteri_bp.route('/musteri_ekle', methods=['POST'])
def musteri_ekle():
    db.session.add(Musteri(
        ad_soyad=request.form.get('ad_soyad'), 
        telefon=request.form.get('telefon'), 
        isyeri_adi=request.form.get('isyeri_adi'), 
        isyeri_adresi=request.form.get('isyeri_adresi'), 
        durum='Aktif'
    ))
    db.session.commit()
    return redirect(request.referrer or url_for('musteri.musteriler'))

@musteri_bp.route('/musteri/<int:id>')
def musteri_detay(id):
    if 'logged_in' not in session: 
        return redirect(url_for('genel.index'))
    m = Musteri.query.get_or_404(id)
    kasalar = BankaKasa.query.filter_by(durum='Aktif').all()
    net_tl = sum(i.toplam_bedel * GUNCEL_KURLAR.get(i.para_birimi, 1.0) for i in m.isler) - sum(o.tutar * o.kur_degeri for o in m.odemeler)
    return render_template('musteri_detay.html', 
                           musteri=m, 
                           toplam_tl=round(net_tl, 2), 
                           toplam_usd=round(net_tl / GUNCEL_KURLAR.get('USD', 1.0), 2), 
                           kurlar=GUNCEL_KURLAR,
                           kasalar=kasalar)

@musteri_bp.route('/musteri_duzenle/<int:id>', methods=['GET', 'POST'])
def musteri_duzenle(id):
    if 'logged_in' not in session: 
        return redirect(url_for('genel.index'))
    musteri = Musteri.query.get_or_404(id)
    if request.method == 'POST':
        musteri.ad_soyad = request.form.get('ad_soyad')
        musteri.telefon = request.form.get('telefon')
        musteri.isyeri_adi = request.form.get('isyeri_adi')
        musteri.isyeri_adresi = request.form.get('isyeri_adresi')
        db.session.commit()
        return redirect(url_for('musteri.musteriler'))
    return render_template('musteri_duzenle.html', musteri=musteri)

@musteri_bp.route('/musteri_sil/<int:id>')
def musteri_sil(id):
    if 'logged_in' not in session: 
        return redirect(url_for('genel.index'))
    musteri = Musteri.query.get_or_404(id)
    if musteri.isler or musteri.odemeler: 
        musteri.durum = 'Pasif'
    else: 
        db.session.delete(musteri)
    db.session.commit()
    return redirect(url_for('musteri.musteriler'))

@musteri_bp.route('/pasif_musteriler')
def pasif_musteriler():
    if 'logged_in' not in session: 
        return redirect(url_for('genel.index'))
    return render_template('pasif_musteriler.html', musteriler=Musteri.query.filter_by(durum='Pasif').all())

@musteri_bp.route('/musteri_aktif_et/<int:id>')
def musteri_aktif_et(id):
    if 'logged_in' not in session: 
        return redirect(url_for('genel.index'))
    musteri = Musteri.query.get_or_404(id)
    musteri.durum = 'Aktif'
    db.session.commit()
    return redirect(url_for('musteri.musteriler'))

@musteri_bp.route('/is_ekle')
def is_ekle():
    if 'logged_in' not in session: 
        return redirect(url_for('genel.index'))
    secili_id = request.args.get('m_id')
    return render_template('is_ekle.html', musteriler=Musteri.query.filter_by(durum='Aktif').all(), secili_id=secili_id)

@musteri_bp.route('/is_kaydet', methods=['POST'])
def is_kaydet():
    m_id = int(request.form.get('musteri_id'))
    is_adi = request.form.get('is_tanimi')
    t_bedel = float(request.form.get('toplam_bedel') or 0)
    p_birimi = request.form.get('para_birimi')
    is_maliyeti = float(request.form.get('maliyet') or 0)
    
    yeni_is = IsKaydi(
        is_tanimi=is_adi, 
        toplam_bedel=round(t_bedel, 2), 
        para_birimi=p_birimi, 
        maliyet=round(is_maliyeti, 2),
        teslim_tarihi=request.form.get('teslim_tarihi'), 
        durum='Devam Ediyor', 
        musteri_id=m_id
    )
    db.session.add(yeni_is)
    
    a_kapora = float(request.form.get('alinan_kapora') or 0)
    if a_kapora > 0:
        k_birimi = request.form.get('kapora_birimi')
        # Kapora için varsayılan olarak ilk bulduğu kasayı veya nakit yöntemini atar
        db.session.add(Odeme(
            tutar=round(a_kapora, 2), 
            birim=k_birimi, 
            aciklama=f"Kapora ({is_adi})", 
            kur_degeri=GUNCEL_KURLAR.get(k_birimi, 1.0) if k_birimi != 'TL' else 1.0, 
            odeme_yontemi='Nakit',
            musteri_id=m_id
        ))
    db.session.commit()
    return redirect(url_for('musteri.satislar'))

@musteri_bp.route('/is_teslim_et/<int:id>')
def is_teslim_et(id):
    if 'logged_in' not in session: 
        return redirect(url_for('genel.index'))
    is_k = IsKaydi.query.get_or_404(id)
    is_k.durum = 'Teslim Edildi'
    db.session.commit()
    return redirect(url_for('musteri.musteri_detay', id=is_k.musteri_id))

@musteri_bp.route('/is_durum_geri_al/<int:id>')
def is_durum_geri_al(id):
    if 'logged_in' not in session: 
        return redirect(url_for('genel.index'))
    is_k = IsKaydi.query.get_or_404(id)
    is_k.durum = 'Devam Ediyor'
    db.session.commit()
    return redirect(url_for('musteri.musteri_detay', id=is_k.musteri_id))

@musteri_bp.route('/is_sil/<int:id>')
def is_sil(id):
    if 'logged_in' not in session: 
        return redirect(url_for('genel.index'))
    is_k = IsKaydi.query.get_or_404(id)
    m_id = is_k.musteri_id
    db.session.delete(is_k)
    db.session.commit()
    return redirect(url_for('musteri.musteri_detay', id=m_id))

@musteri_bp.route('/musteri_odeme_ekle/<int:m_id>', methods=['POST'])
def musteri_odeme_ekle(m_id):
    birim = request.form.get('birim')
    kur = GUNCEL_KURLAR.get(birim, 1.0) if birim != 'TL' else 1.0
    
    yeni_odeme = Odeme(
        tutar=round(float(request.form.get('tutar') or 0), 2), 
        birim=birim, 
        aciklama=request.form.get('aciklama'), 
        odeme_yontemi=request.form.get('odeme_yontemi'),
        banka_kasa_id=request.form.get('banka_kasa_id'),
        kur_degeri=kur, 
        musteri_id=m_id
    )
    db.session.add(yeni_odeme)
    db.session.commit()
    return redirect(url_for('musteri.musteri_detay', id=m_id))

@musteri_bp.route('/odeme_sil/<int:id>')
def odeme_sil(id):
    if 'logged_in' not in session: 
        return redirect(url_for('genel.index'))
    o = Odeme.query.get_or_404(id)
    m_id = o.musteri_id
    db.session.delete(o)
    db.session.commit()
    return redirect(url_for('musteri.musteri_detay', id=m_id))

@musteri_bp.route('/pdf_indir/<int:id>')
def pdf_indir(id):
    m = Musteri.query.get_or_404(id)
    net_tl = sum(i.toplam_bedel * GUNCEL_KURLAR.get(i.para_birimi, 1.0) for i in m.isler) - sum(o.tutar * o.kur_degeri for o in m.odemeler)
    return pdf_olustur(m, net_tl, net_tl / GUNCEL_KURLAR.get('USD', 1.0))