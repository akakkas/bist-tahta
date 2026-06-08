"""
Günlük Makroekonomi Bülteni
Her sabah 08:00 (TR) çalışır, ForexFactory haftalık ekonomi takvimini çeker,
bugünün önemli olaylarını süzer, Gemini ile BIST yorumu üretir, Telegram'a yollar.

Gerekli GitHub Secrets:
  GEMINI_API_KEY     → aistudio.google.com
  TELEGRAM_BOT_TOKEN → mevcut
  TELEGRAM_CHAT_ID   → mevcut
(FMP_API_KEY ARTIK GEREKMİYOR — ForexFactory ücretsiz, anahtarsız.)
"""

import os
import sys
import requests
from datetime import datetime, timezone, timedelta
from google import genai

# ── Sabitler ──────────────────────────────────────────────
GEMINI_API_KEY     = os.environ.get("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID", "")

TR_TZ = timezone(timedelta(hours=3))

# ForexFactory haftalık takvim (anahtarsız, ücretsiz mirror)
FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

# ForexFactory para birimi kodu → bayrak. BIST açısından önemli olanlar.
CURRENCY_EMOJI = {
    "USD": "🇺🇸", "EUR": "🇪🇺", "GBP": "🇬🇧",
    "JPY": "🇯🇵", "CNY": "🇨🇳", "TRY": "🇹🇷",
    "CHF": "🇨🇭", "CAD": "🇨🇦",
}
RELEVANT = set(CURRENCY_EMOJI.keys())


# ── Takvim Verisi ─────────────────────────────────────────
def fetch_calendar() -> list:
    try:
        resp = requests.get(
            FF_URL,
            headers={"User-Agent": "Mozilla/5.0 (briefing-bot)"},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            return data
        print(f"ForexFactory beklenmedik format: {type(data)}")
        return []
    except Exception as e:
        print(f"ForexFactory hatası: {e}")
        return []


def parse_dt_tr(iso_str: str):
    """ForexFactory ISO tarihini TR saatine çevirir. Hata olursa None."""
    try:
        dt = datetime.fromisoformat(iso_str)  # tz bilgili gelir
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(TR_TZ)
    except Exception:
        return None


def filter_today(events: list) -> list:
    """Bugün (TR), yüksek/orta etkili, ilgili para birimi olaylarını süz."""
    today_tr = datetime.now(TR_TZ).date()
    out = []
    for e in events:
        impact = (e.get("impact") or "").strip()
        cur    = (e.get("country") or "").strip().upper()
        if impact not in ("High", "Medium"):
            continue
        if cur not in RELEVANT:
            continue
        dt_tr = parse_dt_tr(e.get("date", ""))
        if dt_tr is None or dt_tr.date() != today_tr:
            continue
        e["_dt_tr"] = dt_tr
        out.append(e)

    out.sort(key=lambda x: (0 if x.get("impact") == "High" else 1, x["_dt_tr"]))
    return out


# ── Gemini Analizi ────────────────────────────────────────
def analyze_with_gemini(events: list) -> str:
    if not events:
        return "Bugün takvimde önemli ekonomik veri açıklaması yok."

    lines = []
    for e in events:
        cur      = e.get("country", "")
        name     = e.get("title", "")
        impact   = e.get("impact", "")
        forecast = e.get("forecast", "")
        previous = e.get("previous", "")
        time_tr  = e["_dt_tr"].strftime("%H:%M")

        line = f"[{impact}] {time_tr} {cur}: {name}"
        parts = []
        if forecast: parts.append(f"beklenti: {forecast}")
        if previous: parts.append(f"önceki: {previous}")
        if parts:    line += " (" + ", ".join(parts) + ")"
        lines.append(line)

    events_text = "\n".join(lines)

    prompt = f"""Sen deneyimli bir BIST (Borsa İstanbul) analistisin.
Bugün açıklanacak küresel ve Türkiye ekonomik verileri:

{events_text}

Bu verileri aşağıdaki çerçevede Türkçe ve net yorumla:
1. Genel BIST yön baskısı (yukarı / aşağı / yatay) ve kısa gerekçe
2. En kritik 2-3 verinin BIST üzerindeki olası etkisi
3. TL ve gelişen piyasa (EM) risk iştahına yansıması (varsa)
4. Dikkat edilmesi gereken sektör veya hisse tipi (varsa)

Maksimum 7 cümle, sade ve direkt yaz."""

    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        return (resp.text or "").strip() or "Gemini boş yanıt döndürdü."
    except Exception as e:
        print(f"Gemini hatası: {e}")
        return "Gemini analizi alınamadı."


# ── Telegram Mesajı ───────────────────────────────────────
def build_message(events: list, analysis: str) -> str:
    today_str = datetime.now(TR_TZ).strftime("%d.%m.%Y")
    msg = f"📅 <b>GÜNLÜK MAKRO TAKVİM</b>\n{today_str}\n"

    high   = [e for e in events if e.get("impact") == "High"]
    medium = [e for e in events if e.get("impact") == "Medium"]

    def fmt(e):
        cur      = e.get("country", "").upper()
        flag     = CURRENCY_EMOJI.get(cur, "🌍")
        name     = e.get("title", "")
        time_tr  = e["_dt_tr"].strftime("%H:%M")
        forecast = e.get("forecast", "")
        f_str    = f" <i>(beklenti: {forecast})</i>" if forecast else ""
        return f"• {time_tr} {flag} {name}{f_str}"

    if high:
        msg += "\n🔴 <b>YÜKSEK ETKİ</b>\n" + "\n".join(fmt(e) for e in high) + "\n"
    if medium:
        msg += "\n🟡 <b>ORTA ETKİ</b>\n" + "\n".join(fmt(e) for e in medium[:6]) + "\n"
    if not high and not medium:
        msg += "\nℹ️ Bugün önemli veri açıklaması yok.\n"

    msg += f"\n🤖 <b>YORUM</b>\n{analysis}"
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
