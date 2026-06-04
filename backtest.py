"""
backtest.py
===========
yildiz_breakout_scanner.py için doğrulama (validation) harness'ı.

Soru: Tarayıcının "GEÇTİ" dediği hisseler, sonraki 20-40 günde
gerçekten kırılım/çıkış yaptı mı? Yoksa skor gürültü mü?

Yöntem (lookahead bias YOK):
  - Her hisse için TÜM geçmişi bir kez çek.
  - Test aralığında belirli aralıklarla (step) değerlendirme tarihleri seç.
  - Her (tarih, sembol) için: veriyi O GÜNE KADAR kes -> evaluate() çalıştır.
    (evaluate sadece trailing pencereler ve .iloc[-1] kullandığı için
     dilimi kesmek geleceği otomatik gizler.)
  - Sonra ileriye bak: +forward_days içindeki getiriyi ve maksimum
    lehte hareketi ölç. "hit" = ileri max getiri >= target_pct.
  - GEÇENLER ile TÜM değerlendirilenler (baseline) karşılaştır.
    Tarayıcının bir KENARI (edge) varsa, geçenlerin hit oranı ve
    ortalama ileri getirisi baseline'ı belirgin biçimde aşmalı.

NOT: İstatistiksel bir kenar görmek, gelecekte kâr garantisi değildir.
Yatırım tavsiyesi değildir.
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

from yildiz_breakout_scanner import (
    ScannerConfig,
    DataProvider,
    YFinanceProvider,
    CSVProvider,
    evaluate,
    load_universe,
)


# ---------------------------------------------------------------------------
# İleri getiri ölçümü
# ---------------------------------------------------------------------------

def forward_metrics(close: pd.Series, idx: int, forward_days: int,
                    horizons=(20, 40)) -> dict:
    """idx konumundan ileriye bakıp getirileri hesapla.
    close: tüm seri. idx: değerlendirme gününün konumu."""
    entry = float(close.iloc[idx])
    end = min(idx + forward_days, len(close) - 1)
    window = close.iloc[idx + 1: end + 1]
    if window.empty:
        return {}
    fwd_max_ret = float(window.max() / entry - 1.0)
    fwd_min_ret = float(window.min() / entry - 1.0)
    out = {"fwd_max_ret": fwd_max_ret, "fwd_min_ret": fwd_min_ret}
    for h in horizons:
        j = idx + h
        out[f"fwd_ret_{h}"] = (float(close.iloc[j] / entry - 1.0)
                               if j < len(close) else np.nan)
    return out


# ---------------------------------------------------------------------------
# Backtest çekirdeği
# ---------------------------------------------------------------------------

def backtest(symbols: list[str], provider: DataProvider,
             cfg: ScannerConfig,
             start: str, end: str,
             step: int = 5,
             forward_days: int = 40,
             target_pct: float = 0.15,
             history_days: int = 900) -> pd.DataFrame:
    """Her (değerlendirme_tarihi, sembol) için bir satır döndürür."""
    rows = []
    start_ts, end_ts = pd.Timestamp(start), pd.Timestamp(end)

    for n, sym in enumerate(symbols, 1):
        try:
            df = provider.fetch(sym, history_days)
        except Exception as e:
            print(f"[{n}/{len(symbols)}] {sym}: çekme hatası {e}", file=sys.stderr)
            continue
        if df is None or len(df) < cfg.min_rows + forward_days + 1:
            print(f"[{n}/{len(symbols)}] {sym}: yetersiz geçmiş", file=sys.stderr)
            continue

        close = df["close"]
        # Değerlendirme tarihleri: test aralığında, ileride forward_days
        # barı kalacak ve geride min_rows barı olacak şekilde.
        positions = range(cfg.min_rows, len(df) - forward_days, step)
        n_eval = 0
        for pos in positions:
            date = df.index[pos]
            if not (start_ts <= date <= end_ts):
                continue
            sub = df.iloc[: pos + 1]          # O GÜNE KADAR (dahil) -> no lookahead
            res = evaluate(sym, sub, cfg)
            if res.score == 0.0 and res.reason.startswith(("yetersiz", "hata")):
                continue
            fwd = forward_metrics(close, pos, forward_days)
            if not fwd:
                continue
            rows.append({
                "sembol": sym,
                "tarih": date.date(),
                "skor": res.score,
                "gecti": res.passed,
                "elendi": res.reason.startswith("elendi"),
                "hit": fwd["fwd_max_ret"] >= target_pct,
                **fwd,
            })
            n_eval += 1
        print(f"[{n}/{len(symbols)}] {sym:10s} {n_eval} değerlendirme",
              file=sys.stderr)

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Özet / kenar analizi
# ---------------------------------------------------------------------------

def summarize(trades: pd.DataFrame, target_pct: float) -> None:
    if trades.empty:
        print("Sonuç yok. Tarih aralığını / universe'i kontrol et.")
        return

    # Eleneni baseline dışında tut (zaten 'çıkışını yapmış' grubu)
    base = trades[~trades["elendi"]]
    passed = trades[trades["gecti"]]

    def block(name: str, d: pd.DataFrame) -> None:
        if d.empty:
            print(f"\n[{name}] örnek yok"); return
        print(f"\n[{name}]  n={len(d)}")
        print(f"  hit oranı (ileri max >= %{target_pct*100:.0f}) : "
              f"%{d['hit'].mean()*100:5.1f}")
        for h in (20, 40):
            col = f"fwd_ret_{h}"
            if col in d:
                print(f"  +{h}g getiri  ort=%{d[col].mean()*100:6.2f}  "
                      f"medyan=%{d[col].median()*100:6.2f}")
        print(f"  ileri max getiri ort=%{d['fwd_max_ret'].mean()*100:6.2f}  "
              f"ileri min getiri ort=%{d['fwd_min_ret'].mean()*100:6.2f}")

    print("=" * 60)
    print("KENAR (EDGE) ANALİZİ — geçenler baseline'ı aşmalı")
    print("=" * 60)
    block("BASELINE (tüm değerlendirmeler, eleme hariç)", base)
    block("GEÇENLER (tarayıcı sinyali)", passed)

    # Lift: geçenlerin hit oranının baseline'a oranı
    if not base.empty and not passed.empty and base["hit"].mean() > 0:
        lift = passed["hit"].mean() / base["hit"].mean()
        print(f"\n>>> LIFT (hit): geçenler baseline'ın {lift:.2f}x'i "
              f"({'KENAR VAR' if lift > 1.15 else 'belirgin kenar yok'})")

    # Skor decile bazında hit oranı: skor anlamlı mı?
    print("\n[Skor dilimi bazında hit oranı] — monoton artış istenir")
    valid = base.dropna(subset=["skor"])
    if len(valid) >= 20:
        valid = valid.copy()
        valid["dilim"] = pd.qcut(valid["skor"], 5, duplicates="drop")
        tab = valid.groupby("dilim", observed=True).agg(
            n=("hit", "size"),
            hit_orani=("hit", "mean"),
            ort_fwd40=("fwd_ret_40", "mean"),
        )
        tab["hit_orani"] = (tab["hit_orani"] * 100).round(1)
        tab["ort_fwd40"] = (tab["ort_fwd40"] * 100).round(2)
        print(tab.to_string())
    else:
        print("  (yeterli örnek yok)")


def main() -> None:
    p = argparse.ArgumentParser(description="Yıldız Pazar tarayıcı backtest")
    p.add_argument("--universe")
    p.add_argument("--source", choices=["yfinance", "csv"], default="yfinance")
    p.add_argument("--csv-dir")
    p.add_argument("--start", default="2023-01-01")
    p.add_argument("--end", default="2025-01-01")
    p.add_argument("--step", type=int, default=5, help="değ. tarihi aralığı (bar)")
    p.add_argument("--forward-days", type=int, default=40)
    p.add_argument("--target-pct", type=float, default=0.15, help="kırılım eşiği")
    p.add_argument("--min-score", type=float, default=55.0)
    p.add_argument("--out", help="işlem bazında CSV")
    args = p.parse_args()

    cfg = ScannerConfig(min_score=args.min_score)
    if args.source == "csv":
        if not args.csv_dir:
            p.error("--source csv için --csv-dir gerekli")
        provider: DataProvider = CSVProvider(args.csv_dir)
    else:
        provider = YFinanceProvider()

    symbols = load_universe(args.universe)
    trades = backtest(
        symbols, provider, cfg,
        start=args.start, end=args.end,
        step=args.step, forward_days=args.forward_days,
        target_pct=args.target_pct,
    )
    summarize(trades, args.target_pct)

    if args.out and not trades.empty:
        trades.to_csv(args.out, index=False, encoding="utf-8-sig")
        print(f"\nİşlem detayı kaydedildi: {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
