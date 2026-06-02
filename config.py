# config.py
# Tüm ayarlar buradan yönetilir.
# Telegram token ve chat_id için GitHub Secrets kullanılır.

import os

# ── Telegram ──────────────────────────────────────────────
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Tarama Parametreleri ───────────────────────────────────
INTERVAL          = "15m"   # yfinance veri aralığı
LOOKBACK_PERIOD   = "5d"    # kaç günlük veri çekilsin
BATCH_SIZE        = 20      # aynı anda kaç hisse çekilsin (rate limit)
BATCH_DELAY_SEC   = 2.0     # batch'ler arası bekleme (saniye)

# ── Sinyal Eşikleri ────────────────────────────────────────
# Hacim anomalisi
VOLUME_SPIKE_THRESHOLD     = 3.0   # ortalamanın kaç katı → anomali
VOLUME_LOOKBACK_CANDLES    = 20    # ortalama için kaç mum bakılsın

# Fiyat hareketi
MIN_PRICE_CHANGE_PCT       = 1.5   # minimum % fiyat değişimi (gürültü filtresi)
MAX_PRICE_CHANGE_PCT       = 20.0  # üstü manipülasyon/haber etkisi, filtrele

# Tahtacı skoru
TAHTACI_MIN_SCORE          = 55    # 0-100, bu altı gönderilmez
POMPA_CONSECUTIVE_CANDLES  = 3     # kaç ardışık yukarı kapanış pompayı doğrular
SILKELEME_DROP_PCT         = 2.0   # silkeleme için minimum düşüş %
SILKELEME_RECOVERY_PCT     = 1.5   # silkeleme sonrası toparlanma eşiği

# ── Skor Ağırlıkları ───────────────────────────────────────
W_AKUMULASYON   = 0.20
W_SILKELEME     = 0.20
W_POMPA         = 0.35
W_HACIM_ANOMALI = 0.25

# ── Filtreler ──────────────────────────────────────────────
MIN_VOLUME_FILTER          = 50_000   # çok ince hisseleri ele (günlük hacim TL)
MIN_CANDLE_COUNT           = 10       # en az bu kadar mum yoksa sinyal üretme
COOLDOWN_MINUTES           = 60       # aynı hisse için tekrar sinyal süresi

# ── Borsa Saatleri (UTC+3) ─────────────────────────────────
MARKET_OPEN_HOUR    = 10
MARKET_OPEN_MINUTE  = 0
MARKET_CLOSE_HOUR   = 18
MARKET_CLOSE_MINUTE = 10
