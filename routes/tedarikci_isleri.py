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


def _kur(pb: str, kurlar: dict) -> Decimal:
    """
    Para birimini normalize eder ve Decimal kur döner.
    TRY için 1 döner.
    """
    pb_n = normalize_currency(pb)
    return rate(kurlar.get(pb_n, 1)) if pb_n != "TRY" else rate(1)


def _int_or_none(v):
    """
    Formdan gelen id değerini güvenle int/None'a çevirir.
    '', None, '0' -> None
    """
    if v is None:
        return None
    s = str(v).strip()
    if s == "" or s == "0":
        return None
    if s.isdigit():
        return int(s)
    return None


@tedarikci_bp.route('/ticari_borclar')
def ticari_borclar():
    if 'logged_in' not in session:
        return redirect(url_for('genel.index'))

    kurlar = _kurlar_try_guvenli()
    q = request.args.get('q')

    if q:
        tedarikciler = (
            Tedarikci.query.filter(
                Tedarikci.durum == 'Aktif',
                or_(Tedarikci.firma_adi.contains(q), Tedarikci.yetkili_kisi.contains(q))
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
            sum((o.tutar * (o.kur_degeri or Decimal("1"))) for o in t.odenenler)
            if t.odenenler else Decimal("0")
        )

        # Template tarafında gerekirse gösterim için kullanırsın.
        # (Decimal kalsın)
        t.guncel_bakiye = money(alis_toplam - odeme_toplam)

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
    if 'logged_in' not in session:
        return redirect(url_for('genel.index'))

    db.session.add(Tedarikci(
        firma_adi=request.form.get('firma_adi'),
        yetkili_kisi=request.form.get('yetkili_kisi'),
        telefon=request.form.get('telefon'),
        adres=request.form.get('adres'),
        durum='Aktif'
    ))
    db.session.commit()
    return redirect(url_for('tedarikci.ticari_borclar'))


@tedarikci_bp.route('/tedarikci/<int:id>')
def tedarikci_detay(id):
    if 'logged_in' not in session:
        return redirect(url_for('genel.index'))

    kurlar = _kurlar_try_guvenli()

    t = Tedarikci.query.get_or_404(id)
    kasalar = BankaKasa.query.all()

    alis_toplam = (
        sum((alim.tutar * _kur(alim.para_birimi, kurlar)) for alim in t.satin_almalar)
        if t.satin_almalar else Decimal("0")
    )

    odeme_toplam = (
        sum((o.tutar * (o.kur_degeri or Decimal("1"))) for o in t.odenenler)
        if t.odenenler else Decimal("0")
    )

    net_try = money(alis_toplam - odeme_toplam)

    usd_kur = rate(kurlar.get('USD', 1))
    toplam_usd = money(net_try / usd_kur) if usd_kur != 0 else money("0")

    # ✅ KRİTİK: template "{:,.2f}".format(...) kullandığı için STR GÖNDERME!
    # Decimal gönderiyoruz -> format(...) sorunsuz.
    return render_template(
        'tedarikci_detay.html',
        tedarikci=t,
        toplam_tl=net_try,
        toplam_usd=toplam_usd,
        kurlar=kurlar,
        kasalar=kasalar
    )


@tedarikci_bp.route('/tedarikci_duzenle/<int:id>', methods=['GET', 'POST'])
def tedarikci_duzenle(id):
    if 'logged_in' not in session:
        return redirect(url_for('genel.index'))

    tedarikci = Tedarikci.query.get_or_404(id)
    if request.method == 'POST':
        tedarikci.firma_adi = request.form.get('firma_adi')
        tedarikci.yetkili_kisi = request.form.get('yetkili_kisi')
        tedarikci.telefon = request.form.get('telefon')
        tedarikci.adres = request.form.get('adres')
        db.session.commit()
        return redirect(url_for('tedarikci.ticari_borclar'))

    return render_template('tedarikci_duzenle.html', tedarikci=tedarikci)


@tedarikci_bp.route('/tedarikci_sil/<int:id>', methods=['POST'])
def tedarikci_sil(id):
    if 'logged_in' not in session:
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
    if 'logged_in' not in session:
        return redirect(url_for('genel.index'))

    t_id = int(request.form.get('tedarikci_id'))
    pb = normalize_currency(request.form.get('para_birimi') or 'TRY')

    db.session.add(SatinAlma(
        malzeme_tanimi=request.form.get('malzeme_tanimi'),
        tutar=money(request.form.get('tutar') or 0),
        para_birimi=pb,
        fatura_no=request.form.get('fatura_no'),
        tarih=datetime.now(),
        tedarikci_id=t_id
    ))
    db.session.commit()
    return redirect(url_for('tedarikci.tedarikci_detay', id=t_id))


@tedarikci_bp.route('/alim_sil/<int:id>', methods=['POST'])
def alim_sil(id):
    if 'logged_in' not in session:
        return redirect(url_for('genel.index'))

    kayit = SatinAlma.query.get_or_404(id)
    t_id = kayit.tedarikci_id
    db.session.delete(kayit)
    db.session.commit()
    return redirect(url_for('tedarikci.tedarikci_detay', id=t_id))


@tedarikci_bp.route('/tedarikci_odeme_yap', methods=['POST'])
def tedarikci_odeme_yap():
    if 'logged_in' not in session:
        return redirect(url_for('genel.index'))

    kurlar = _kurlar_try_guvenli()

    t_id = int(request.form.get('tedarikci_id'))
    birim = normalize_currency(request.form.get('birim') or 'TRY')
    banka_kasa_id = _int_or_none(request.form.get('banka_kasa_id'))  # ✅ int/None

    kur = rate(kurlar.get(birim, 1)) if birim != 'TRY' else rate(1)

    yeni_odeme = TedarikciOdeme(
        tutar=money(request.form.get('tutar') or 0),
        birim=birim,
        aciklama=request.form.get('aciklama'),
        kur_degeri=kur,
        banka_kasa_id=banka_kasa_id,   # ✅ integer kaydolur -> kasa özetinde düşer
        odeme_tarihi=datetime.now(),
        tedarikci_id=t_id
    )
    db.session.add(yeni_odeme)
    db.session.commit()
    flash('Tedarikçi ödemesi kaydedildi.', 'success')
    return redirect(url_for('tedarikci.tedarikci_detay', id=t_id))


@tedarikci_bp.route('/tedarikci_odeme_sil/<int:id>', methods=['POST'])
def tedarikci_odeme_sil(id):
    if 'logged_in' not in session:
        return redirect(url_for('genel.index'))

    kayit = TedarikciOdeme.query.get_or_404(id)
    t_id = kayit.tedarikci_id
    db.session.delete(kayit)
    db.session.commit()
    flash('Tedarikçi ödemesi silindi.', 'warning')
    return redirect(url_for('tedarikci.tedarikci_detay', id=t_id))
