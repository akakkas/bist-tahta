# telegram_bot.py
# Sinyal sonuçlarını formatlar ve Telegram'a gönderir.

import logging
import requests
from datetime import datetime
from sinyal_motoru import SinyalSonucu
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)


def _skor_emoji(skor: float) -> str:
    if skor >= 85: return "🔥"
    if skor >= 70: return "🚨"
    if skor >= 55: return "⚠️"
    return "📊"


def _faz_emoji(faz: str) -> str:
    emojiler = {
        "POMPA":              "🚀",
        "SİLKELEME SONRASI":  "🔄",
        "AKÜMÜLASİYON":       "🤫",
        "DAĞITIM ŞÜPHESİ":    "⛔",
        "BELİRSİZ":           "❓",
    }
    return emojiler.get(faz, "❓")


def _progress_bar(skor: float, uzunluk: int = 10) -> str:
    """Skor için görsel bar üretir."""
    dolu = int(skor / 100 * uzunluk)
    bos  = uzunluk - dolu
    return "█" * dolu + "░" * bos


def _format_sayi(sayi: float) -> str:
    """Büyük sayıları okunabilir hale getirir."""
    if sayi >= 1_000_000:
        return f"{sayi/1_000_000:.1f}M"
    if sayi >= 1_000:
        return f"{sayi/1_000:.0f}K"
    return f"{sayi:.0f}"


def sinyal_mesaji_olustur(s: SinyalSonucu) -> str:
    """
    Tek bir sinyal için detaylı Telegram mesajı oluşturur.
    """
    faz      = s.faz.aktif_faz
    ana_emoji = _skor_emoji(s.tahtaci_skoru)
    faz_emoji = _faz_emoji(faz)

    # Ticker'dan .IS uzantısını kaldır
    ticker_kisa = s.ticker.replace(".IS", "")

    # Skor çubuğu
    bar = _progress_bar(s.tahtaci_skoru)

    # Alt faz göstergeleri
    faz_detay = []
    if s.faz.akumulasyon:
        faz_detay.append("✅ Akümülasyon izi mevcut")
    if s.faz.silkeleme:
        faz_detay.append("✅ Silkeleme tespit edildi")
    if s.ardisik_yukari_mum >= 3:
        faz_detay.append(f"✅ Ardışık ↑ kapanış: {s.ardisik_yukari_mum} mum")
    if s.hacim_carpani >= 3.0:
        faz_detay.append(f"✅ Hacim anomalisi: {s.hacim_carpani:.1f}x")
    if s.faz.dagitim:
        faz_detay.append("⚠️ Dağıtım izi var — dikkat!")

    faz_satir = "\n   ".join(faz_detay) if faz_detay else "   (detay yok)"

    # Risk notu
    if s.faz.dagitim:
        risk_notu = "⛔ Dağıtım sinyali var, pozisyon almadan önce doğrula"
    elif s.tahtaci_skoru >= 80:
        risk_notu = "💪 Güçlü sinyal — yine de kendi analizini yap"
    else:
        risk_notu = "🔎 Orta güç sinyal — ek teyit ara"

    zaman = datetime.now().strftime("%H:%M")
    tarih = datetime.now().strftime("%d.%m.%Y")

    mesaj = (
        f"{ana_emoji} *TAHTACİ SİNYALİ — {ticker_kisa}*\n"
        f"{'─' * 28}\n"
        f"💰 Fiyat: *{s.fiyat:.2f} ₺*  "
        f"({'+' if s.fiyat_degisim_pct >= 0 else ''}{s.fiyat_degisim_pct:.1f}%)\n"
        f"\n"
        f"🎯 *Tahtacı Skoru: {s.tahtaci_skoru:.0f}/100*\n"
        f"   `{bar}` \n"
        f"\n"
        f"📊 Hacim: {_format_sayi(s.son_hacim)}  "
        f"(Ort: {_format_sayi(s.ort_hacim)}, *{s.hacim_carpani:.1f}x*)\n"
        f"\n"
        f"{faz_emoji} *Aktif Faz: {faz}*\n"
        f"   {faz_satir}\n"
        f"\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"Alt Skorlar:\n"
        f"  Akümülasyon : {s.akumulasyon_skoru:5.0f}/100\n"
        f"  Silkeleme   : {s.silkeleme_skoru:5.0f}/100\n"
        f"  Pompa       : {s.pompa_skoru:5.0f}/100\n"
        f"  Hacim Anom. : {s.hacim_skoru:5.0f}/100\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"\n"
        f"{risk_notu}\n"
        f"\n"
        f"🕐 {zaman} · {tarih}"
    )
    return mesaj


def ozet_mesaji_olustur(sinyaller: list, taranan: int) -> str:
    """
    Tarama tamamlandığında özet mesaj oluşturur.
    """
    zaman = datetime.now().strftime("%H:%M")

    if not sinyaller:
        return (
            f"🔍 *BİST TARAMA TAMAMLANDI*\n"
            f"{'─' * 28}\n"
            f"📋 Taranan hisse: {taranan}\n"
            f"❌ Sinyal bulunamadı\n"
            f"🕐 {zaman}"
        )

    en_iyi = sinyaller[0]
    ticker_kisa = en_iyi.ticker.replace(".IS", "")

    satir_listesi = []
    for s in sinyaller[:10]:  # max 10 göster
        t = s.ticker.replace(".IS", "")
        faz_k = s.faz.aktif_faz[:3]
        satir_listesi.append(
            f"  • {t:<8} {s.tahtaci_skoru:3.0f}/100  "
            f"{'+' if s.fiyat_degisim_pct >= 0 else ''}{s.fiyat_degisim_pct:.1f}%  "
            f"[{faz_k}]"
        )

    tablo = "\n".join(satir_listesi)

    return (
        f"📡 *BİST TARAMA ÖZETI*\n"
        f"{'─' * 28}\n"
        f"📋 Taranan: {taranan} hisse\n"
        f"🚨 Sinyal: {len(sinyaller)} adet\n"
        f"🏆 En güçlü: *{ticker_kisa}* ({en_iyi.tahtaci_skoru:.0f}/100)\n"
        f"\n"
        f"```\n{tablo}\n```\n"
        f"\n"
        f"🕐 {zaman}"
    )


def mesaj_gonder(metin: str) -> bool:
    """
    Telegram'a mesaj gönderir.
    Başarı durumunda True döner.
    """
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("TELEGRAM_TOKEN veya TELEGRAM_CHAT_ID tanımlı değil!")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    try:
        response = requests.post(
            url,
            json={
                "chat_id":    TELEGRAM_CHAT_ID,
                "text":       metin,
                "parse_mode": "Markdown",
            },
            timeout=10,
        )

        if response.status_code == 200:
            return True
        else:
            logger.error(f"Telegram hatası: {response.status_code} — {response.text}")
            return False

    except requests.exceptions.RequestException as e:
        logger.error(f"Telegram bağlantı hatası: {e}")
        return False


def sinyalleri_gonder(sinyaller: list, taranan: int) -> int:
    """
    Tüm sinyalleri Telegram'a gönderir.
    Döner: gönderilen mesaj sayısı.
    """
    import time

    gonderilen = 0

    # Önce detaylı sinyaller
    for sinyal in sinyaller:
        mesaj = sinyal_mesaji_olustur(sinyal)
        if mesaj_gonder(mesaj):
            gonderilen += 1
            logger.info(f"Sinyal gönderildi: {sinyal.ticker} ({sinyal.tahtaci_skoru:.0f}/100)")
        else:
            logger.warning(f"Sinyal gönderilemedi: {sinyal.ticker}")

        # Telegram rate limit: 30 mesaj/saniye → güvenli aralık
        time.sleep(0.5)

    # Sonra özet
    ozet = ozet_mesaji_olustur(sinyaller, taranan)
    if mesaj_gonder(ozet):
        gonderilen += 1

    return gonderilen
