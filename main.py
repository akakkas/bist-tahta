# main.py
# BİST Tahtacı Scanner — Ana modül
# GitHub Actions tarafından tetiklenir.

import logging
import sys
from datetime import datetime, timezone, timedelta

from hisse_listesi import get_tickers
from veri_cekici import toplu_veri_cek
from sinyal_motoru import toplu_analiz
from telegram_bot import sinyalleri_gonder, mesaj_gonder
from config import (
    TELEGRAM_TOKEN, TELEGRAM_CHAT_ID,
    MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE,
    MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE,
)

# ── Loglama ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("main")

# ── Zaman Dilimi ──────────────────────────────────────────────
TRT = timezone(timedelta(hours=3))  # Türkiye Saati (UTC+3)


def borsa_acik_mi() -> bool:
    """Şu an Borsa İstanbul'un açık olup olmadığını kontrol eder."""
    simdi = datetime.now(TRT)

    # Hafta sonu kontrol
    if simdi.weekday() >= 5:
        logger.info("Hafta sonu — borsa kapalı.")
        return False

    # Saat kontrolü
    acilis = simdi.replace(hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MINUTE, second=0)
    kapanis = simdi.replace(hour=MARKET_CLOSE_HOUR, minute=MARKET_CLOSE_MINUTE, second=0)

    if acilis <= simdi <= kapanis:
        return True

    logger.info(f"Borsa saatleri dışı. Şu an: {simdi.strftime('%H:%M TRT')}")
    return False


def config_dogrula() -> bool:
    """Gerekli ortam değişkenlerini kontrol eder."""
    hatalar = []
    if not TELEGRAM_TOKEN:
        hatalar.append("TELEGRAM_TOKEN tanımlı değil")
    if not TELEGRAM_CHAT_ID:
        hatalar.append("TELEGRAM_CHAT_ID tanımlı değil")

    if hatalar:
        for h in hatalar:
            logger.error(f"Config hatası: {h}")
        return False
    return True


def tara():
    """Ana tarama döngüsü."""
    logger.info("=" * 50)
    logger.info("BİST Tahtacı Scanner başlatıldı")
    logger.info(f"Zaman: {datetime.now(TRT).strftime('%d.%m.%Y %H:%M TRT')}")
    logger.info("=" * 50)

    # Config kontrolü
    if not config_dogrula():
        sys.exit(1)

    # Borsa açık mı?
    if not borsa_acik_mi():
        logger.info("Borsa kapalı, tarama yapılmıyor.")
        # Yine de Telegram'a bilgi ver (opsiyonel)
        # mesaj_gonder("ℹ️ Borsa kapalı, tarama yapılmadı.")
        sys.exit(0)

    # Hisse listesini al
    tickers = get_tickers()
    logger.info(f"{len(tickers)} hisse taranacak.")

    # Veri çek
    logger.info("Veri çekiliyor...")
    veri = toplu_veri_cek(tickers)
    logger.info(f"{len(veri)} hisse için veri alındı.")

    if not veri:
        logger.error("Hiç veri alınamadı!")
        mesaj_gonder("❌ BİST Scanner: Veri çekilemedi. yfinance erişim sorunu olabilir.")
        sys.exit(1)

    # Analiz et
    logger.info("Analiz yapılıyor...")
    sinyaller = toplu_analiz(veri)

    logger.info(f"{len(sinyaller)} sinyal bulundu.")

    # Telegram'a gönder
    if sinyaller or True:  # Sinyal olmasa da özet gönder
        logger.info("Telegram'a gönderiliyor...")
        gonderilen = sinyalleri_gonder(sinyaller, len(veri))
        logger.info(f"{gonderilen} mesaj gönderildi.")

    logger.info("Tarama tamamlandı.")


if __name__ == "__main__":
    tara()
