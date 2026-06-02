# veri_cekici.py
# yfinance üzerinden BİST hisselerini batch halinde çeker.
# Rate limit aşımını önlemek için BATCH_SIZE ve BATCH_DELAY_SEC kullanılır.

import time
import logging
import pandas as pd
import yfinance as yf
from typing import Dict, Optional
from config import (
    INTERVAL, LOOKBACK_PERIOD,
    BATCH_SIZE, BATCH_DELAY_SEC,
    MIN_CANDLE_COUNT
)

logger = logging.getLogger(__name__)


def hisse_verisi_cek(ticker: str) -> Optional[pd.DataFrame]:
    """
    Tek bir hisse için OHLCV verisi çeker.
    Hata durumunda None döner.
    """
    try:
        df = yf.download(
            ticker,
            period=LOOKBACK_PERIOD,
            interval=INTERVAL,
            progress=False,
            auto_adjust=True,
            prepost=False,
        )

        if df is None or df.empty:
            return None

        # Multi-level column varsa düzelt
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.droplevel(1)

        # Minimum mum kontrolü
        if len(df) < MIN_CANDLE_COUNT:
            return None

        df.index = pd.to_datetime(df.index)
        df = df.dropna(subset=["Close", "Volume"])
        df.attrs["ticker"] = ticker

        return df

    except Exception as e:
        logger.debug(f"{ticker} verisi çekilemedi: {e}")
        return None


def toplu_veri_cek(tickers: list) -> Dict[str, pd.DataFrame]:
    """
    Tüm ticker listesini batch halinde çeker.
    Başarılı olanları dict olarak döner: {ticker: DataFrame}
    """
    sonuclar: Dict[str, pd.DataFrame] = {}
    toplam = len(tickers)
    basarili = 0
    basarisiz = 0

    # Batch'lere böl
    batches = [tickers[i:i + BATCH_SIZE] for i in range(0, toplam, BATCH_SIZE)]
    logger.info(f"{toplam} hisse {len(batches)} batch'te çekilecek.")

    for batch_no, batch in enumerate(batches, 1):
        logger.info(f"Batch {batch_no}/{len(batches)} işleniyor... ({len(batch)} hisse)")

        try:
            # yfinance'in toplu çekimi daha hızlı
            raw = yf.download(
                tickers=" ".join(batch),
                period=LOOKBACK_PERIOD,
                interval=INTERVAL,
                progress=False,
                auto_adjust=True,
                prepost=False,
                group_by="ticker",
            )

            for ticker in batch:
                try:
                    if len(batch) == 1:
                        # Tek hisse durumu
                        df = raw.copy()
                    else:
                        if ticker not in raw.columns.get_level_values(0):
                            basarisiz += 1
                            continue
                        df = raw[ticker].copy()

                    df = df.dropna(subset=["Close", "Volume"])

                    if df.empty or len(df) < MIN_CANDLE_COUNT:
                        basarisiz += 1
                        continue

                    df.index = pd.to_datetime(df.index)
                    df.attrs["ticker"] = ticker
                    sonuclar[ticker] = df
                    basarili += 1

                except Exception as e:
                    logger.debug(f"{ticker} parse hatası: {e}")
                    basarisiz += 1

        except Exception as e:
            logger.warning(f"Batch {batch_no} hatası: {e}")
            # Batch başarısız olursa tek tek dene
            for ticker in batch:
                df = hisse_verisi_cek(ticker)
                if df is not None:
                    sonuclar[ticker] = df
                    basarili += 1
                else:
                    basarisiz += 1

        # Rate limit koruması
        if batch_no < len(batches):
            time.sleep(BATCH_DELAY_SEC)

    logger.info(
        f"Veri çekimi tamamlandı. "
        f"Başarılı: {basarili}, Başarısız: {basarisiz}, "
        f"Oran: %{basarili/toplam*100:.1f}"
    )
    return sonuclar
