"""
liste_uret.py — BİST hisse evrenini pykap ile çekip hisse_listesi.py'yi yeniden üretir.

Çalıştırma:  python liste_uret.py
Bağımlılık:  pip install pykap

Davranış:
  1) pykap online (canlı KAP) dener — en taze liste.
  2) Olmazsa pykap bundled (offline) veriye düşer — yine de tam liste.
  3) Sonuç >= MIN_HISSE ise hisse_listesi.py'yi baştan yazar; değilse DOKUNMAZ.
"""

import sys
import pykap

HEDEF = "hisse_listesi.py"
MIN_HISSE = 400

SABLON = '''"""
hisse_listesi.py — BİST hisse evreni.

!!! BU DOSYA OTOMATİK ÜRETİLİR — ELLE DÜZENLEME !!!
Kaynak: KAP (pykap), liste_uret.py ile üretildi.
Toplam: {adet} hisse
"""

BIST_TICKERS = [
{satirlar}
]


def get_tickers():
    return BIST_TICKERS


if __name__ == "__main__":
    print(f"Toplam {{len(BIST_TICKERS)}} hisse yüklendi.")
'''


def _tickerlari_al(online: bool) -> list[str]:
    df = pykap.get_bist_companies(online=online)
    ticks = [str(t).strip().upper() for t in df["ticker"].dropna()]
    return sorted({f"{t}.IS" for t in ticks if t})


def liste_cek() -> list[str]:
    # 1) Canlı dene
    try:
        ticks = _tickerlari_al(online=True)
        if len(ticks) >= MIN_HISSE:
            print(f"Canlı KAP listesi alındı: {len(ticks)}")
            return ticks
        print(f"Canlı liste kısa ({len(ticks)}), bundled'a düşülüyor.", file=sys.stderr)
    except Exception as e:
        print(f"Canlı KAP alınamadı ({e}), bundled'a düşülüyor.", file=sys.stderr)

    # 2) Bundled (offline) fallback
    ticks = _tickerlari_al(online=False)
    print(f"Bundled liste alındı: {len(ticks)}")
    return ticks


def dosya_yaz(semboller: list[str]) -> None:
    satirlar = []
    for i in range(0, len(semboller), 6):
        grup = ", ".join(f'"{s}"' for s in semboller[i:i + 6])
        satirlar.append(f"    {grup},")
    icerik = SABLON.format(adet=len(semboller), satirlar="\n".join(satirlar))
    with open(HEDEF, "w", encoding="utf-8") as f:
        f.write(icerik)


def main() -> int:
    try:
        semboller = liste_cek()
    except Exception as e:
        print(f"HATA: liste hiç alınamadı: {e}", file=sys.stderr)
        return 1

    if len(semboller) < MIN_HISSE:
        print(f"HATA: sadece {len(semboller)} hisse (< {MIN_HISSE}). "
              f"{HEDEF} DEĞİŞTİRİLMEDİ.", file=sys.stderr)
        return 1

    dosya_yaz(semboller)
    print(f"OK → {HEDEF} güncellendi ({len(semboller)} hisse).")
    print("VAKFA.IS listede mi?", "VAKFA.IS" in semboller)
    return 0


if __name__ == "__main__":
    sys.exit(main())
