# sinyal_motoru.py
# Supertrend tabanlı BİST sinyal motoru.
# ATR(10), çarpan 3.0 — standart parametreler.

import numpy as np
import pandas as pd
import logging
from dataclasses import dataclass, field
from config import (
    MIN_VOLUME_FILTER,
    MIN_CANDLE_COUNT,
    VOLUME_LOOKBACK_CANDLES,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Sabitler
# ─────────────────────────────────────────────────────────────
ST_ATR_PERIOD  = 10
ST_MULTIPLIER  = 3.0


# ─────────────────────────────────────────────────────────────
# Veri Sınıfı
# ─────────────────────────────────────────────────────────────

@dataclass
class SinyalSonucu:
    ticker:            str
    gecerli:           bool  = False

    # Fiyat bilgisi
    fiyat:             float = 0.0
    fiyat_degisim_pct: float = 0.0

    # Supertrend
    st_yon:            str   = ""    # "YUKARI" veya "ASAGI"
    st_deger:          float = 0.0   # supertrend çizgisi değeri
    st_mesafe_pct:     float = 0.0   # fiyat ile supertrend arası %

    # Hacim
    son_hacim:         float = 0.0
    ort_hacim:         float = 0.0
    hacim_carpani:     float = 0.0

    # Detay
    mum_sayisi:        int   = 0
    red_flag:          str   = ""


# ─────────────────────────────────────────────────────────────
# Supertrend Hesaplayıcı
# ─────────────────────────────────────────────────────────────

def _supertrend(df: pd.DataFrame, atr_period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    """
    Supertrend göstergesini hesaplar.
    Döner: df + 'ST', 'ST_YON' sütunları
      ST_YON: 1 = yukarı trend (alım), -1 = aşağı trend (satım)
    """
    high  = df["High"].values.astype(float)
    low   = df["Low"].values.astype(float)
    close = df["Close"].values.astype(float)
    n     = len(close)

    # ATR hesapla (Wilder's smoothing)
    tr = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i]  - close[i - 1])
        )
    tr[0] = high[0] - low[0]

    atr = np.zeros(n)
    atr[atr_period - 1] = np.mean(tr[:atr_period])
    for i in range(atr_period, n):
        atr[i] = (atr[i - 1] * (atr_period - 1) + tr[i]) / atr_period

    # Üst ve alt bantlar
    hl2       = (high + low) / 2.0
    ust_bant  = hl2 + multiplier * atr
    alt_bant  = hl2 - multiplier * atr

    # Supertrend hesapla
    st     = np.zeros(n)
    yon    = np.ones(n, dtype=int)   # 1 = yukarı, -1 = aşağı

    for i in range(atr_period, n):
        # Alt bant güncelle
        if alt_bant[i] > alt_bant[i - 1] or close[i - 1] < st[i - 1]:
            alt_bant[i] = alt_bant[i]
        else:
            alt_bant[i] = alt_bant[i - 1]

        # Üst bant güncelle
        if ust_bant[i] < ust_bant[i - 1] or close[i - 1] > st[i - 1]:
            ust_bant[i] = ust_bant[i]
        else:
            ust_bant[i] = ust_bant[i - 1]

        # Yön belirle
        if st[i - 1] == ust_bant[i - 1]:
            if close[i] <= ust_bant[i]:
                st[i]  = ust_bant[i]
                yon[i] = -1
            else:
                st[i]  = alt_bant[i]
                yon[i] = 1
        else:
            if close[i] >= alt_bant[i]:
                st[i]  = alt_bant[i]
                yon[i] = 1
            else:
                st[i]  = ust_bant[i]
                yon[i] = -1

    result = df.copy()
    result["ST"]     = st
    result["ST_YON"] = yon
    return result


# ─────────────────────────────────────────────────────────────
# Hacim Yardımcısı
# ─────────────────────────────────────────────────────────────

def _hacim_bilgisi(df: pd.DataFrame) -> tuple[float, float, float]:
    """Döner: (son_hacim, ort_hacim, carpan)"""
    try:
        hacimler  = df["Volume"].values.astype(float)
        son_hacim = hacimler[-1]
        ort_hacim = np.mean(hacimler[-VOLUME_LOOKBACK_CANDLES:-1])
        carpan    = son_hacim / ort_hacim if ort_hacim > 0 else 0.0
        return son_hacim, ort_hacim, carpan
    except Exception:
        return 0.0, 0.0, 0.0


def _fiyat_degisim(df: pd.DataFrame) -> float:
    """Günün açılışına göre son kapanışın % değişimi."""
    try:
        acilis   = float(df["Open"].iloc[-min(8, len(df))])
        kapanis  = float(df["Close"].iloc[-1])
        return (kapanis - acilis) / acilis * 100
    except Exception:
        return 0.0


# ─────────────────────────────────────────────────────────────
# Ana Analiz Fonksiyonu
# ─────────────────────────────────────────────────────────────

def analiz_et(ticker: str, df: pd.DataFrame) -> SinyalSonucu:
    """
    Supertrend kesişimi tespit eder.
    Sadece bear→bull dönüşü (yeni alım sinyali) gönderilir.
    """
    sonuc = SinyalSonucu(ticker=ticker)

    try:
        sonuc.mum_sayisi = len(df)

        # ── Minimum veri kontrolü ─────────────────────────────
        if len(df) < ST_ATR_PERIOD + 5:
            sonuc.red_flag = "Yetersiz mum sayısı"
            return sonuc

        # ── Hacim filtresi ────────────────────────────────────
        gun_hacmi = float(df["Volume"].tail(8).sum())
        if gun_hacmi < MIN_VOLUME_FILTER:
            sonuc.red_flag = "Hacim çok düşük"
            return sonuc

        # ── Supertrend hesapla ────────────────────────────────
        df_st = _supertrend(df, ST_ATR_PERIOD, ST_MULTIPLIER)

        son_yon    = int(df_st["ST_YON"].iloc[-1])
        onceki_yon = int(df_st["ST_YON"].iloc[-2])
        son_st     = float(df_st["ST"].iloc[-1])
        son_fiyat  = float(df_st["Close"].iloc[-1])

        # ── Sadece yeni kesişimi yakala (bear→bull) ───────────
        yeni_kesisim = (onceki_yon == -1 and son_yon == 1)

        if not yeni_kesisim:
            sonuc.red_flag = "Supertrend kesişimi yok"
            return sonuc

        # ── Ek bilgiler ───────────────────────────────────────
        son_hacim, ort_hacim, carpan = _hacim_bilgisi(df)
        fiyat_degisim                = _fiyat_degisim(df)
        mesafe_pct = (son_fiyat - son_st) / son_st * 100 if son_st > 0 else 0.0

        sonuc.gecerli           = True
        sonuc.fiyat             = son_fiyat
        sonuc.fiyat_degisim_pct = fiyat_degisim
        sonuc.st_yon            = "YUKARI"
        sonuc.st_deger          = son_st
        sonuc.st_mesafe_pct     = mesafe_pct
        sonuc.son_hacim         = son_hacim
        sonuc.ort_hacim         = ort_hacim
        sonuc.hacim_carpani     = carpan

    except Exception as e:
        logger.error(f"{ticker} analiz hatası: {e}")
        sonuc.red_flag = f"Hata: {e}"

    return sonuc


# ─────────────────────────────────────────────────────────────
# Toplu Analiz
# ─────────────────────────────────────────────────────────────

def toplu_analiz(veri_sozlugu: dict) -> list[SinyalSonucu]:
    """Tüm hisseler için analiz yapar, fiyat değişimine göre sıralar."""
    sonuclar = []

    for ticker, df in veri_sozlugu.items():
        sonuc = analiz_et(ticker, df)
        if sonuc.gecerli:
            sonuclar.append(sonuc)

    # Fiyat değişimine göre sırala (en güçlü hareket önce)
    sonuclar.sort(key=lambda x: x.fiyat_degisim_pct, reverse=True)

    logger.info(
        f"Analiz tamamlandı. "
        f"{len(veri_sozlugu)} hisse tarandı, "
        f"{len(sonuclar)} Supertrend sinyali üretildi."
    )
    return sonuclar
