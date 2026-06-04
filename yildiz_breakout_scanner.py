"""
yildiz_breakout_scanner.py
===========================
bist-tahta projesi için ek modül.

Amaç: BİST Yıldız Pazar hisseleri içinde HENÜZ ÇIKIŞ YAPMAMIŞ
(pre-breakout / sessiz birikim - "coil") kâğıtları tespit etmek.

Mantık 6 kritere dayanır, her biri 0..1 arası alt-skora çevrilir,
ağırlıklandırılıp 0..100 toplam skor üretilir:

  1) Konum     : 52h zirvenin altında, dipten uzakta (orta bant)
  2) Sıkışma   : Bollinger bant genişliği 6 ayın en darında + ATR düşüyor
  3) Trend nötr: 50g ortalama yataylaşmış (eğim ~0)
  4) Birikim   : OBV yukarı dönerken fiyat hâlâ yatay (sessiz para girişi)
  5) Hacim     : Yakın ortalama hacim kurumuş + tekil hacim sıçramaları var
  6) Eleme     : Son 60 günde %X+ uçmuşsa "çıkışını yapmış" -> elenir

Veri kaynağı SOYUTTUR (DataProvider). Varsayılan yfinance.
Kendi API'n / İş Yatırım / Matriks için yeni bir Provider yazıp ver.

NOT: Bu bir tarama aracıdır, yatırım tavsiyesi değildir. Çıktı bir
başlangıç listesidir; kararı insan verir.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# 1. VERİ KATMANI  (kaynağı buradan değiştir)
# ---------------------------------------------------------------------------

class DataProvider(Protocol):
    """OHLCV sağlayan her kaynak bu arayüzü uygulamalı.

    Beklenen DataFrame: index = tarih (DatetimeIndex), kolonlar:
    ['open', 'high', 'low', 'close', 'volume'] (küçük harf).
    """
    def fetch(self, symbol: str, lookback_days: int) -> pd.DataFrame:
        ...


class YFinanceProvider:
    """Varsayılan kaynak. BİST sembolleri Yahoo'da '.IS' uzantılıdır:
    THYAO -> THYAO.IS. Sembolü zaten '.IS' ile verirsen dokunmaz."""

    def __init__(self, suffix: str = ".IS"):
        self.suffix = suffix

    def fetch(self, symbol: str, lookback_days: int) -> pd.DataFrame:
        import yfinance as yf  # tembel import: yoksa diğer provider'lar çalışsın

        ticker = symbol if symbol.endswith(self.suffix) else symbol + self.suffix
        # period'i takvim günü olarak alıp biraz pay bırakıyoruz
        period_days = int(lookback_days * 1.6) + 30
        df = yf.download(
            ticker,
            period=f"{period_days}d",
            interval="1d",
            auto_adjust=True,
            progress=False,
        )
        if df is None or df.empty:
            return pd.DataFrame()
        # yfinance bazen MultiIndex kolon döndürür; düzleştir
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df.rename(columns=str.lower)
        keep = ["open", "high", "low", "close", "volume"]
        df = df[[c for c in keep if c in df.columns]].dropna()
        return df


class CSVProvider:
    """Kendi indirdiğin OHLCV dosyaların için. dir/SEMBOL.csv bekler.
    Kolon eşlemesini kendi başlıklarına göre düzenle."""

    def __init__(self, directory: str):
        self.directory = directory.rstrip("/")

    def fetch(self, symbol: str, lookback_days: int) -> pd.DataFrame:
        import os
        path = os.path.join(self.directory, f"{symbol}.csv")
        if not os.path.exists(path):
            return pd.DataFrame()
        df = pd.read_csv(path, parse_dates=[0], index_col=0)
        df = df.rename(columns=str.lower)
        keep = ["open", "high", "low", "close", "volume"]
        df = df[[c for c in keep if c in df.columns]].dropna()
        return df.tail(int(lookback_days * 1.6))


# ---------------------------------------------------------------------------
# 2. İNDİKATÖRLER  (harici TA kütüphanesi gerektirmez)
# ---------------------------------------------------------------------------

def sma(series: pd.Series, n: int) -> pd.Series:
    return series.rolling(n).mean()


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - prev_close).abs(), (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return tr.rolling(n).mean()


def bollinger_bandwidth(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.Series:
    mid = close.rolling(n).mean()
    std = close.rolling(n).std()
    upper, lower = mid + k * std, mid - k * std
    return (upper - lower) / mid  # normalize bant genişliği


def obv(df: pd.DataFrame) -> pd.Series:
    direction = np.sign(df["close"].diff()).fillna(0)
    return (direction * df["volume"]).cumsum()


def slope_normalized(series: pd.Series, n: int) -> float:
    """Son n noktanın lineer regresyon eğimi, fiyat seviyesine göre
    normalize (günlük % eğim). Yataylık testi için kullanılır."""
    y = series.tail(n).dropna().values
    if len(y) < n:
        return np.nan
    x = np.arange(len(y))
    m = np.polyfit(x, y, 1)[0]
    return m / np.mean(y)  # birimsiz: günlük göreli eğim


def percentile_rank(series: pd.Series, value: float) -> float:
    """value'nun series içindeki yüzdelik konumu (0..1)."""
    s = series.dropna()
    if s.empty or np.isnan(value):
        return np.nan
    return float((s < value).mean())


# ---------------------------------------------------------------------------
# 3. KONFİGÜRASYON
# ---------------------------------------------------------------------------

@dataclass
class ScannerConfig:
    lookback_days: int = 260          # ~1 işlem yılı
    bb_window: int = 20
    atr_window: int = 14
    sma_fast: int = 50
    sma_slow: int = 200
    squeeze_lookback: int = 126       # ~6 ay (sıkışma yüzdeliği bu pencerede)

    # Konum (52h)
    min_below_high_pct: float = 0.20  # zirvenin en az %20 altında olmalı
    min_above_low_pct: float = 0.10   # dipten en az %10 yukarıda olmalı

    # Trend yataylığı (50g eğimi mutlak günlük göreli)
    flat_slope_abs: float = 0.0015    # |eğim| bunun altıysa "yatay"

    # Hacim kuruması
    vol_recent_n: int = 10
    vol_base_n: int = 60
    vol_spike_mult: float = 1.8       # baz ortalamanın bu katı = sıçrama

    # Eleme
    max_run_60d_pct: float = 0.40     # son 60g'de bundan fazla uçtuysa ele

    # Ağırlıklar (toplamı önemli değil, normalize edilir)
    w_position: float = 1.0
    w_squeeze: float = 1.4
    w_trend: float = 1.0
    w_accumulation: float = 1.3
    w_volume: float = 0.9

    min_score: float = 55.0           # bu skorun altı listelenmez
    min_rows: int = 220               # yeterli veri yoksa atla


# ---------------------------------------------------------------------------
# 4. TEK HİSSE DEĞERLENDİRMESİ
# ---------------------------------------------------------------------------

@dataclass
class ScanResult:
    symbol: str
    score: float
    passed: bool
    reason: str = ""
    detail: dict = field(default_factory=dict)


def evaluate(symbol: str, df: pd.DataFrame, cfg: ScannerConfig) -> ScanResult:
    if df is None or len(df) < cfg.min_rows:
        return ScanResult(symbol, 0.0, False, "yetersiz veri")

    close = df["close"]
    price = float(close.iloc[-1])

    # --- 52 hafta konum ---
    hi_52 = float(close.tail(cfg.lookback_days).max())
    lo_52 = float(close.tail(cfg.lookback_days).min())
    rng = max(hi_52 - lo_52, 1e-9)
    below_high = (hi_52 - price) / hi_52
    above_low = (price - lo_52) / rng
    # İdeal: zirvenin yeterince altında AMA dipte değil. Orta banda yakınlık ödüllenir.
    pos_band_ok = (below_high >= cfg.min_below_high_pct) and (above_low >= cfg.min_above_low_pct)
    # orta noktaya (0.45) yakınlık -> 1, uçlara -> 0
    pos_score = max(0.0, 1.0 - abs(above_low - 0.45) / 0.45) if pos_band_ok else 0.0

    # --- Sıkışma: Bollinger bant genişliği yüzdeliği + ATR düşüşü ---
    bbw = bollinger_bandwidth(close, cfg.bb_window)
    bbw_now = float(bbw.iloc[-1])
    bbw_pctile = percentile_rank(bbw.tail(cfg.squeeze_lookback), bbw_now)  # düşük = dar
    squeeze_from_bbw = 1.0 - bbw_pctile if not np.isnan(bbw_pctile) else 0.0
    a = atr(df, cfg.atr_window)
    atr_falling = float(a.iloc[-1]) < float(a.tail(cfg.vol_base_n).mean())
    squeeze_score = squeeze_from_bbw * (1.0 if atr_falling else 0.6)

    # --- Trend nötr: 50g yatay, fiyat 50/200 etrafında ---
    fast = sma(close, cfg.sma_fast)
    slow = sma(close, cfg.sma_slow)
    fast_slope = slope_normalized(fast, cfg.sma_fast)
    flat = abs(fast_slope) < cfg.flat_slope_abs if not np.isnan(fast_slope) else False
    # fiyatın ortalamalara yakınlığı (uzaklık ne kadar azsa o kadar nötr)
    near_ma = abs(price - float(fast.iloc[-1])) / price < 0.08 if not np.isnan(fast.iloc[-1]) else False
    trend_score = (0.6 if flat else 0.0) + (0.4 if near_ma else 0.0)

    # --- Birikim: OBV yukarı eğimli, fiyat yatay ---
    o = obv(df)
    obv_slope = slope_normalized(o, cfg.sma_fast)
    price_slope = slope_normalized(close, cfg.sma_fast)
    # OBV pozitif eğilimli + fiyat düz/zayıf -> sessiz toplama
    accumulation_score = 0.0
    if not np.isnan(obv_slope) and not np.isnan(price_slope):
        if obv_slope > 0 and abs(price_slope) < cfg.flat_slope_abs * 1.5:
            accumulation_score = min(1.0, obv_slope / (cfg.flat_slope_abs * 2) )
            accumulation_score = max(0.0, min(1.0, accumulation_score))
        elif obv_slope > 0:
            accumulation_score = 0.4

    # --- Hacim: kuruma + sıçrama ---
    vol = df["volume"]
    v_recent = float(vol.tail(cfg.vol_recent_n).mean())
    v_base = float(vol.tail(cfg.vol_base_n).mean()) or 1.0
    dry_up = v_recent < v_base  # son günler sönük
    spikes = int((vol.tail(cfg.vol_base_n) > v_base * cfg.vol_spike_mult).sum())
    vol_score = (0.6 if dry_up else 0.2) + min(0.4, spikes * 0.1)

    # --- ELEME: zaten uçmuş mu? ---
    p_60 = float(close.tail(60).iloc[0])
    run_60 = (price - p_60) / p_60
    if run_60 > cfg.max_run_60d_pct:
        return ScanResult(
            symbol, 0.0, False,
            f"elendi: son 60g +%{run_60*100:.0f} (çıkışını yapmış)",
            {"run_60d": run_60},
        )

    # --- Toplam skor ---
    weights = np.array([cfg.w_position, cfg.w_squeeze, cfg.w_trend,
                        cfg.w_accumulation, cfg.w_volume])
    subs = np.array([pos_score, squeeze_score, trend_score,
                     accumulation_score, vol_score])
    score = float((subs * weights).sum() / weights.sum() * 100)

    detail = {
        "fiyat": round(price, 4),
        "zirve_alti_%": round(below_high * 100, 1),
        "52h_konum": round(above_low, 2),
        "bbw_yuzdelik": round(bbw_pctile, 2) if not np.isnan(bbw_pctile) else None,
        "atr_dusuyor": atr_falling,
        "50g_yatay": flat,
        "obv_egim": round(obv_slope, 5) if not np.isnan(obv_slope) else None,
        "hacim_kurudu": dry_up,
        "hacim_sicrama_say": spikes,
        "son60g_%": round(run_60 * 100, 1),
        "alt_skorlar": {
            "konum": round(pos_score, 2),
            "sikisma": round(squeeze_score, 2),
            "trend": round(trend_score, 2),
            "birikim": round(accumulation_score, 2),
            "hacim": round(vol_score, 2),
        },
    }
    passed = score >= cfg.min_score
    return ScanResult(symbol, round(score, 1), passed, "", detail)


# ---------------------------------------------------------------------------
# 5. TARAYICI
# ---------------------------------------------------------------------------

def scan(symbols: list[str], provider: DataProvider,
         cfg: ScannerConfig | None = None) -> pd.DataFrame:
    cfg = cfg or ScannerConfig()
    rows = []
    for i, sym in enumerate(symbols, 1):
        try:
            df = provider.fetch(sym, cfg.lookback_days)
            res = evaluate(sym, df, cfg)
        except Exception as e:  # bir hisse patlarsa tüm tarama durmasın
            res = ScanResult(sym, 0.0, False, f"hata: {e}")
        rows.append(res)
        print(f"[{i}/{len(symbols)}] {sym:10s} "
              f"skor={res.score:5.1f} "
              f"{'GEÇTİ' if res.passed else res.reason or '-'}",
              file=sys.stderr)

    data = [{
        "sembol": r.symbol,
        "skor": r.score,
        "gecti": r.passed,
        "not": r.reason,
        **{k: v for k, v in r.detail.items() if k != "alt_skorlar"},
    } for r in rows]
    out = pd.DataFrame(data).sort_values("skor", ascending=False).reset_index(drop=True)
    return out


def load_universe(path: str | None) -> list[str]:
    """Yıldız Pazar sembol listesini dosyadan yükle (her satır bir sembol).
    Listeyi BİST günlük pazar dosyasından ya da kendi bist-tahta
    veri tabanından güncel tut — pazar üyeliği değişir."""
    if path:
        with open(path, encoding="utf-8") as f:
            return [ln.strip().upper() for ln in f if ln.strip() and not ln.startswith("#")]
    # Yedek: yalnızca DEMO amaçlı örnek semboller.
    # !!! Pazar üyeliği zamanla değişir; üretimde mutlaka güncel liste yükle. !!!
    return ["THYAO", "ASELS", "KCHOL", "EREGL", "SISE",
            "TUPRS", "BIMAS", "SAHOL", "FROTO", "TCELL"]


def main() -> None:
    p = argparse.ArgumentParser(
        description="BİST Yıldız Pazar pre-breakout / birikim tarayıcı")
    p.add_argument("--universe", help="Sembol listesi dosyası (her satır 1 sembol)")
    p.add_argument("--source", choices=["yfinance", "csv"], default="yfinance")
    p.add_argument("--csv-dir", help="CSVProvider için klasör")
    p.add_argument("--min-score", type=float, default=55.0)
    p.add_argument("--out", help="Sonucu CSV olarak kaydet")
    p.add_argument("--only-passed", action="store_true",
                   help="Yalnızca eşik üstü geçenleri göster")
    args = p.parse_args()

    cfg = ScannerConfig(min_score=args.min_score)
    if args.source == "csv":
        if not args.csv_dir:
            p.error("--source csv için --csv-dir gerekli")
        provider: DataProvider = CSVProvider(args.csv_dir)
    else:
        provider = YFinanceProvider()

    symbols = load_universe(args.universe)
    result = scan(symbols, provider, cfg)

    if args.only_passed:
        result = result[result["gecti"]].reset_index(drop=True)

    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 200)
    print(result.to_string(index=False))

    if args.out:
        result.to_csv(args.out, index=False, encoding="utf-8-sig")
        print(f"\nKaydedildi: {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
