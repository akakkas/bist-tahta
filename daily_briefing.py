"""
Günlük Makroekonomi Bülteni
ForexFactory ücretsiz takvimi + google.genai + Telegram

Gerekli GitHub Secrets:
  GEMINI_API_KEY
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID
"""

import os
import sys
import requests
from datetime import date, datetime, timezone, timedelta
import warnings
warnings.filterwarnings("ignore")
import google.generativeai as genai

# ── Config ────────────────────────────────────────────────
GEMINI_API_KEY     = os.environ.get("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

# ForexFactory döviz kodu → bayrak + isim
CURRENCY_META = {
    "USD": ("🇺🇸", "ABD"),
    "EUR": ("🇪🇺", "Euro Bölgesi"),
    "GBP": ("🇬🇧", "İngiltere"),
    "JPY": ("🇯🇵", "Japonya"),
    "CNY": ("🇨🇳", "Çin"),
    "CHF": ("🇨🇭", "İsviçre"),
    "AUD": ("🇦🇺", "Avustralya"),
    "CAD": ("🇨🇦", "Kanada"),
}

BIST_RELEVANT = {"USD", "EUR", "GBP", "JPY", "CNY"}


# ── Takvim Verisi ─────────────────────────────────────────
def fetch_calendar() -> list:
    try:
        resp = requests.get(
            CALENDAR_URL,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Takvim verisi alınamadı: {e}")
        return []


def filter_today(events: list) -> list:
    today = date.today()
    result = []
    for e in events:
        try:
            event_date = datetime.strptime(e.get("date", ""), "%b %d, %Y").date()
        except Exception:
            continue
        impact   = e.get("impact", "")
        currency = e.get("country", "")  # FF'de 'country' aslında döviz kodu
        if event_date == today and impact in ("High", "Medium") and currency in BIST_RELEVANT:
            result.append(e)

    # Yüksek önce, sonra zaman sırasına göre
    result.sort(key=lambda x: (
        0 if x.get("impact") == "High" else 1,
        x.get("time", "")
    ))
    return result


# ── Gemini Analizi ────────────────────────────────────────
def analyze_with_gemini(events: list) -> str:
    if not events:
        return "Bugün BIST açısından önemli ekonomik veri açıklaması yok."

    lines = []
    for e in events:
        currency = e.get("country", "")
        name     = e.get("title", "")
        impact   = e.get("impact", "")
        forecast = e.get("forecast", "")
        previous = e.get("previous", "")
        actual   = e.get("actual", "")
        time_et  = e.get("time", "")

        line = f"[{impact}] {time_et} ET | {currency}: {name}"
        parts = []
        if actual:   parts.append(f"açıklanan: {actual}")
        if forecast: parts.append(f"beklenti: {forecast}")
        if previous: parts.append(f"önceki: {previous}")
        if parts:    line += " (" + ", ".join(parts) + ")"
        lines.append(line)

    events_text = "\n".join(lines)

    prompt = f"""Sen deneyimli bir BIST (Borsa İstanbul) analistisin.
Bugün açıklanacak / açıklanan küresel ekonomik veriler (saatler ET = New York):

{events_text}

Bu verileri BIST açısından Türkçe ve net yorumla:
1. Genel BIST yön baskısı (yukarı / aşağı / yatay) ve kısa gerekçe
2. En kritik 2-3 verinin BIST üzerindeki olası etkisi
3. TL ve EM risk iştahına yansıması
4. Dikkat edilmesi gereken sektör veya tema (varsa)

Maksimum 7 cümle, sade ve direkt yaz."""

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model    = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Gemini hatası: {e}")
        return "Gemini analizi alınamadı."


# ── Mesaj Oluştur ─────────────────────────────────────────
def build_message(events: list, analysis: str) -> str:
    today_str = date.today().strftime("%d.%m.%Y")

    msg  = f"📅 <b>GÜNLÜK MAKROEKONOMİ TAKVİMİ</b> — {today_str}\n"
    msg += "<i>(Saatler New York / ET)</i>\n"

    high   = [e for e in events if e.get("impact") == "High"]
    medium = [e for e in events if e.get("impact") == "Medium"]

    def fmt(e):
        currency = e.get("country", "")
        flag, _  = CURRENCY_META.get(currency, ("🌍", currency))
        name     = e.get("title", "")
        time_et  = e.get("time", "")
        forecast = e.get("forecast", "")
        est_str  = f" <i>(beklenti: {forecast})</i>" if forecast else ""
        return f"• {time_et} {flag} {name}{est_str}"

    if high:
        msg += "\n🔴 <b>YÜKSEK ETKİ</b>\n"
        for e in high:
            msg += fmt(e) + "\n"

    if medium:
        msg += "\n🟡 <b>ORTA ETKİ</b>\n"
        for e in medium[:5]:
            msg += fmt(e) + "\n"

    if not high and not medium:
        msg += "\nℹ️ Bugün BIST için önemli veri yok.\n"

    msg += f"\n🤖 <b>GEMİNİ YORUMU</b>\n{analysis}"
    return msg


# ── Telegram ──────────────────────────────────────────────
def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id":    TELEGRAM_CHAT_ID,
        "text":       message,
        "parse_mode": "HTML",
    }
    try:
        resp = requests.post(url, json=payload, timeout=20)
        resp.raise_for_status()
        print("Telegram mesajı gönderildi.")
    except Exception as e:
        print(f"Telegram hatası: {e}")
        sys.exit(1)


# ── Ana Akış ──────────────────────────────────────────────
def main():
    print("Takvim çekiliyor (ForexFactory)...")
    raw    = fetch_calendar()
    events = filter_today(raw)
    print(f"{len(events)} önemli olay bulundu.")

    print("Gemini analizi yapılıyor...")
    analysis = analyze_with_gemini(events)

    message = build_message(events, analysis)
    print("Telegram'a gönderiliyor...")
    send_telegram(message)
    print("Tamamlandı.")


if __name__ == "__main__":
    main()
