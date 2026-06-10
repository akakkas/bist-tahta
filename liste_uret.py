"""
liste_uret.py — BİST hisse evrenini KAP'tan çekip hisse_listesi.py'yi yeniden üretir.

Çalıştırma:
    python liste_uret.py

Davranış:
  - KAP bist-sirketler sayfasından TÜM BİST hisse kodlarını çeker.
  - >= MIN_HISSE kod bulursa hisse_listesi.py'yi baştan yazar.
  - Daha az bulursa HATA verir ve dosyaya DOKUNMAZ (mevcut liste korunur).

Scanner bu dosyayı çalıştırmaz; sadece haftalık generator (CI) çalıştırır.
Scanner runtime'da yalnızca hisse_listesi.get_tickers() okur — ağ yok, risk yok.
"""

import re
import sys

import requests

KAP_URL = "https://kap.org.tr/tr/bist-sirketler"
HEDEF = "hisse_listesi.py"
MIN_HISSE = 400          # bundan az gelirse güvenme, dosyayı yazma
TIMEOUT = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9",
}

# Şirket özet linkinin metni saf kod (3-6 büyük harf) ise yakala.
# Şirket adı / denetçi adı uzun olduğu için elenir.
KOD_RE = re.compile(r'/sirket-bilgileri/ozet/[^"\']*"[^>]*>\s*([A-Z]{3,6})\s*<')

SABLON = '''"""
hisse_listesi.py — BİST hisse evreni.

!!! BU DOSYA OTOMATİK ÜRETİLİR — ELLE DÜZENLEME !!!
Kaynak: {kaynak}
Üretim: liste_uret.py (haftalık CI ile yenilenir)
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


def kap_listesi_cek() -> list[str]:
    r = requests.get(KAP_URL, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    kodlar = KOD_RE.findall(r.text)
    semboller = sorted({f"{k}.IS" for k in kodlar})
    return semboller


def dosya_yaz(semboller: list[str]) -> None:
    # 6'şarlı satırlar, hizalı
    satirlar = []
    for i in range(0, len(semboller), 6):
        grup = ", ".join(f'"{s}"' for s in semboller[i:i + 6])
        satirlar.append(f"    {grup},")
    icerik = SABLON.format(
        kaynak=KAP_URL,
        adet=len(semboller),
        satirlar="\n".join(satirlar),
    )
    with open(HEDEF, "w", encoding="utf-8") as f:
        f.write(icerik)


def main() -> int:
    print(f"KAP'tan liste çekiliyor: {KAP_URL}")
    try:
        semboller = kap_listesi_cek()
    except Exception as e:
        print(f"HATA: KAP'tan liste çekilemedi: {e}", file=sys.stderr)
        return 1

    print(f"Bulunan hisse sayısı: {len(semboller)}")

    if len(semboller) < MIN_HISSE:
        print(
            f"HATA: Sadece {len(semboller)} kod bulundu (< {MIN_HISSE}). "
            f"Sayfa JS-render ediyor olabilir veya markup değişti. "
            f"{HEDEF} DEĞİŞTİRİLMEDİ.",
            file=sys.stderr,
        )
        return 1

    dosya_yaz(semboller)
    print(f"OK → {HEDEF} güncellendi ({len(semboller)} hisse).")
    print("VAKFA.IS listede mi?", "VAKFA.IS" in semboller)
    return 0


if __name__ == "__main__":
    sys.exit(main())
