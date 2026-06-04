"""
notify_yildiz.py
================
yildiz_breakout_scanner.py'nin ürettiği sonuc.csv'yi okuyup özetini
Telegram'a yollar. Yalnızca standart kütüphane kullanır (ek paket yok).

Mevcut telegram_bot.py'ndan ayrı tutuldu ki eski tahtacı botuyla
çakışmasın. İstersen kendi telegram_bot.py'ndaki fonksiyonu da çağırabilirsin.

Çalıştırma:  python notify_yildiz.py sonuc.csv
Ortam değişkenleri (GitHub Secrets):  TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
"""

import os
import sys
import urllib.parse
import urllib.request

import pandas as pd

MAX_ROWS = 15  # Telegram mesajını şişirmemek için en yüksek skorlu N hisse


def send(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    with urllib.request.urlopen(url, data=data, timeout=30) as resp:
        if resp.status != 200:
            print(f"Telegram yanıt kodu: {resp.status}", file=sys.stderr)


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "sonuc.csv"
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("TELEGRAM_TOKEN/CHAT_ID bulunamadı; bildirim atlanıyor.",
              file=sys.stderr)
        return

    try:
        df = pd.read_csv(path, encoding="utf-8-sig")
    except Exception:
        df = None

    if df is None or df.empty:
        send(token, chat_id,
             "📡 <b>Yıldız Pre-Breakout</b>\nBugün eşik üstü sinyal yok.")
        return

    if "gecti" in df.columns:
        df = df[df["gecti"]]
    if df.empty:
        send(token, chat_id,
             "📡 <b>Yıldız Pre-Breakout</b>\nBugün eşik üstü sinyal yok.")
        return

    df = df.sort_values("skor", ascending=False).head(MAX_ROWS)
    lines = ["📡 <b>Yıldız Pre-Breakout Sinyalleri</b>", ""]
    for _, r in df.iterrows():
        zirve = r.get("zirve_alti_%", "?")
        spike = r.get("hacim_sicrama_say", "?")
        lines.append(
            f"• <b>{r['sembol']}</b>  skor {float(r['skor']):.0f}"
            f"  · zirve altı %{zirve}  · hacim sıçrama {spike}"
        )
    lines += ["", "⚠️ Yatırım tavsiyesi değildir — kendi analizini yap."]
    send(token, chat_id, "\n".join(lines))


if __name__ == "__main__":
    main()
