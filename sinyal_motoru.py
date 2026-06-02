# sinyal_motoru.py
# BİST hisselerinde tahtacı davranışını proxy göstergelerle tespit eder.
# Her hisse için 0-100 arası bileşik bir "Tahtacı Skoru" üretir.

import numpy as np
import pandas as pd
import logging
from dataclasses import dataclass, field
from typing import Optional
from config import (
    VOLUME_SPIKE_THRESHOLD, VOLUME_LOOKBACK_CANDLES,
    MIN_PRICE_CHANGE_PCT, MAX_PRICE_CHANGE_PCT,
    TAHTACI_MIN_SCORE, POMPA_CONSECUTIVE_CANDLES,
    SILKELEME_DROP_PCT, SILKELEME_RECOVERY_PCT,
    MIN_VOLUME_FILTER,
    W_AKUMULASYON, W_SILKELEME, W_POMPA, W_HACIM_ANOMALI
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Veri Sınıfları
# ─────────────────────────────────────────────────────────────

@dataclass
class FazTespiti:
    akumulasyon:  bool = False
    silkeleme:    bool = False
    pompa:        bool = False
    dagitim:      bool = False
    aktif_faz:    str  = "BELİRSİZ"

@dataclass
class SinyalSonucu:
    ticker:              str
    gecerli:             bool
    tahtaci_skoru:       float       = 0.0
    fiyat:               float       = 0.0
    fiyat_degisim_pct:   float       = 0.0
    hacim_carpani:       float       = 0.0
    ort_hacim:           float       = 0.0
    son_hacim:           float       = 0.0
    faz:                 FazTespiti  = field(default_factory=FazTespiti)

    # Alt skorlar
    akumulasyon_skoru:   float = 0.0
    silkeleme_skoru:     float = 0.0
    pompa_skoru:         float = 0.0
    hacim_skoru:         float = 0.0

    # Detay
    ardisik_yukari_mum:  int   = 0
    mum_sayisi:          int   = 0
    red_flag:            str   = ""


# ─────────────────────────────────────────────────────────────
# Yardımcı Fonksiyonlar
# ─────────────────────────────────────────────────────────────

def _normalize(value: float, min_val: float, max_val: float) -> float:
    """0-100 aralığına normalize eder."""
    if max_val == min_val:
        return 0.0
    return max(0.0, min(100.0, (value - min_val) / (max_val - min_val) * 100))


def _son_kapanis_degisim(df: pd.DataFrame) -> float:
    """Günün ilk fiyatına göre son kapanışın % değişimi."""
    try:
        bugun_baslangic = df["Open"].iloc[-min(8, len(df))]
        son_kapanis     = df["Close"].iloc[-1]
        return (son_kapanis - bugun_baslangic) / bugun_baslangic * 100
    except Exception:
        return 0.0


# ─────────────────────────────────────────────────────────────
# Alt Skor Hesaplayıcıları
# ─────────────────────────────────────────────────────────────

def _hesapla_hacim_skoru(df: pd.DataFrame) -> tuple[float, float, float]:
    """
    Hacim anomali skoru.
    Son mum hacmini son N mumun ortalamasıyla karşılaştırır.
    Döner: (skor 0-100, carpan, ortalama_hacim)
    """
    try:
        hacimler   = df["Volume"].values
        ort_hacim  = np.mean(hacimler[-VOLUME_LOOKBACK_CANDLES:-1])
        son_hacim  = hacimler[-1]

        if ort_hacim < 1:
            return 0.0, 0.0, 0.0

        carpan = son_hacim / ort_hacim

        # Carpan → skor: 1x=0, 3x=50, 5x+=100
        skor = _normalize(carpan, 1.0, 5.0)
        return skor, carpan, ort_hacim

    except Exception:
        return 0.0, 0.0, 0.0


def _hesapla_akumulasyon_skoru(df: pd.DataFrame) -> float:
    """
    Akümülasyon fazı tespiti.
    Düşüklerde uzun alt gölge + kapanış yukarıda → akümülasyon.
    Ek: Hacim var ama fiyat hareket etmiyorsa (baskı eritiliyor).
    """
    try:
        son_n = df.tail(6)
        skorlar = []

        for _, row in son_n.iterrows():
            high   = row["High"]
            low    = row["Low"]
            close  = row["Close"]
            open_  = row["Open"]
            aralik = high - low

            if aralik < 1e-9:
                continue

            # Alt gölge oranı: (close - low) / aralik → 1'e yakın = güçlü alım
            alt_golge_oran = (close - low) / aralik
            skorlar.append(alt_golge_oran * 100)

        if not skorlar:
            return 0.0

        return np.mean(skorlar)

    except Exception:
        return 0.0


def _hesapla_silkeleme_skoru(df: pd.DataFrame) -> tuple[float, bool]:
    """
    Silkeleme (shake-out) tespiti.
    Son N mum içinde: ani düşüş + yüksek hacim + toparlanma.
    Döner: (skor, tespit_edildi_mi)
    """
    try:
        if len(df) < 5:
            return 0.0, False

        # Son 10 mum içinde bak
        pencere = df.tail(10).reset_index(drop=True)
        max_skor = 0.0
        tespit = False

        for i in range(1, len(pencere) - 1):
            onceki_kapanis = pencere["Close"].iloc[i - 1]
            bu_kapanis     = pencere["Close"].iloc[i]
            sonraki_kapanis = pencere["Close"].iloc[i + 1]
            bu_hacim       = pencere["Volume"].iloc[i]

            # Ortalama hacim (bu mum hariç)
            ort = pencere["Volume"].drop(i).mean()
            if ort < 1:
                continue

            hacim_carpan = bu_hacim / ort
            dusus_pct = (onceki_kapanis - bu_kapanis) / onceki_kapanis * 100
            toparlanma_pct = (sonraki_kapanis - bu_kapanis) / bu_kapanis * 100

            if (dusus_pct >= SILKELEME_DROP_PCT and
                    toparlanma_pct >= SILKELEME_RECOVERY_PCT and
                    hacim_carpan >= 2.0):

                # Skor: ne kadar derin düştü + ne kadar hızlı topladı
                skor = min(100.0, (dusus_pct * 10) + (toparlanma_pct * 10) + (hacim_carpan * 5))
                if skor > max_skor:
                    max_skor = skor
                    tespit = True

        return max_skor, tespit

    except Exception:
        return 0.0, False


def _hesapla_pompa_skoru(df: pd.DataFrame) -> tuple[float, int, bool]:
    """
    Pompa fazı tespiti.
    Ardışık yukarı kapanışlar + hacim ivmelenmesi.
    Döner: (skor, ardisik_mum_sayisi, tespit_edildi_mi)
    """
    try:
        kapanislar = df["Close"].values
        hacimler   = df["Volume"].values

        if len(kapanislar) < POMPA_CONSECUTIVE_CANDLES + 1:
            return 0.0, 0, False

        # Ardışık yukarı kapanış say (sondan geriye)
        ardisik = 0
        for i in range(len(kapanislar) - 1, 0, -1):
            if kapanislar[i] > kapanislar[i - 1]:
                ardisik += 1
            else:
                break

        # Hacim ivmeleniyor mu? Son 3 mum artan hacim
        hacim_ivme = False
        if len(hacimler) >= 3:
            hacim_ivme = (hacimler[-1] > hacimler[-2] > hacimler[-3])

        tespit = ardisik >= POMPA_CONSECUTIVE_CANDLES

        # Skor hesabı
        ardisik_skor = min(100.0, ardisik / POMPA_CONSECUTIVE_CANDLES * 60)
        ivme_bonus   = 40.0 if hacim_ivme else 0.0
        skor = ardisik_skor + ivme_bonus if tespit else ardisik_skor * 0.5

        return min(100.0, skor), ardisik, tespit

    except Exception:
        return 0.0, 0, False


def _tespit_dagitim(df: pd.DataFrame) -> bool:
    """
    Dağıtım fazı şüphesi.
    Yüksek hacim + kapanış günün alt yarısında = satış baskısı var.
    """
    try:
        son = df.tail(3)
        for _, row in son.iterrows():
            aralik = row["High"] - row["Low"]
            if aralik < 1e-9:
                continue
            ust_golge_oran = (row["High"] - row["Close"]) / aralik
            if ust_golge_oran > 0.65:
                return True
        return False
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────
# Ana Analiz Fonksiyonu
# ─────────────────────────────────────────────────────────────

def analiz_et(ticker: str, df: pd.DataFrame) -> SinyalSonucu:
    """
    Bir hisse için tam tahtacı analizi yapar.
    """
    sonuc = SinyalSonucu(ticker=ticker, gecerli=False)

    try:
        sonuc.mum_sayisi = len(df)

        # ── Temel filtreler ─────────────────────────────────
        gun_hacmi = df["Volume"].tail(8).sum()
        if gun_hacmi < MIN_VOLUME_FILTER:
            sonuc.red_flag = "Hacim çok düşük"
            return sonuc

        fiyat_degisim = _son_kapanis_degisim(df)

        if abs(fiyat_degisim) < MIN_PRICE_CHANGE_PCT:
            sonuc.red_flag = "Fiyat hareketi yetersiz"
            return sonuc

        if abs(fiyat_degisim) > MAX_PRICE_CHANGE_PCT:
            sonuc.red_flag = "Haber/devre kesici şüphesi"
            return sonuc

        # Sadece alım yönünü takip et
        if fiyat_degisim < 0:
            sonuc.red_flag = "Düşüş yönü (kapsam dışı)"
            return sonuc

        sonuc.fiyat             = float(df["Close"].iloc[-1])
        sonuc.fiyat_degisim_pct = fiyat_degisim
        sonuc.son_hacim         = float(df["Volume"].iloc[-1])

        # ── Alt Skorlar ─────────────────────────────────────
        h_skor, carpan, ort_h       = _hesapla_hacim_skoru(df)
        a_skor                       = _hesapla_akumulasyon_skoru(df)
        s_skor, silkeleme_var        = _hesapla_silkeleme_skoru(df)
        p_skor, ardisik, pompa_var   = _hesapla_pompa_skoru(df)
        dagitim_var                  = _tespit_dagitim(df)

        sonuc.hacim_skoru        = h_skor
        sonuc.akumulasyon_skoru  = a_skor
        sonuc.silkeleme_skoru    = s_skor
        sonuc.pompa_skoru        = p_skor
        sonuc.hacim_carpani      = carpan
        sonuc.ort_hacim          = ort_h
        sonuc.ardisik_yukari_mum = ardisik

        # ── Bileşik Tahtacı Skoru ───────────────────────────
        tahtaci_skoru = (
            a_skor * W_AKUMULASYON +
            s_skor * W_SILKELEME   +
            p_skor * W_POMPA       +
            h_skor * W_HACIM_ANOMALI
        )
        sonuc.tahtaci_skoru = round(tahtaci_skoru, 1)

        # ── Faz Tespiti ─────────────────────────────────────
        faz = FazTespiti()
        faz.akumulasyon = a_skor > 60
        faz.silkeleme   = silkeleme_var
        faz.pompa       = pompa_var
        faz.dagitim     = dagitim_var

        # Aktif faz (öncelik sırası: pompa > silkeleme > akümülasyon > dağıtım)
        if faz.pompa and not faz.dagitim:
            faz.aktif_faz = "POMPA"
        elif faz.silkeleme:
            faz.aktif_faz = "SİLKELEME SONRASI"
        elif faz.akumulasyon:
            faz.aktif_faz = "AKÜMÜLASİYON"
        elif faz.dagitim:
            faz.aktif_faz = "DAĞITIM ŞÜPHESİ"
        else:
            faz.aktif_faz = "BELİRSİZ"

        sonuc.faz = faz

        # ── Son Karar ───────────────────────────────────────
        if tahtaci_skoru >= TAHTACI_MIN_SCORE:
            sonuc.gecerli = True
        else:
            sonuc.red_flag = f"Skor yetersiz ({tahtaci_skoru:.0f} < {TAHTACI_MIN_SCORE})"

    except Exception as e:
        logger.error(f"{ticker} analiz hatası: {e}")
        sonuc.red_flag = f"Analiz hatası: {e}"

    return sonuc


def toplu_analiz(veri_sozlugu: dict) -> list[SinyalSonucu]:
    """
    Tüm hisseler için analiz yapar, skora göre sıralı döner.
    """
    sonuclar = []

    for ticker, df in veri_sozlugu.items():
        sonuc = analiz_et(ticker, df)
        if sonuc.gecerli:
            sonuclar.append(sonuc)

    # Tahtacı skoruna göre sırala
    sonuclar.sort(key=lambda x: x.tahtaci_skoru, reverse=True)

    logger.info(
        f"Analiz tamamlandı. "
        f"{len(veri_sozlugu)} hisse tarandı, "
        f"{len(sonuclar)} sinyal üretildi."
    )
    return sonuclar
