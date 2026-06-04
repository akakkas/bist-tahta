"""
notify_text.py
==============
Bir metin dosyasının içeriğini Telegram'a <pre> bloğu olarak yollar.
Backtest raporu gibi tablo çıktıları için. Sadece standart kütüphane.

Çalıştırma:  python notify_text.py rapor.txt
Ortam değişkenleri:  TELEGRAM_TOKEN, TELEGRAM_CHAT_ID
"""

import os
import sys
import html
import urllib.parse
import urllib.request


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else "rapor.txt"
    token = os.environ.get("TELEGRAM_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("TELEGRAM_TOKEN/CHAT_ID yok; bildirim atlanıyor.", file=sys.stderr)
        return

    try:
        txt = open(path, encoding="utf-8").read()
    except Exception as e:
        txt = f"(rapor okunamadı: {e})"

    # HTML kaçışı + Telegram 4096 sınırına karşı kırp
    txt = html.escape(txt)[:3800]
    msg = "\U0001F4CA <b>Yıldız Backtest Raporu</b>\n<pre>" + txt + "</pre>"

    data = urllib.parse.urlencode({
        "chat_id": chat,
        "text": msg,
        "parse_mode": "HTML",
    }).encode()
    try:
        with urllib.request.urlopen(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data, timeout=30,
        ) as resp:
            if resp.status != 200:
                print(f"Telegram yanıt kodu: {resp.status}", file=sys.stderr)
    except Exception as e:
        print(f"Telegram gönderim hatası: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
