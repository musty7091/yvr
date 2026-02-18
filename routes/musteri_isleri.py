from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from sqlalchemy import or_, func, extract
from models import db, Musteri, IsKaydi, Odeme, BankaKasa, money, rate, normalize_currency
from utils import GUNCEL_KURLAR, pdf_olustur
from datetime import datetime, timedelta
from decimal import Decimal

musteri_bp = Blueprint('musteri', __name__)


def _kurlar_try_guvenli():
    k = dict(GUNCEL_KURLAR)
    k.setdefault("TRY", 1)
    return k


def _login_gerekli():
    return bool(session.get("logged_in"))


def _safe_int(v, default=0):
    try:
        return int(v)
    except Exception:
        return default


def _safe_decimal_one(v):
    try:
        if v is None:
            return Decimal("1")
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v))
    except Exception:
        return Decimal("1")


@musteri_bp.route('/satislar')
def satislar():
    if not _login_gerekli():
        return redirect(url_for('genel.index'))

    kurlar = _kurlar_try_guvenli()

    aktif_musteriler = Musteri.query.filter_by(durum='Aktif').all()

    toplam_alacak_try = Decimal("0")
    devam_eden_is_sayisi = 0

    for m in aktif_musteriler:
        for i in m.isler:
            if i.durum == 'Devam Ediyor':
                devam_eden_is_sayisi += 1

            pb = normalize_currency(i.para_birimi)
            kur = rate(kurlar.get(pb, 1)) if pb != "TRY" else rate(1)
            toplam_alacak_try += (i.toplam_bedel * kur)

        for o in m.odemeler:
            kur_d = _safe_decimal_one(getattr(o, "kur_degeri", None))
            toplam_alacak_try -= (o.tutar * kur_d)

    yaklasan_isler = (
        IsKaydi.query
        .filter(IsKaydi.durum == 'Devam Ediyor')
        .order_by(IsKaydi.teslim_tarihi.asc())
        .limit(5)
        .all()
    )

    # Bu ayki ciroyu SQL ile hesapla (performans)
    simdi = datetime.now()
    bu_ayki_ciro = db.session.query(
        func.coalesce(func.sum(Odeme.tutar * func.coalesce(Odeme.kur_degeri, Decimal("1"))), Decimal("0"))
    ).filter(
        extract('month', Odeme.odeme_tarihi) == simdi.month,
        extract('year', Odeme.odeme_tarihi) == simdi.year
    ).scalar()
    bu_ayki_ciro = money(bu_ayki_ciro)

    return render_template(
        'satislar.html',
        alacak=str(money(toplam_alacak_try)),
        is_sayisi=devam_eden_is_sayisi,
        yaklasan_isler=yaklasan_isler,
        kurlar=kurlar,
        t_musteri=Musteri.query.count(),
        a_musteri=len(aktif_musteriler),
        biten_is=IsKaydi.query.filter_by(durum='Teslim Edildi').count(),
        ay_ciro=str(bu_ayki_ciro)
    )


@musteri_bp.route('/vadesi_yaklasanlar')
def vadesi_yaklasanlar():
    if not _login_gerekli():
        return redirect(url_for('genel.index'))

    teslim_edilenler = IsKaydi.query.filter_by(durum='Teslim Edildi').all()
    yaklasanlar = []
    simdi = datetime.now()

    for is_k in teslim_edilenler:
        if is_k.teslim_edildi_tarihi and (is_k.vade_gun or 0) > 0:
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
    if not _login_gerekli():
        return redirect(url_for('genel.index'))

    q = (request.args.get('q') or '').strip()
    if q:
        bulunanlar = Musteri.query.filter(
            Musteri.durum == 'Aktif',
            or_(Musteri.ad_soyad.contains(q), Musteri.isyeri_adi.contains(q))
        ).all()
        return render_template('musteriler.html', musteriler=bulunanlar, arama_var=True, terim=q)

    return render_template('musteriler.html', musteriler=Musteri.query.filter_by(durum='Aktif').all(), arama_var=False)


@musteri_bp.route('/musteri_ekle', methods=['POST'])
def musteri_ekle():
    if not _login_gerekli():
        return redirect(url_for('genel.index'))

    ad_soyad = (request.form.get('ad_soyad') or '').strip()
    if not ad_soyad:
        flash('Müşteri adı boş olamaz.', 'danger')
        return redirect(request.referrer or url_for('musteri.musteriler'))

    db.session.add(Musteri(
        ad_soyad=ad_soyad,
        telefon=(request.form.get('telefon') or '').strip(),
        isyeri_adi=(request.form.get('isyeri_adi') or '').strip(),
        isyeri_adresi=(request.form.get('isyeri_adresi') or '').strip(),
        durum='Aktif'
    ))
    db.session.commit()
    return redirect(request.referrer or url_for('musteri.musteriler'))


@musteri_bp.route('/musteri/<int:id>')
def musteri_detay(id):
    if not _login_gerekli():
        return redirect(url_for('genel.index'))

    kurlar = _kurlar_try_guvenli()

    m = Musteri.query.get_or_404(id)
    kasalar = BankaKasa.query.all()

    net_try = Decimal("0")
    for i in m.isler:
        pb = normalize_currency(i.para_birimi)
        kur = rate(kurlar.get(pb, 1)) if pb != "TRY" else rate(1)
        net_try += (i.toplam_bedel * kur)
    for o in m.odemeler:
        kur_d = _safe_decimal_one(getattr(o, "kur_degeri", None))
        net_try -= (o.tutar * kur_d)

    usd_kur = rate(kurlar.get('USD', 1))

    return render_template(
        'musteri_detay.html',
        musteri=m,
        toplam_tl=str(money(net_try)),  # template uyumu için aynı alan adı
        toplam_usd=str(money(net_try / usd_kur)) if usd_kur != 0 else "0.00",
        kurlar=kurlar,
        kasalar=kasalar
    )


@musteri_bp.route('/musteri_duzenle/<int:id>', methods=['GET', 'POST'])
def musteri_duzenle(id):
    if not _login_gerekli():
        return redirect(url_for('genel.index'))

    musteri = Musteri.query.get_or_404(id)
    if request.method == 'POST':
        ad_soyad = (request.form.get('ad_soyad') or '').strip()
        if not ad_soyad:
            flash('Müşteri adı boş olamaz.', 'danger')
            return redirect(url_for('musteri.musteri_duzenle', id=id))

        musteri.ad_soyad = ad_soyad
        musteri.telefon = (request.form.get('telefon') or '').strip()
        musteri.isyeri_adi = (request.form.get('isyeri_adi') or '').strip()
        musteri.isyeri_adresi = (request.form.get('isyeri_adresi') or '').strip()
        db.session.commit()
        return redirect(url_for('musteri.musteriler'))

    return render_template('musteri_duzenle.html', musteri=musteri)


@musteri_bp.route('/musteri_sil/<int:id>', methods=['POST'])
def musteri_sil(id):
    if not _login_gerekli():
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
    if not _login_gerekli():
        return redirect(url_for('genel.index'))
    return render_template('pasif_musteriler.html', musteriler=Musteri.query.filter_by(durum='Pasif').all())


@musteri_bp.route('/musteri_aktif_et/<int:id>')
def musteri_aktif_et(id):
    if not _login_gerekli():
        return redirect(url_for('genel.index'))

    musteri = Musteri.query.get_or_404(id)
    musteri.durum = 'Aktif'
    db.session.commit()
    return redirect(url_for('musteri.musteriler'))


@musteri_bp.route('/is_ekle')
def is_ekle():
    if not _login_gerekli():
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
    if not _login_gerekli():
        return redirect(url_for('genel.index'))

    kurlar = _kurlar_try_guvenli()

    m_id = _safe_int(request.form.get('musteri_id'), 0)
    if not m_id:
        flash('Müşteri seçimi hatalı.', 'danger')
        return redirect(request.referrer or url_for('musteri.is_ekle'))

    is_adi = (request.form.get('is_tanimi') or '').strip()
    if not is_adi:
        flash('İş tanımı boş olamaz.', 'danger')
        return redirect(request.referrer or url_for('musteri.is_ekle'))

    t_bedel = money(request.form.get('toplam_bedel'))
    if t_bedel < 0:
        flash('Toplam bedel negatif olamaz.', 'danger')
        return redirect(request.referrer or url_for('musteri.is_ekle'))

    p_birimi = normalize_currency(request.form.get('para_birimi') or 'TRY')

    v_gun = _safe_int(request.form.get('vade_gun') or 0, 0)
    if v_gun < 0:
        v_gun = 0

    # banka_kasa_id formdan string gelebilir -> int/None
    kasa_id_raw = request.form.get('banka_kasa_id')
    kasa_id = _safe_int(kasa_id_raw, 0) if (kasa_id_raw and str(kasa_id_raw).isdigit()) else None

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
    if a_kapora < 0:
        a_kapora = money("0")

    if a_kapora > 0:
        k_birimi = normalize_currency(request.form.get('kapora_birimi') or 'TRY')
        kapora_kur = rate(kurlar.get(k_birimi, 1)) if k_birimi != 'TRY' else rate(1)

        # 1) Odeme kaydı
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

        # 2) Kasa bakiyesi artır (TRY karşılığı)
        if kasa_id:
            kasa = BankaKasa.query.get(kasa_id)
            if kasa:
                try:
                    try_tutar = money(a_kapora * (kapora_kur or Decimal("1")))
                except Exception:
                    try_tutar = money("0")

                try:
                    mevcut_bakiye = money(getattr(kasa, "bakiye", Decimal("0")) or Decimal("0"))
                except Exception:
                    mevcut_bakiye = money("0")

                kasa.bakiye = money(mevcut_bakiye + try_tutar)

    db.session.commit()
    return redirect(url_for('musteri.satislar'))


@musteri_bp.route('/is_teslim_et/<int:id>')
def is_teslim_et(id):
    if not _login_gerekli():
        return redirect(url_for('genel.index'))

    is_k = IsKaydi.query.get_or_404(id)
    is_k.durum = 'Teslim Edildi'
    is_k.teslim_edildi_tarihi = datetime.now()
    db.session.commit()
    return redirect(request.referrer or url_for('musteri.musteri_detay', id=is_k.musteri_id))


@musteri_bp.route('/is_durum_geri_al/<int:id>')
def is_durum_geri_al(id):
    if not _login_gerekli():
        return redirect(url_for('genel.index'))

    is_k = IsKaydi.query.get_or_404(id)
    is_k.durum = 'Devam Ediyor'
    is_k.teslim_edildi_tarihi = None
    db.session.commit()
    return redirect(url_for('musteri.musteri_detay', id=is_k.musteri_id))


@musteri_bp.route('/is_sil/<int:id>', methods=['POST'])
def is_sil(id):
    if not _login_gerekli():
        return redirect(url_for('genel.index'))

    is_k = IsKaydi.query.get_or_404(id)
    m_id = is_k.musteri_id
    db.session.delete(is_k)
    db.session.commit()
    return redirect(url_for('musteri.musteri_detay', id=m_id))


@musteri_bp.route('/musteri_odeme_ekle/<int:m_id>', methods=['POST'])
def musteri_odeme_ekle(m_id):
    if not _login_gerekli():
        return redirect(url_for('genel.index'))

    kurlar = _kurlar_try_guvenli()

    if m_id == 0:
        m_id = _safe_int(request.form.get('musteri_id_hizli'), 0)
        if not m_id:
            flash('Müşteri seçimi hatalı.', 'danger')
            return redirect(request.referrer or url_for('musteri.satislar'))

    birim = normalize_currency(request.form.get('birim') or 'TRY')
    kur = rate(kurlar.get(birim, 1)) if birim != 'TRY' else rate(1)

    is_id_raw = request.form.get('is_id')
    is_id = _safe_int(is_id_raw, 0) if (is_id_raw and str(is_id_raw).isdigit()) else None

    # banka_kasa_id formdan string gelebilir -> int/None
    kasa_id_raw = request.form.get('banka_kasa_id')
    kasa_id = _safe_int(kasa_id_raw, 0) if (kasa_id_raw and str(kasa_id_raw).isdigit()) else None

    tutar = money(request.form.get('tutar'))
    if tutar <= 0:
        flash('Tutar 0 olamaz.', 'danger')
        return redirect(request.referrer or url_for('musteri.musteri_detay', id=m_id))

    yeni_odeme = Odeme(
        tutar=tutar,
        birim=birim,
        aciklama=(request.form.get('aciklama') or '').strip(),
        odeme_yontemi=(request.form.get('odeme_yontemi') or 'Havale/EFT').strip(),
        banka_kasa_id=kasa_id,
        kur_degeri=kur,
        is_kaydi_id=is_id,
        musteri_id=m_id
    )
    db.session.add(yeni_odeme)

    # Kasa bakiyesi artır (TRY karşılığı)
    if kasa_id:
        kasa = BankaKasa.query.get(kasa_id)
        if kasa:
            try:
                try_tutar = money(tutar * (kur or Decimal("1")))
            except Exception:
                try_tutar = money("0")

            try:
                mevcut_bakiye = money(getattr(kasa, "bakiye", Decimal("0")) or Decimal("0"))
            except Exception:
                mevcut_bakiye = money("0")

            kasa.bakiye = money(mevcut_bakiye + try_tutar)

    db.session.commit()

    flash('Tahsilat kaydedildi.', 'success')
    return redirect(request.referrer or url_for('musteri.musteri_detay', id=m_id))


@musteri_bp.route('/odeme_sil/<int:id>', methods=['POST'])
def odeme_sil(id):
    if not _login_gerekli():
        return redirect(url_for('genel.index'))

    o = Odeme.query.get_or_404(id)
    m_id = o.musteri_id

    # Silmeden önce kasa geri alımı (TRY karşılığı)
    kasa_id = o.banka_kasa_id
    if kasa_id:
        kasa = BankaKasa.query.get(kasa_id)
        if kasa:
            kur_degeri = _safe_decimal_one(getattr(o, "kur_degeri", None))

            try:
                try_tutar = money(o.tutar * kur_degeri)
            except Exception:
                try_tutar = money("0")

            try:
                mevcut_bakiye = money(getattr(kasa, "bakiye", Decimal("0")) or Decimal("0"))
            except Exception:
                mevcut_bakiye = money("0")

            kasa.bakiye = money(mevcut_bakiye - try_tutar)

    db.session.delete(o)
    db.session.commit()

    flash('Tahsilat silindi.', 'warning')
    return redirect(url_for('musteri.musteri_detay', id=m_id))


@musteri_bp.route('/pdf_indir/<int:id>')
def pdf_indir(id):
    if not _login_gerekli():
        return redirect(url_for('genel.index'))

    kurlar = _kurlar_try_guvenli()

    m = Musteri.query.get_or_404(id)

    net_try = Decimal("0")
    for i in m.isler:
        pb = normalize_currency(i.para_birimi)
        kur = rate(kurlar.get(pb, 1)) if pb != "TRY" else rate(1)
        net_try += (i.toplam_bedel * kur)
    for o in m.odemeler:
        kur_d = _safe_decimal_one(getattr(o, "kur_degeri", None))
        net_try -= (o.tutar * kur_d)

    usd_kur = rate(kurlar.get('USD', 1))
    net_usd = (net_try / usd_kur) if usd_kur != 0 else Decimal("0")

    return pdf_olustur(m, money(net_try), money(net_usd))
