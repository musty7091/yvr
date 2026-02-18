from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from sqlalchemy import or_
from models import db, Tedarikci, SatinAlma, TedarikciOdeme, BankaKasa, money, rate, normalize_currency
from utils import GUNCEL_KURLAR
from decimal import Decimal
from datetime import datetime

tedarikci_bp = Blueprint('tedarikci', __name__)


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


def _int_or_none(v):
    if v is None:
        return None
    s = str(v).strip()
    if s == "" or s.lower() in ("none", "null"):
        return None
    return int(s) if s.isdigit() else None


def _safe_decimal_one(v):
    try:
        if v is None:
            return Decimal("1")
        if isinstance(v, Decimal):
            return v
        return Decimal(str(v))
    except Exception:
        return Decimal("1")


def _kur(pb: str, kurlar: dict) -> Decimal:
    pb_n = normalize_currency(pb)
    return rate(kurlar.get(pb_n, 1)) if pb_n != "TRY" else rate(1)


def _kasa_bakiye_azalt(kasa_id: int, tutar_try: Decimal):
    """
    Kasa bakiyesini TRY bazında azaltır.
    tutar_try: Decimal (TRY)
    """
    if not kasa_id:
        return

    kasa = BankaKasa.query.get(kasa_id)
    if not kasa:
        return

    mevcut = money(getattr(kasa, "bakiye", Decimal("0")) or Decimal("0"))
    kasa.bakiye = money(mevcut - money(tutar_try))


def _kasa_bakiye_arttir(kasa_id: int, tutar_try: Decimal):
    """
    Kasa bakiyesini TRY bazında arttırır.
    tutar_try: Decimal (TRY)
    """
    if not kasa_id:
        return

    kasa = BankaKasa.query.get(kasa_id)
    if not kasa:
        return

    mevcut = money(getattr(kasa, "bakiye", Decimal("0")) or Decimal("0"))
    kasa.bakiye = money(mevcut + money(tutar_try))


@tedarikci_bp.route('/ticari_borclar')
def ticari_borclar():
    if not _login_gerekli():
        return redirect(url_for('genel.index'))

    kurlar = _kurlar_try_guvenli()
    q = (request.args.get('q') or '').strip()

    if q:
        tedarikciler = (
            Tedarikci.query.filter(
                Tedarikci.durum == 'Aktif',
                or_(
                    Tedarikci.firma_adi.contains(q),
                    Tedarikci.yetkili_kisi.contains(q)
                )
            ).all()
        )
    else:
        tedarikciler = Tedarikci.query.filter_by(durum='Aktif').all()

    for t in tedarikciler:
        alis_toplam = (
            sum((alim.tutar * _kur(alim.para_birimi, kurlar)) for alim in t.satin_almalar)
            if t.satin_almalar else Decimal("0")
        )
        odeme_toplam = (
            sum((o.tutar * (_safe_decimal_one(getattr(o, "kur_degeri", None)))) for o in t.odenenler)
            if t.odenenler else Decimal("0")
        )
        t.guncel_bakiye = alis_toplam - odeme_toplam

    tedarikciler.sort(key=lambda x: x.guncel_bakiye, reverse=True)

    return render_template(
        'ticari_borclar.html',
        tedarikciler=tedarikciler,
        arama_var=bool(q),
        terim=q,
        kurlar=kurlar
    )


@tedarikci_bp.route('/tedarikci_ekle', methods=['POST'])
def tedarikci_ekle():
    if not _login_gerekli():
        return redirect(url_for('genel.index'))

    firma_adi = (request.form.get('firma_adi') or '').strip()
    if not firma_adi:
        flash('Firma adı boş olamaz.', 'danger')
        return redirect(url_for('tedarikci.ticari_borclar'))

    db.session.add(Tedarikci(
        firma_adi=firma_adi,
        yetkili_kisi=(request.form.get('yetkili_kisi') or '').strip(),
        telefon=(request.form.get('telefon') or '').strip(),
        adres=(request.form.get('adres') or '').strip(),
        durum='Aktif'
    ))
    db.session.commit()
    return redirect(url_for('tedarikci.ticari_borclar'))


@tedarikci_bp.route('/tedarikci/<int:id>')
def tedarikci_detay(id):
    if not _login_gerekli():
        return redirect(url_for('genel.index'))

    kurlar = _kurlar_try_guvenli()
    t = Tedarikci.query.get_or_404(id)
    kasalar = BankaKasa.query.all()

    alis_toplam = (
        sum((alim.tutar * _kur(alim.para_birimi, kurlar)) for alim in t.satin_almalar)
        if t.satin_almalar else Decimal("0")
    )
    odeme_toplam = (
        sum((o.tutar * (_safe_decimal_one(getattr(o, "kur_degeri", None)))) for o in t.odenenler)
        if t.odenenler else Decimal("0")
    )

    net_try = alis_toplam - odeme_toplam

    usd_kur = rate(kurlar.get('USD', 1))
    toplam_usd = (net_try / usd_kur) if usd_kur != 0 else Decimal("0")

    return render_template(
        'tedarikci_detay.html',
        tedarikci=t,
        toplam_tl=money(net_try),          # Decimal
        toplam_usd=money(toplam_usd),      # Decimal
        kurlar=kurlar,
        kasalar=kasalar
    )


@tedarikci_bp.route('/tedarikci_duzenle/<int:id>', methods=['GET', 'POST'])
def tedarikci_duzenle(id):
    if not _login_gerekli():
        return redirect(url_for('genel.index'))

    tedarikci = Tedarikci.query.get_or_404(id)
    if request.method == 'POST':
        firma_adi = (request.form.get('firma_adi') or '').strip()
        if not firma_adi:
            flash('Firma adı boş olamaz.', 'danger')
            return redirect(url_for('tedarikci.tedarikci_duzenle', id=id))

        tedarikci.firma_adi = firma_adi
        tedarikci.yetkili_kisi = (request.form.get('yetkili_kisi') or '').strip()
        tedarikci.telefon = (request.form.get('telefon') or '').strip()
        tedarikci.adres = (request.form.get('adres') or '').strip()
        db.session.commit()
        return redirect(url_for('tedarikci.ticari_borclar'))

    return render_template('tedarikci_duzenle.html', tedarikci=tedarikci)


@tedarikci_bp.route('/tedarikci_sil/<int:id>', methods=['POST'])
def tedarikci_sil(id):
    if not _login_gerekli():
        return redirect(url_for('genel.index'))

    t = Tedarikci.query.get_or_404(id)
    if t.satin_almalar or t.odenenler:
        t.durum = 'Pasif'
    else:
        db.session.delete(t)

    db.session.commit()
    return redirect(url_for('tedarikci.ticari_borclar'))


@tedarikci_bp.route('/malzeme_alim_ekle', methods=['POST'])
def malzeme_alim_ekle():
    if not _login_gerekli():
        return redirect(url_for('genel.index'))

    t_id = _safe_int(request.form.get('tedarikci_id'), 0)
    if not t_id:
        flash('Tedarikçi seçimi hatalı.', 'danger')
        return redirect(request.referrer or url_for('tedarikci.ticari_borclar'))

    pb = normalize_currency(request.form.get('para_birimi') or 'TRY')
    tutar = money(request.form.get('tutar') or 0)
    if tutar < 0:
        flash('Tutar negatif olamaz.', 'danger')
        return redirect(url_for('tedarikci.tedarikci_detay', id=t_id))

    malzeme_tanimi = (request.form.get('malzeme_tanimi') or '').strip()
    if not malzeme_tanimi:
        flash('Malzeme tanımı boş olamaz.', 'danger')
        return redirect(url_for('tedarikci.tedarikci_detay', id=t_id))

    db.session.add(SatinAlma(
        malzeme_tanimi=malzeme_tanimi,
        tutar=tutar,
        para_birimi=pb,
        fatura_no=(request.form.get('fatura_no') or '').strip(),
        tarih=datetime.now(),
        tedarikci_id=t_id
    ))
    db.session.commit()
    return redirect(url_for('tedarikci.tedarikci_detay', id=t_id))


@tedarikci_bp.route('/alim_sil/<int:id>', methods=['POST'])
def alim_sil(id):
    if not _login_gerekli():
        return redirect(url_for('genel.index'))

    kayit = SatinAlma.query.get_or_404(id)
    t_id = kayit.tedarikci_id
    db.session.delete(kayit)
    db.session.commit()
    return redirect(url_for('tedarikci.tedarikci_detay', id=t_id))


@tedarikci_bp.route('/tedarikci_odeme_yap', methods=['POST'])
def tedarikci_odeme_yap():
    """
    KRİTİK:
    - TedarikciOdeme kaydı eklenir
    - Seçilen kasa/banka hesabının BAKİYESİ (TRY bazında) DÜŞÜRÜLÜR
    """
    if not _login_gerekli():
        return redirect(url_for('genel.index'))

    kurlar = _kurlar_try_guvenli()

    t_id = _safe_int(request.form.get('tedarikci_id') or 0, 0)
    if not t_id:
        flash('Tedarikçi seçimi hatalı.', 'danger')
        return redirect(request.referrer or url_for('tedarikci.ticari_borclar'))

    birim = normalize_currency(request.form.get('birim') or 'TRY')

    kasa_id = _int_or_none(request.form.get('banka_kasa_id'))
    if not kasa_id:
        flash('Lütfen ödeme çıkacak hesabı seçin.', 'danger')
        return redirect(url_for('tedarikci.tedarikci_detay', id=t_id))

    tutar = money(request.form.get('tutar') or 0)
    if tutar <= 0:
        flash('Tutar 0 olamaz.', 'danger')
        return redirect(url_for('tedarikci.tedarikci_detay', id=t_id))

    kur = rate(kurlar.get(birim, 1)) if birim != 'TRY' else rate(1)
    tutar_try = money(tutar * kur)  # TRY karşılığı

    yeni_odeme = TedarikciOdeme(
        tutar=tutar,
        birim=birim,
        aciklama=(request.form.get('aciklama') or '').strip(),
        kur_degeri=kur,
        banka_kasa_id=kasa_id,
        tedarikci_id=t_id,
        odeme_tarihi=datetime.now()
    )
    db.session.add(yeni_odeme)

    # >>> KASA BAKİYESİNİ DÜŞ
    _kasa_bakiye_azalt(kasa_id, tutar_try)

    db.session.commit()
    flash('Tedarikçi ödemesi kaydedildi, kasa bakiyesi güncellendi.', 'success')
    return redirect(url_for('tedarikci.tedarikci_detay', id=t_id))


@tedarikci_bp.route('/tedarikci_odeme_sil/<int:id>', methods=['POST'])
def tedarikci_odeme_sil(id):
    """
    KRİTİK:
    - TedarikciOdeme silinir
    - Seçilen kasa/banka hesabına TRY karşılığı GERİ EKLENİR
    """
    if not _login_gerekli():
        return redirect(url_for('genel.index'))

    kayit = TedarikciOdeme.query.get_or_404(id)
    t_id = kayit.tedarikci_id

    kasa_id = kayit.banka_kasa_id
    kur_d = _safe_decimal_one(getattr(kayit, "kur_degeri", None))
    tutar_try = money((kayit.tutar or Decimal("0")) * kur_d)

    db.session.delete(kayit)

    # >>> KASA BAKİYESİNİ GERİ AL
    _kasa_bakiye_arttir(kasa_id, tutar_try)

    db.session.commit()
    flash('Ödeme silindi, kasa bakiyesi geri güncellendi.', 'warning')
    return redirect(url_for('tedarikci.tedarikci_detay', id=t_id))
