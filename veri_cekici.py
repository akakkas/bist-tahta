# veri_cekici.py
# yfinance üzerinden BİST hisselerini batch halinde çeker.
# Rate-limit'e karşı: batch düzeyinde retry + exponential backoff,
# ve başarısız batch'te tek-tek "hammer" YAPMAZ (blok'u azdırmamak için).

import time
import random
import logging
import pandas as pd
import yfinance as yf
from typing import Dict, Optional

import config
from config import (
    INTERVAL, LOOKBACK_PERIOD,
    BATCH_SIZE, BATCH_DELAY_SEC,
    MIN_CANDLE_COUNT,
)

logger = logging.getLogger(__name__)

# Yeni ayarlar — config.py'de tanımlıysa oradan, değilse bu varsayılanlar.
MAX_RETRIES = getattr(config, "MAX_RETRIES", 3)          # batch başına deneme
RETRY_BACKOFF_SEC = getattr(config, "RETRY_BACKOFF_SEC", 5)  # 5s, 10s, 20s...


def _temizle(df: Optional[pd.DataFrame], ticker: str) -> Optional[pd.DataFrame]:
    """Ortak temizlik: kolon düzleştir, NaN at, min mum kontrolü."""
    if df is None or df.empty:
        return None
    # Hem standalone (MultiIndex olabilir) hem raw[ticker] dilimi için güvenli:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(-1)  # alan seviyesini al (OHLCV)
    if "Close" not in df.columns or "Volume" not in df.columns:
        return None
    df = df.dropna(subset=["Close", "Volume"])
    if df.empty or len(df) < MIN_CANDLE_COUNT:
        return None
    df.index = pd.to_datetime(df.index)
    df.attrs["ticker"] = ticker
    return df


def hisse_verisi_cek(ticker: str) -> Optional[pd.DataFrame]:
    """Tek hisse, kısa retry'li. (Nadiren; tercih batch'tir.)"""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            df = yf.download(
                ticker, period=LOOKBACK_PERIOD, interval=INTERVAL,
                progress=False, auto_adjust=True, prepost=False, threads=False,
            )
            out = _temizle(df, ticker)
            if out is not None:
                return out
        except Exception as e:
            logger.debug(f"{ticker} deneme {attempt} hata: {e}")
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_BACKOFF_SEC * attempt + random.uniform(0, 1))
    return None


def _batch_indir(batch: list, batch_no: int) -> Optional[pd.DataFrame]:
    """Bir batch'i retry + exponential backoff ile indirir.
    Ham (group_by='ticker') veriyi ya da None döner."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            raw = yf.download(
                tickers=" ".join(batch),
                period=LOOKBACK_PERIOD,
                interval=INTERVAL,
                progress=False,
                auto_adjust=True,
                prepost=False,
                group_by="ticker",
                threads=False,   # paralel istek rate-limit'i kötüleştirir
            )
            if raw is not None and not raw.empty:
                return raw
            logger.warning(
                f"Batch {batch_no} boş döndü "
                f"(deneme {attempt}/{MAX_RETRIES}) — muhtemelen rate-limit."
            )
        except Exception as e:
            logger.warning(
                f"Batch {batch_no} indirme hatası "
                f"(deneme {attempt}/{MAX_RETRIES}): {e}"
            )
        # Son deneme değilse artan süre bekle (5s, 10s, 20s + jitter)
        if attempt < MAX_RETRIES:
            wait = RETRY_BACKOFF_SEC * (2 ** (attempt - 1)) + random.uniform(0, 2)
            logger.info(f"{wait:.0f}s bekleniyor, tekrar denenecek...")
            time.sleep(wait)
    return None


def toplu_veri_cek(tickers: list) -> Dict[str, pd.DataFrame]:
    """Tüm listeyi batch + retry ile çeker. {ticker: DataFrame} döner."""
    sonuclar: Dict[str, pd.DataFrame] = {}
    toplam = len(tickers)
    basarili = 0
    basarisiz = 0

    batches = [tickers[i:i + BATCH_SIZE] for i in range(0, toplam, BATCH_SIZE)]
    logger.info(f"{toplam} hisse {len(batches)} batch'te çekilecek.")

    for batch_no, batch in enumerate(batches, 1):
        logger.info(f"Batch {batch_no}/{len(batches)} işleniyor... ({len(batch)} hisse)")

        raw = _batch_indir(batch, batch_no)

        if raw is None:
            # Retry'lere rağmen olmadı. Tek-tek DENEME (IP throttle'ını azdırır),
            # bunun yerine batch'i atla ve biraz fazladan bekle.
            logger.warning(f"Batch {batch_no} tüm denemelerde başarısız, atlanıyor.")
            basarisiz += len(batch)
            time.sleep(RETRY_BACKOFF_SEC * 2 + random.uniform(0, 2))
            continue

        for ticker in batch:
            try:
                if len(batch) == 1:
                    df = raw.copy()
                else:
                    if ticker not in raw.columns.get_level_values(0):
                        basarisiz += 1
                        continue
                    df = raw[ticker].copy()
                out = _temizle(df, ticker)
                if out is None:
                    basarisiz += 1
                    continue
                sonuclar[ticker] = out
                basarili += 1
            except Exception as e:
                logger.debug(f"{ticker} parse hatası: {e}")
                basarisiz += 1

        # Batch'ler arası rate-limit koruması
        if batch_no < len(batches):
            time.sleep(BATCH_DELAY_SEC + random.uniform(0, 1))

    oran = (basarili / toplam * 100) if toplam else 0
    logger.info(
        f"Veri çekimi tamamlandı. "
        f"Başarılı: {basarili}, Başarısız: {basarisiz}, Oran: %{oran:.1f}"
    )
    return sonuclar
