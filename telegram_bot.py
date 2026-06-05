# telegram_bot.py
# Supertrend sinyal mesajlarını formatlar ve Telegram'a gönderir.

import logging
import requests
from datetime import datetime
from sinyal_motoru import SinyalSonucu
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)


def _format_sayi(sayi: float) -> str:
    if sayi >= 1_000_000:
        return f"{sayi/1_000_000:.1f}M"
    if sayi >= 1_000:
        return f"{sayi/1_000:.0f}K"
    return f"{sayi:.0f}"


def _hacim_yorum(carpan: float) -> str:
    if carpan >= 5.0: return "🔥 Çok yüksek"
    if carpan >= 3.0: return "🚨 Yüksek"
    if carpan >= 1.5: return "📈 Normal üstü"
    return "➡️ Normal"


def sinyal_mesaji_olustur(s: SinyalSonucu) -> str:
    ticker_kisa = s.ticker.replace(".IS", "")
    zaman = datetime.now().strftime("%H:%M")
    tarih = datetime.now().strftime("%d.%m.%Y")

    hacim_yorum = _hacim_yorum(s.hacim_carpani)

    mesaj = (
        f"🟢 *SUPERTREND SİNYALİ — {ticker_kisa}*\n"
        f"{'─' * 30}\n"
        f"\n"
        f"💰 Fiyat : *{s.fiyat:.2f} ₺*"
        f"  ({'+' if s.fiyat_degisim_pct >= 0 else ''}{s.fiyat_degisim_pct:.1f}%)\n"
        f"📐 ST Çizgisi : {s.st_deger:.2f} ₺\n"
        f"📏 Mesafe : %{s.st_mesafe_pct:.1f} yukarıda\n"
        f"\n"
        f"📊 *Hacim*\n"
        f"   Son    : {_format_sayi(s.son_hacim)}\n"
        f"   Ort    : {_format_sayi(s.ort_hacim)}\n"
        f"   Çarpan : *{s.hacim_carpani:.1f}x*  {hacim_yorum}\n"
        f"\n"
        f"⚙️ Parametre: ATR({10}) × {3.0} · 15dk\n"
        f"\n"
        f"{'─' * 30}\n"
        f"⚠️ Bu bir bilgi sinyalidir, yatırım tavsiyesi değildir.\n"
        f"🕐 {zaman} · {tarih}"
    )
    return mesaj


def ozet_mesaji_olustur(sinyaller: list, taranan: int) -> str:
    zaman = datetime.now().strftime("%H:%M")

    if not sinyaller:
        return (
            f"🔍 *BİST SUPERTREND TARAMASI*\n"
            f"{'─' * 30}\n"
            f"📋 Taranan : {taranan} hisse\n"
            f"❌ Yeni kesişim bulunamadı\n"
            f"🕐 {zaman}"
        )

    satir_listesi = []
    for s in sinyaller[:15]:
        t = s.ticker.replace(".IS", "")
        satir_listesi.append(
            f"  {t:<8} "
            f"{'+' if s.fiyat_degisim_pct >= 0 else ''}{s.fiyat_degisim_pct:.1f}%  "
            f"hacim:{s.hacim_carpani:.1f}x"
        )

    tablo = "\n".join(satir_listesi)

    return (
        f"📡 *BİST SUPERTREND ÖZET*\n"
        f"{'─' * 30}\n"
        f"📋 Taranan  : {taranan} hisse\n"
        f"🟢 Sinyal   : {len(sinyaller)} yeni kesişim\n"
        f"\n"
        f"```\n{tablo}\n```\n"
        f"\n"
        f"🕐 {zaman}"
    )


def mesaj_gonder(metin: str) -> bool:
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
    import time
    gonderilen = 0

    for sinyal in sinyaller:
        mesaj = sinyal_mesaji_olustur(sinyal)
        if mesaj_gonder(mesaj):
            gonderilen += 1
            logger.info(f"Sinyal gönderildi: {sinyal.ticker} (+{sinyal.fiyat_degisim_pct:.1f}%)")
        else:
            logger.warning(f"Sinyal gönderilemedi: {sinyal.ticker}")
        time.sleep(0.5)

    ozet = ozet_mesaji_olustur(sinyaller, taranan)
    if mesaj_gonder(ozet):
        gonderilen += 1

    return gonderilen
