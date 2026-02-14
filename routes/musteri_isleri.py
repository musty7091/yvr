from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from sqlalchemy import or_
from models import db, Musteri, IsKaydi, Odeme, BankaKasa
from datetime import datetime, timedelta
from decimal import Decimal

# ImportError fix: money/rate utils.py içinde yoksa models.py'den al
try:
    from utils import GUNCEL_KURLAR, pdf_olustur, money, rate
except ImportError:
    from utils import GUNCEL_KURLAR, pdf_olustur
    from models import money, rate

musteri_bp = Blueprint('musteri', __name__)

@musteri_bp.route('/satislar')
def satislar():
    if 'logged_in' not in session:
        return redirect(url_for('genel.index'))

    aktif_musteriler = Musteri.query.filter_by(durum='Aktif').all()

    toplam_alacak_tl = Decimal("0")
    devam_eden_is_sayisi = 0

    for m in aktif_musteriler:
        for i in m.isler:
            if i.durum == 'Devam Ediyor':
                devam_eden_is_sayisi += 1

            kur = rate(GUNCEL_KURLAR.get(i.para_birimi, 1))
            toplam_alacak_tl += (i.toplam_bedel * kur)

        for o in m.odemeler:
            toplam_alacak_tl -= (o.tutar * o.kur_degeri)

    yaklasan_isler = (
        IsKaydi.query
        .filter(IsKaydi.durum == 'Devam Ediyor')
        .order_by(IsKaydi.teslim_tarihi.asc())
        .limit(5)
        .all()
    )

    simdi = datetime.now()
    bu_ayki_ciro = Decimal("0")
    for o in Odeme.query.all():
        if o.odeme_tarihi and o.odeme_tarihi.month == simdi.month and o.odeme_tarihi.year == simdi.year:
            bu_ayki_ciro += (o.tutar * o.kur_degeri)

    return render_template(
        'satislar.html',
        alacak=str(money(toplam_alacak_tl)),
        is_sayisi=devam_eden_is_sayisi,
        yaklasan_isler=yaklasan_isler,
        kurlar=GUNCEL_KURLAR,
        t_musteri=Musteri.query.count(),
        a_musteri=len(aktif_musteriler),
        biten_is=IsKaydi.query.filter_by(durum='Teslim Edildi').count(),
        ay_ciro=str(money(bu_ayki_ciro))
    )

@musteri_bp.route('/vadesi_yaklasanlar')
def vadesi_yaklasanlar():
    if 'logged_in' not in session:
        return redirect(url_for('genel.index'))

    teslim_edilenler = IsKaydi.query.filter_by(durum='Teslim Edildi').all()
    yaklasanlar = []
    simdi = datetime.now()

    for is_k in teslim_edilenler:
        if is_k.teslim_edildi_tarihi and is_k.vade_gun > 0:
            vade_tarihi = is_k.teslim_edildi_tarihi + timedelta(days=is_k.vade_gun)
            kalan_gun = (vade_tarihi - simdi).days

            yaklasanlar.append({
                'is': is_k,
                'vade_tarihi': vade_tarihi,
                'kalan_gun': kalan_gun
            })

    yaklasanlar.sort(key=lambda x: x['vade_tarihi'])
    return render_template('vadesi_yaklasanlar.html', yaklasanlar=yaklasanlar)

@musteri_bp.route('/musteriler')
def musteriler():
    if 'logged_in' not in session:
        return redirect(url_for('genel.index'))

    q = request.args.get('q')
    if q:
        bulunanlar = Musteri.query.filter(
            Musteri.durum == 'Aktif',
            or_(Musteri.ad_soyad.contains(q), Musteri.isyeri_adi.contains(q))
        ).all()
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
    kasalar = BankaKasa.query.all()

    net_tl = Decimal("0")
    for i in m.isler:
        kur = rate(GUNCEL_KURLAR.get(i.para_birimi, 1))
        net_tl += (i.toplam_bedel * kur)
    for o in m.odemeler:
        net_tl -= (o.tutar * o.kur_degeri)

    usd_kur = rate(GUNCEL_KURLAR.get('USD', 1))

    return render_template(
        'musteri_detay.html',
        musteri=m,
        toplam_tl=str(money(net_tl)),
        toplam_usd=str(money(net_tl / usd_kur)) if usd_kur != 0 else "0.00",
        kurlar=GUNCEL_KURLAR,
        kasalar=kasalar
    )

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

@musteri_bp.route('/musteri_sil/<int:id>', methods=['POST'])
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
    kasalar = BankaKasa.query.all()

    return render_template(
        'is_ekle.html',
        musteriler=Musteri.query.filter_by(durum='Aktif').all(),
        secili_id=secili_id,
        kasalar=kasalar
    )

@musteri_bp.route('/is_kaydet', methods=['POST'])
def is_kaydet():
    m_id = int(request.form.get('musteri_id'))
    is_adi = request.form.get('is_tanimi')

    t_bedel = money(request.form.get('toplam_bedel'))
    p_birimi = request.form.get('para_birimi') or 'TL'

    v_gun = int(request.form.get('vade_gun') or 0)
    kasa_id = request.form.get('banka_kasa_id')

    yeni_is = IsKaydi(
        is_tanimi=is_adi,
        toplam_bedel=t_bedel,
        para_birimi=p_birimi,
        maliyet=money("0"),
        vade_gun=v_gun,
        teslim_tarihi=request.form.get('teslim_tarihi'),
        durum='Devam Ediyor',
        musteri_id=m_id
    )
    db.session.add(yeni_is)
    db.session.commit()

    a_kapora = money(request.form.get('alinan_kapora'))
    if a_kapora > 0:
        k_birimi = request.form.get('kapora_birimi') or 'TL'
        kapora_kur = rate(GUNCEL_KURLAR.get(k_birimi, 1)) if k_birimi != 'TL' else rate(1)

        db.session.add(Odeme(
            tutar=a_kapora,
            birim=k_birimi,
            aciklama=f"Kapora ({is_adi})",
            kur_degeri=kapora_kur,
            odeme_yontemi='Nakit',
            banka_kasa_id=kasa_id,
            is_kaydi_id=yeni_is.id,
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
    is_k.teslim_edildi_tarihi = datetime.now()
    db.session.commit()
    return redirect(request.referrer or url_for('musteri.musteri_detay', id=is_k.musteri_id))

@musteri_bp.route('/is_durum_geri_al/<int:id>')
def is_durum_geri_al(id):
    if 'logged_in' not in session:
        return redirect(url_for('genel.index'))

    is_k = IsKaydi.query.get_or_404(id)
    is_k.durum = 'Devam Ediyor'
    is_k.teslim_edildi_tarihi = None
    db.session.commit()
    return redirect(url_for('musteri.musteri_detay', id=is_k.musteri_id))

@musteri_bp.route('/is_sil/<int:id>', methods=['POST'])
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
    if m_id == 0:
        m_id = int(request.form.get('musteri_id_hizli'))

    birim = request.form.get('birim') or 'TL'
    kur = rate(GUNCEL_KURLAR.get(birim, 1)) if birim != 'TL' else rate(1)

    is_id_raw = request.form.get('is_id')
    is_id = int(is_id_raw) if (is_id_raw and str(is_id_raw).isdigit()) else None

    yeni_odeme = Odeme(
        tutar=money(request.form.get('tutar')),
        birim=birim,
        aciklama=request.form.get('aciklama'),
        odeme_yontemi=request.form.get('odeme_yontemi') or 'Havale/EFT',
        banka_kasa_id=request.form.get('banka_kasa_id'),
        kur_degeri=kur,
        is_kaydi_id=is_id,
        musteri_id=m_id
    )
    db.session.add(yeni_odeme)
    db.session.commit()

    flash('Tahsilat kaydedildi.', 'success')
    return redirect(request.referrer or url_for('musteri.musteri_detay', id=m_id))

@musteri_bp.route('/odeme_sil/<int:id>', methods=['POST'])
def odeme_sil(id):
    if 'logged_in' not in session:
        return redirect(url_for('genel.index'))

    o = Odeme.query.get_or_404(id)
    m_id = o.musteri_id
    db.session.delete(o)
    db.session.commit()

    flash('Tahsilat silindi.', 'warning')
    return redirect(url_for('musteri.musteri_detay', id=m_id))

@musteri_bp.route('/pdf_indir/<int:id>')
def pdf_indir(id):
    m = Musteri.query.get_or_404(id)

    net_tl = Decimal("0")
    for i in m.isler:
        kur = rate(GUNCEL_KURLAR.get(i.para_birimi, 1))
        net_tl += (i.toplam_bedel * kur)
    for o in m.odemeler:
        net_tl -= (o.tutar * o.kur_degeri)

    usd_kur = rate(GUNCEL_KURLAR.get('USD', 1))
    net_usd = (net_tl / usd_kur) if usd_kur != 0 else Decimal("0")

    return pdf_olustur(m, money(net_tl), money(net_usd))
