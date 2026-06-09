# PUMA Beden (M) Stok Takipçisi

İki Fenerbahçe forması sayfasını periyodik kontrol eder; **M bedeni stoğa girdiğinde**
**Telegram + telefon push (ntfy) + e-posta** ile sana bir kez haber verir.

- Sadece "yok → stokta" geçişinde bildirir (spam yapmaz).
- Önce hafif yolu (HTTP) dener; engellenirse otomatik olarak tarayıcılı (Playwright) yola düşer.
- Hem **GitHub Actions**'ta (bilgisayarın kapalıyken bile) hem de **laptopunda** çalışır.

---

## 0) Dosya yapısı
```
puma-stok-takip/
├─ monitor.py
├─ requirements.txt
├─ README.md
└─ .github/
   └─ workflows/
      └─ stock-check.yml
```
`.github/workflows/` yolu **aynen** böyle olmalı, yoksa GitHub Actions çalışmaz.

---

## 1) Bildirim kanallarını hazırla

Üç kanal da **bağımsız ve isteğe bağlı**: hangi bilgileri girersen o kanal çalışır.
İstersen önce Telegram + ntfy ile başla, e-postayı sonra ekle.

### A) Telegram botu (zorunlu — senin ana kanalın)
1. Telegram'da **@BotFather**'a yaz → `/newbot` → bota isim ver. Sana bir **token** verir
   (`123456:ABC-DEF...` gibi). Bu `TELEGRAM_BOT_TOKEN`.
2. Kendi **chat id**'ni öğren: yeni botuna bir mesaj yaz (örn. "merhaba"), sonra
   tarayıcıda şunu aç:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
   Dönen JSON'da `"chat":{"id":123456789}` → bu sayı `TELEGRAM_CHAT_ID`.
   (Alternatif: **@userinfobot**'a yazınca id'ni söyler.)

### B) ntfy — telefon push (zorunlu — gözden kaçmaması için ikinci kanal)
ntfy ücretsiz, **hesap/şifre gerektirmez**; bir "topic" (konu) adına mesaj atarsın,
o konuya abone olan telefonun anında bildirim alır.
1. Telefonuna **ntfy** uygulamasını kur (App Store / Google Play).
2. **Tahmin edilemez, uzun bir topic adı** seç — bu senin gizli adresin gibidir.
   Örn: `puma-fb-m-7h3k9x2q`. (Kısa/tahmin edilebilir bir ad seçersen başkaları da
   o bildirimleri görebilir.)
3. Uygulamada "Subscribe to topic" ile bu adı ekle.
4. Aynı adı `NTFY_TOPIC` olarak kullanacağız. Sunucu varsayılan `https://ntfy.sh`.
   - Test: telefonda abone olduktan sonra terminalde
     `curl -d "deneme" ntfy.sh/puma-fb-m-7h3k9x2q` → anında bildirim gelmeli.

### C) E-posta (üçüncü kanal) — en kolay ücretsiz yol: Gmail "Uygulama Şifresi"

**Neden Gmail uygulama şifresi?** Hiçbir 3. servise kayıt gerektirmez, sonsuza kadar
ücretsizdir ve "kendine e-posta at" senaryosu için en pratiğidir. Kurulumu birkaç tık:

1. Google hesabında **2 Adımlı Doğrulama** açık olmalı
   (Google Hesabı → Güvenlik → 2 Adımlı Doğrulama).
2. Sonra **Uygulama Şifreleri** sayfasına git
   (Google Hesabı → Güvenlik → Uygulama şifreleri / App passwords).
3. Yeni bir uygulama şifresi oluştur (isim: "puma-takip" yazabilirsin). Sana
   **16 haneli** bir şifre verir (`abcd efgh ijkl mnop`). Bunu bir yere not al,
   bir daha gösterilmez.
4. Bu bilgileri kullan:
   - `SMTP_USER` = gmail adresin (örn. `adin@gmail.com`)
   - `SMTP_PASS` = 16 haneli uygulama şifresi (boşlukları silebilirsin)
   - `EMAIL_TO`  = bildirimleri alacağın adres (kendine atmak için yine kendi adresin)

**E-posta için ücretsiz alternatifler (istersen):**
- **Brevo (eski adıyla Sendinblue):** ücretsiz planda günde ~300 e-posta, SMTP
  bilgisi verir, alan adı (domain) gerektirmez. `SMTP_HOST=smtp-relay.brevo.com`
  olarak girip aynı `SMTP_USER`/`SMTP_PASS` mantığıyla kullanılır.
- **Resend / SendGrid:** ücretsiz katmanları var ve API ile çok kolay; ama kendi
  alan adından göndermek için domain doğrulaması ister. Kişisel "kendine bildirim"
  için Gmail uygulama şifresi daha az uğraştırır, o yüzden varsayılan olarak onu öneriyorum.

> Bu script e-postayı standart SMTP ile gönderir; yani Gmail veya Brevo, ikisi de
> hiç kod değişikliği olmadan çalışır — sadece ortam değişkenlerini değiştirirsin.

---

## 2) GitHub Actions ile çalıştırma (önerilen)

### Adımlar
1. **GitHub'da yeni bir repo oluştur.** Önemli: repoyu **public (herkese açık)** yap.
   - Neden? GitHub Actions, **public repolarda ücretsiz/sınırsız** dakika verir.
     Private repolarda ayda yalnızca ~2.000 dakika ücretsizdir; 5 dakikada bir
     çalışınca bu süre ~1 haftada biter. Gizli bilgilerin (token vs.) zaten kodda
     değil **Secrets**'ta durur, o yüzden public repo güvenli.
2. Buradaki dosyaları repoya yükle (yapıyı koruyarak).
3. **Secrets'ı gir:** repo → **Settings → Secrets and variables → Actions →
   New repository secret**. Şu adlarla tek tek ekle (sadece kullandığın kanallar için):
   - `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
   - `NTFY_TOPIC`
   - `SMTP_USER`, `SMTP_PASS`, `EMAIL_TO`
4. Repo → **Actions** sekmesine gir, çıkan uyarıda workflow'ları **etkinleştir**.
5. Soldan **"PUMA beden takibi"** workflow'unu seç → sağdan **Run workflow** ile
   elle bir kez çalıştır. **Logs**'a bakıp şuna benzer satırları gör:
   ```
   - Fenerbahçe 24/25 Erkek Deplasman Forması
     SONUÇ: M -> yok
   ```
   `yok` veya `STOKTA` görüyorsan çalışıyor demektir. Eğer **"belirsiz / engellendi"**
   görürsen → aşağıdaki "Engellenirsem" bölümüne bak.

### Bildirimleri test et
İlk kurulumda kanalların çalıştığını görmek için: bilgisayarında (bkz. Bölüm 3)
```
python monitor.py --test-notify
```
komutu üç kanala da deneme bildirimi atar. (Bunun için ortam değişkenlerini
yerelde tanımlamış olman gerekir.)

### Önemli GitHub Actions uyarıları
- **Zamanlama garanti değil:** `schedule` (cron) yoğunlukta gecikir, hatta bazen
  bir turu atlar. Genelde birkaç–on dakikalık sapma normaldir. Saniyelerin önemli
  olduğu kapışmalı bir dropta laptop yöntemi (Bölüm 3) daha güvenilirdir.
- **En sık 5 dakika:** GitHub cron için minimum aralık 5 dk'dır.
- **60 gün kuralı:** Repoda 60 gün hiç hareket olmazsa GitHub zamanlanmış
  workflow'u otomatik durdurur (sana e-posta atar). Stok uzun süre değişmezse
  ara sıra repoya küçük bir commit atmak ya da uyarı gelince yeniden etkinleştirmek
  yeterli. (Stok her değiştiğinde script zaten `state.json`'u commit'ler.)
- **state.json:** Script son durumu bu dosyaya yazar ve workflow değişiklik olunca
  repoya geri commit'ler. Böylece her turda "yine stokta" diye tekrar tekrar
  bildirim atılmaz. Commit geçmişinden stok değişimlerini de görebilirsin.

---

## 3) Laptopta çalıştırma (alternatif / daha hassas zamanlama)

```bash
pip install -r requirements.txt
# (yedek tarayıcı yolunu da istiyorsan:)
python -m playwright install chromium

# Ortam değişkenleri (Linux/macOS örneği):
export TELEGRAM_BOT_TOKEN="..."
export TELEGRAM_CHAT_ID="..."
export NTFY_TOPIC="puma-fb-m-7h3k9x2q"
export SMTP_USER="adin@gmail.com"
export SMTP_PASS="16hanesifre"
export EMAIL_TO="adin@gmail.com"

# Tek seferlik kontrol:
python monitor.py

# Sürekli, her 180 saniyede bir (Ctrl+C ile durur):
python monitor.py --loop 180
```

- Tarayıcıyı **gözünle görmek** için (ne yaptığını anlamak/ayıklamak adına):
  `HEADLESS=false python monitor.py`
- **Ayıklama (debug):** `DEBUG=1 python monitor.py` çalıştırırsan sayfanın HTML'ini
  (`debug_*.html`) ve ekran görüntüsünü (`debug_playwright.png`) diske kaydeder;
  ayrıca bulduğu beden listesini yazar. Bedenin "M" mı yoksa "Medium" mu yazdığını
  buradan teyit edebilirsin.
- Windows'ta arka planda sürekli çalışması için **Görev Zamanlayıcı** (Task Scheduler)
  ile `python monitor.py` komutunu belirli aralıkla tetikleyebilirsin; ya da
  `--loop` ile açık bırakırsın.

---

## 4) Engellenirsem? (anti-bot)

PUMA'nın güvenlik/performans katmanı, çok sık veya "bot gibi" isteklerde hafif yolu
(requests) engelleyebilir. Belirtisi: loglarda **"belirsiz / jsonConfig bulunamadı /
engellendi"**.

Çözüm: **tarayıcılı yedek yolu aç.**
- **GitHub Actions'ta:** `.github/workflows/stock-check.yml` içindeki
  *"Tarayıcı kur (yedek yol)"* adımının başındaki `#` işaretlerini kaldır. Script
  zaten requests başarısız olunca otomatik Playwright'a düşecek şekilde yazıldı.
- **Laptopta:** `python -m playwright install chromium` yeterli; gerisi otomatik.

Yine de takılırsan: kontrol aralığını seyrekleştir (örn. 10 dk), gerçekçi bir
User-Agent zaten ayarlı. Çok agresif sorgulama hem IP engeline yol açar hem de
gereksizdir; kişisel kullanım için 3–5 dk fazlasıyla yeterli.

---

## 5) Başka bir ürünü/bedeni takip etmek

- **Beden:** `TARGET_SIZE` değişkenini değiştir (örn. `L`). GitHub'da workflow'daki
  `TARGET_SIZE: "M"` satırını, laptopta `export TARGET_SIZE=L` ile.
- **Ürün eklemek/çıkarmak:** `monitor.py` içindeki `PRODUCTS` listesine yeni
  `{"label": "...", "url": "..."}` satırı ekle.

---

## Notlar
- Bu, herkese açık ürün sayfalarını **kişisel ve düşük hacimli** izleyen bir araçtır.
  Sitenin yapısı (sayfadaki JSON anahtarları, CSS sınıfları) değişirse kodu güncellemek
  gerekebilir — bu tür takip projeleri ara sıra bakım ister.
- Hiçbir gizli bilgi kodda yazmaz; hepsi Secrets / ortam değişkenlerindedir.
- Ek olarak PUMA'nın kendi **"İlk Senin Haberin Olsun"** (stoğa girince e-posta)
  kaydını da yapabilirsin; bu projeyle birlikte bedava bir yedek olur.
