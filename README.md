# 📡 BİST Tahtacı Scanner

Borsa İstanbul'da gün içi **tahtacı davranışı** sergileyen hisseleri tespit edip Telegram'a bildirim gönderen bir bot.

---

## Nasıl Çalışır?

```
yfinance (15dk gecikmeli) → Sinyal Motoru → Telegram
```

Her **30 dakikada bir** tüm BİST hisselerini tarar. Aşağıdaki proxy göstergelerle tahtacı davranışını tespit eder:

| Gösterge | Açıklama |
|----------|----------|
| 🤫 Akümülasyon | Düşüklerde güçlü kapanış, alt gölge oranı |
| 🔄 Silkeleme | Ani düşüş + yüksek hacim + hızlı toparlanma |
| 🚀 Pompa | Ardışık yukarı kapanışlar + hacim ivmelenmesi |
| 📊 Hacim Anomalisi | Son hacim / 20 mum ortalaması > 3x |

Bunları ağırlıklı olarak birleştirip 0-100 arası **Tahtacı Skoru** üretir.

---

## Kurulum (GitHub Actions — Ücretsiz)

### 1. Telegram Bot Oluştur

1. Telegram'da [@BotFather](https://t.me/BotFather)'a git
2. `/newbot` komutu → bot adı ver → **token al**
3. Bota bir mesaj at, sonra şu URL'yi aç:
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
4. `"chat":{"id":...}` kısmındaki sayıyı al → bu senin **Chat ID**'n

### 2. GitHub'a Fork / Clone Et

```bash
git clone https://github.com/KULLANICI_ADIN/bist-scanner.git
cd bist-scanner
```

### 3. GitHub Secrets Ekle

Repo → **Settings → Secrets and variables → Actions → New repository secret**

| Secret Adı | Değer |
|------------|-------|
| `TELEGRAM_TOKEN` | BotFather'dan aldığın token |
| `TELEGRAM_CHAT_ID` | Chat ID'n (sayı) |

### 4. Actions'ı Aktif Et

Repo → **Actions** sekmesi → "I understand my workflows" → Enable

---

## Örnek Telegram Mesajı

```
🚨 TAHTACİ SİNYALİ — THYAO

💰 Fiyat: 142.80 ₺  (+3.2%)

🎯 Tahtacı Skoru: 78/100
   ████████░░

📊 Hacim: 4.1M  (Ort: 1.0M, 4.1x)

🚀 Aktif Faz: POMPA
   ✅ Akümülasyon izi mevcut
   ✅ Ardışık ↑ kapanış: 4 mum
   ✅ Hacim anomalisi: 4.1x

Alt Skorlar:
  Akümülasyon :    72/100
  Silkeleme   :    55/100
  Pompa       :    90/100
  Hacim Anom. :    82/100

💪 Güçlü sinyal — yine de kendi analizini yap

🕐 14:32 · 02.06.2026
```

---

## Ayarlar (`config.py`)

| Parametre | Varsayılan | Açıklama |
|-----------|-----------|----------|
| `TAHTACI_MIN_SCORE` | 55 | Bu altı bildirim gitmiyor |
| `VOLUME_SPIKE_THRESHOLD` | 3.0 | Kaç katlık hacim anomali sayılır |
| `POMPA_CONSECUTIVE_CANDLES` | 3 | Kaç ardışık yukarı mum = pompa |
| `BATCH_SIZE` | 20 | yfinance'e aynı anda kaç hisse |

---

## Önemli Notlar

- **15 dakika gecikmeli veri** kullanılıyor (yfinance kısıtı)
- Bu bot **yatırım tavsiyesi değildir**
- Tahtacı tespiti proxy göstergelere dayanır, kesin değildir
- Sinyaller kendi analizinle teyit edilmelidir

---

## Geliştirme Yol Haritası

- [ ] Gerçek zamanlı API entegrasyonu (Matriks/Rasyonet)
- [ ] Geçmiş sinyal başarı takibi
- [ ] Telegram komut desteği (`/tara`, `/skor THYAO`)
- [ ] Sektör bazlı anomali tespiti
- [ ] Order book analizi (gerçek tahtacı tespiti)
