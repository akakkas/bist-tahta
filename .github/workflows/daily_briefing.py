"""
Günlük Makroekonomi Bülteni
Her sabah 08:00 (TR) çalışır, FMP ekonomi takvimini çeker,
Gemini ile BIST yorumu üretir, Telegram'a gönderir.

Gerekli GitHub Secrets:
  FMP_API_KEY       → financialmodelingprep.com (ücretsiz)
  GEMINI_API_KEY    → zaten mevcut
  TELEGRAM_BOT_TOKEN → zaten mevcut
  TELEGRAM_CHAT_ID   → zaten mevcut
"""

import os
import sys
import requests
from datetime import date, datetime, timezone, timedelta
import google.generativeai as genai

# ── Sabitler ──────────────────────────────────────────────
FMP_API_KEY        = os.environ.get("FMP_API_KEY", "")
GEMINI_API_KEY     = os.environ.get("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

TR_OFFSET = timedelta(hours=3)

# BIST açısından önemli ülkeler
COUNTRY_EMOJI = {
    "US": "🇺🇸", "EU": "🇪🇺", "TR": "🇹🇷",
    "DE": "🇩🇪", "GB": "🇬🇧", "CN": "🇨🇳",
    "JP": "🇯🇵", "FR": "🇫🇷", "IT": "🇮🇹",
    "RU": "🇷🇺", "SA": "🇸🇦",
}

# Sadece bu ülkelerin verilerini al (gereksiz olanları filtrele)
RELEVANT_COUNTRIES = set(COUNTRY_EMOJI.keys())


# ── Takvim Verisi ─────────────────────────────────────────
def fetch_calendar() -> list:
    today = date.today().strftime("%Y-%m-%d")
    url = (
        f"https://financialmodelingprep.com/api/v3/economic_calendar"
        f"?from={today}&to={today}&apikey={FMP_API_KEY}"
    )
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        print(f"FMP yanıtı beklenmedik format: {data}")
        return []
    except Exception as e:
        print(f"FMP hatası: {e}")
        return []


def filter_events(events: list) -> list:
    """Yüksek/Orta etkili, ilgili ülke olaylarını filtrele."""
    filtered = []
    for e in events:
        impact  = e.get("impact", "")
        country = e.get("country", "").upper()
        if impact in ("High", "Medium") and country in RELEVANT_COUNTRIES:
            filtered.append(e)

    # Önce yüksek, sonra orta; zaman içinde sırala
    filtered.sort(key=lambda x: (
        0 if x.get("impact") == "High" else 1,
        x.get("date", "")
    ))
    return filtered


def utc_to_tr(date_str: str) -> str:
    """'2026-06-05 08:30:00' → '11:30' (TR saati)"""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        dt_tr = dt.replace(tzinfo=timezone.utc) + TR_OFFSET
        return dt_tr.strftime("%H:%M")
    except Exception:
        return date_str[-8:-3] if len(date_str) >= 8 else "?"


# ── Gemini Analizi ────────────────────────────────────────
def analyze_with_gemini(events: list) -> str:
    if not events:
        return "Bugün önemli ekonomik veri açıklaması yok."

    lines = []
    for e in events:
        country  = e.get("country", "")
        name     = e.get("event", "")
        impact   = e.get("impact", "")
        estimate = e.get("estimate", "")
        previous = e.get("previous", "")
        actual   = e.get("actual", "")
        time_tr  = utc_to_tr(e.get("date", ""))

        line = f"[{impact}] {time_tr} {country}: {name}"
        parts = []
        if actual:   parts.append(f"açıklanan: {actual}")
        if estimate: parts.append(f"beklenti: {estimate}")
        if previous: parts.append(f"önceki: {previous}")
        if parts:    line += " (" + ", ".join(parts) + ")"
        lines.append(line)

    events_text = "\n".join(lines)

    prompt = f"""Sen deneyimli bir BIST (Borsa İstanbul) analistisin. 
Bugün açıklanacak / açıklanan küresel ve Türkiye ekonomik verileri:

{events_text}

Bu verileri aşağıdaki çerçevede Türkçe ve net yorumla:
1. Genel BIST yön baskısı (yukarı / aşağı / yatay) ve kısa gerekçe
2. En kritik 2-3 verinin BIST üzerindeki olası etkisi
3. TL ve EM risk iştahına yansıması (varsa)
4. Dikkat edilmesi gereken sektör veya hisse tipi (varsa)

Maksimum 7 cümle, sade ve direkt yaz."""

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model    = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"Gemini hatası: {e}")
        return "Gemini analizi alınamadı."


# ── Telegram Mesajı ───────────────────────────────────────
def build_message(events: list, analysis: str) -> str:
    today_str = datetime.now(timezone.utc).astimezone(
        timezone(TR_OFFSET)
    ).strftime("%d %B %Y")

    msg = f"📅 <b>GÜNLÜK MAKROEKONOMİ TAKVİMİ</b>\n{today_str}\n"

    high   = [e for e in events if e.get("impact") == "High"]
    medium = [e for e in events if e.get("impact") == "Medium"]

    def format_event(e):
        country = e.get("country", "").upper()
        flag    = COUNTRY_EMOJI.get(country, "🌍")
        name    = e.get("event", "")
        time_tr = utc_to_tr(e.get("date", ""))
        estimate = e.get("estimate", "")
        est_str  = f" <i>(beklenti: {estimate})</i>" if estimate else ""
        return f"• {time_tr} {flag} {name}{est_str}"

    if high:
        msg += "\n🔴 <b>YÜKSEK ETKİ</b>\n"
        for e in high:
            msg += format_event(e) + "\n"

    if medium:
        msg += "\n🟡 <b>ORTA ETKİ</b>\n"
        for e in medium[:6]:   # kalabalık olmasın
            msg += format_event(e) + "\n"

    if not high and not medium:
        msg += "\nℹ️ Bugün önemli veri açıklaması yok.\n"

    msg += f"\n🤖 <b>GEMİNİ YORUMU</b>\n{analysis}"
    return msg


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
    print("Ekonomi takvimi çekiliyor...")
    raw    = fetch_calendar()
    events = filter_events(raw)
    print(f"{len(events)} önemli olay filtrelendi.")

    print("Gemini analizi yapılıyor...")
    analysis = analyze_with_gemini(events)

    message = build_message(events, analysis)
    print("Telegram'a gönderiliyor...")
    send_telegram(message)
    print("Tamamlandı.")


if __name__ == "__main__":
    main()
