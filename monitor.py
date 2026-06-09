#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PUMA TR beden stok takipçisi
----------------------------
Belirtilen ürün sayfalarını kontrol eder ve istenen beden (varsayılan: M)
stoğa girdiğinde Telegram + ntfy (telefon push) + e-posta ile BİR KEZ bildirir.

Çalışma mantığı:
  1) Önce hafif yol: sayfayı `requests` ile çeker ve Magento'nun sayfaya
     gömdüğü JSON verisini (jsonConfig) okur. Bedenin stok durumu bu veride
     yazar; tarayıcı açmaya gerek kalmaz.
  2) requests engellenir / veri bulunamazsa: Playwright ile gerçek bir tarayıcı
     açıp sayfayı render eder ve aynı veriyi (ya da görünen bedeni) okur.

Yalnızca "stokta değil -> stokta" geçişinde bildirim atar (spam yapmaz).
Durum `state.json` dosyasında saklanır.
"""

import json
import os
import re
import smtplib
import sys
import time
from email.message import EmailMessage
from pathlib import Path

import requests

# ---- .env dosyasını otomatik yükle (yerel test için; GitHub'da gerekmez) ----
def _load_dotenv(path=".env"):
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

_load_dotenv()

# ----------------------------- AYARLAR -----------------------------
PRODUCTS = [
    {
        "label": "Fenerbahçe S.K. 24/25 ERKEK DEPLASMAN FORMASI",
        "url": "https://tr.puma.com/fenerbahce-s-k-24-25-erkek-deplasman-formasi-775368-02.html",
    },
    {
        "label": "Fenerbahçe S.K. 24/25 ERKEK ÜÇÜNCÜ FORMA",
        "url": "https://tr.puma.com/fenerbahce-s-k-24-25-erkek-ucuncu-forma-775375-09.html",
    },
    {
        "label": "Fenerbahçe S.K. 24/25 KADIN DEPLASMAN FORMASI",
        "url": "https://tr.puma.com/fenerbahce-s-k-24-25-kadin-deplasman-formasi-775370-02.html",
    },
]

TARGET_SIZE = os.environ.get("TARGET_SIZE", "M").strip().upper()
STATE_FILE = Path(os.environ.get("STATE_FILE", "state.json"))

# requests inconclusive olursa Playwright'a düşülsün mü?
PLAYWRIGHT_FALLBACK = os.environ.get("PLAYWRIGHT_FALLBACK", "true").lower() != "false"
HEADLESS = os.environ.get("HEADLESS", "true").lower() != "false"
DEBUG = os.environ.get("DEBUG", "0") == "1"

REQUEST_TIMEOUT = 25
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
}
# -------------------------------------------------------------------


# ============ Gömülü JSON (Magento jsonConfig) ayrıştırma ============
def _walk(obj):
    """İç içe dict/list yapısında tüm düğümleri dolaşır."""
    yield obj
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def extract_jsonconfigs(html):
    """Sayfadaki text/x-magento-init bloklarından tüm jsonConfig'leri toplar."""
    configs = []
    pattern = re.compile(
        r'<script[^>]*type=["\']text/x-magento-init["\'][^>]*>(.*?)</script>',
        re.DOTALL | re.IGNORECASE,
    )
    for m in pattern.finditer(html or ""):
        raw = m.group(1).strip()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for node in _walk(data):
            if isinstance(node, dict) and "jsonConfig" in node:
                cfg = node["jsonConfig"]
                if isinstance(cfg, dict):
                    configs.append(cfg)
    return configs


def size_state_from_config(cfg, target):
    """
    jsonConfig içinde beden niteliğini bulur ve hedef bedenin durumunu döndürür.
      True  -> hedef beden satılabilir (stokta)
      False -> hedef beden listelenmiş ama stokta değil
      None  -> bu config'ten karar verilemedi (yapı farklı/bulunamadı)
    """
    attrs = (cfg or {}).get("attributes") or {}
    for attr in attrs.values():
        if not isinstance(attr, dict):
            continue
        code = (attr.get("code") or "").lower()
        label = (attr.get("label") or "").lower()
        is_size = ("size" in code) or ("beden" in code) or ("beden" in label) or ("size" in label)
        if not is_size:
            continue
        for opt in attr.get("options", []):
            opt_label = (opt.get("label") or "").strip().upper()
            if opt_label == target:
                # Magento yalnızca stoktaki varyantları "products" altında listeler
                return bool(opt.get("products"))
    return None


# ============ Yol 1: requests ile ============
def check_via_requests(url, target):
    try:
        r = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200 or not r.text:
            print(f"  requests: HTTP {r.status_code} (içerik yok/engel olabilir)")
            return None
        html = r.text
    except Exception as e:
        print(f"  requests hata: {e}")
        return None

    if DEBUG:
        Path("debug_requests.html").write_text(html, encoding="utf-8")

    configs = extract_jsonconfigs(html)
    if not configs:
        print("  requests: jsonConfig bulunamadı (muhtemelen engellendi).")
        return None

    for cfg in configs:
        state = size_state_from_config(cfg, target)
        if state is not None:
            if DEBUG:
                _print_sizes(cfg)
            return state
    print("  requests: jsonConfig var ama hedef beden bulunamadı.")
    return None


def _print_sizes(cfg):
    attrs = (cfg or {}).get("attributes") or {}
    for attr in attrs.values():
        if not isinstance(attr, dict):
            continue
        if "size" in (attr.get("code") or "").lower() or "beden" in (attr.get("label") or "").lower():
            opts = [
                f"{o.get('label')}({'var' if o.get('products') else 'yok'})"
                for o in attr.get("options", [])
            ]
            print("  [debug] bedenler:", ", ".join(opts))


# ============ Yol 2: Playwright ile (yedek) ============
def check_via_playwright(url, target):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  Playwright kurulu değil; yedek yol atlanıyor.")
        return None

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=HEADLESS,
                args=["--disable-blink-features=AutomationControlled"],
            )
            ctx = browser.new_context(
                locale="tr-TR",
                user_agent=HEADERS["User-Agent"],
                viewport={"width": 1366, "height": 900},
            )
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(3500)  # JS'in bedenleri yüklemesi için bekle
            html = page.content()

            if DEBUG:
                Path("debug_playwright.html").write_text(html, encoding="utf-8")
                page.screenshot(path="debug_playwright.png", full_page=True)

            # Önce yine gömülü jsonConfig'i dene (en güvenilir)
            for cfg in extract_jsonconfigs(html):
                state = size_state_from_config(cfg, target)
                if state is not None:
                    browser.close()
                    return state

            # Olmazsa görünen "custom-dropdown" üzerinden dene
            state = size_state_from_dom(page, target)
            browser.close()
            return state
    except Exception as e:
        print(f"  Playwright hata: {e}")
        return None


def size_state_from_dom(page, target):
    """Görünen beden seçicisinden hedef bedeni okumaya çalışır (sezgisel)."""
    # Dropdown'u açmayı dene
    for sel in [".custom-dropdown", "[data-role='swatch-options']", ".swatch-attribute"]:
        try:
            page.locator(sel).first.click(timeout=1500)
            page.wait_for_timeout(400)
            break
        except Exception:
            continue

    candidates = page.locator(
        ".custom-dropdown li, .custom-dropdown option, "
        "[data-role='swatch-options'] [option-label], .swatch-option.text"
    )
    try:
        n = candidates.count()
    except Exception:
        return None

    for i in range(n):
        el = candidates.nth(i)
        try:
            text = (el.inner_text() or "").strip().upper()
        except Exception:
            text = ""
        attr_label = (
            el.get_attribute("option-label")
            or el.get_attribute("aria-label")
            or ""
        ).strip().upper()
        value = text or attr_label
        if value == target:
            cls = (el.get_attribute("class") or "").lower()
            disabled = (
                any(x in cls for x in ("disabled", "unavailable", "out-of-stock", "not-available", "soldout"))
                or el.get_attribute("disabled") is not None
                or el.get_attribute("aria-disabled") == "true"
            )
            return not disabled
    return None


def check_product(url, target):
    """Bir ürün için hedef bedenin durumunu döndürür (True/False/None)."""
    state = check_via_requests(url, target)
    if state is None and PLAYWRIGHT_FALLBACK:
        print("  -> Playwright yedek yola geçiliyor...")
        state = check_via_playwright(url, target)
    return state


# ============ Durum (state) yönetimi ============
def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


# ============ Bildirimler ============
def notify(prod, size):
    title = f"PUMA: {size} beden STOKTA"
    body = f"{prod['label']}\nBeden {size} su an satista.\n{prod['url']}"
    print(f"  >>> BILDIRIM: {prod['label']} / {size} stokta!")
    send_telegram(title, body)
    send_ntfy(title, body, prod["url"])
    send_email(title, body)


def send_telegram(title, body):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat, "text": f"🔥 {title}\n\n{body}"},
            timeout=20,
        )
        resp.raise_for_status()
        print("  Telegram: gönderildi.")
    except Exception as e:
        print(f"  Telegram hata: {e}", file=sys.stderr)


def send_ntfy(title, body, click_url):
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        return
    base = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    try:
        resp = requests.post(
            f"{base}/{topic}",
            data=body.encode("utf-8"),
            headers={
                "Title": title,                 # sadece ASCII karakter içerir
                "Priority": "urgent",
                "Tags": "fire,shopping_cart",
                "Click": click_url,             # bildirime dokununca ürün sayfası açılır
            },
            timeout=20,
        )
        resp.raise_for_status()
        print("  ntfy: gönderildi.")
    except Exception as e:
        print(f"  ntfy hata: {e}", file=sys.stderr)


def send_email(title, body):
    host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    port = int(os.environ.get("SMTP_PORT", "465"))
    user = os.environ.get("SMTP_USER")
    pwd = os.environ.get("SMTP_PASS")
    to = os.environ.get("EMAIL_TO", user)
    if not (user and pwd and to):
        return
    try:
        msg = EmailMessage()
        msg["Subject"] = title
        msg["From"] = user
        msg["To"] = to
        msg.set_content(body)
        with smtplib.SMTP_SSL(host, port, timeout=30) as s:
            s.login(user, pwd)
            s.send_message(msg)
        print("  E-posta: gönderildi.")
    except Exception as e:
        print(f"  E-posta hata: {e}", file=sys.stderr)


# ============ Ana akış ============
def check_all():
    print(f"== Kontrol başlıyor (hedef beden: {TARGET_SIZE}) ==")
    state = load_state()
    changed = False

    for prod in PRODUCTS:
        url = prod["url"]
        print(f"- {prod['label']}")
        now = check_product(url, TARGET_SIZE)
        prev = state.get(url)

        if now is None:
            print(f"  SONUÇ: belirsiz (stok okunamadı) — önceki durum korunuyor.")
            continue

        print(f"  SONUÇ: {TARGET_SIZE} -> {'STOKTA' if now else 'yok'}")

        if now and not prev:
            notify(prod, TARGET_SIZE)
        if state.get(url) != now:
            state[url] = now
            changed = True

    save_state(state)
    print(f"== Bitti. Durum {'güncellendi' if changed else 'değişmedi'}. ==")


def selftest():
    """İnternet gerektirmeyen mantık testi."""
    sample = """
    <script type="text/x-magento-init">
    {"[data-role=swatch-options]":{"Magento_Swatches/js/swatch-renderer":{"jsonConfig":{
    "attributes":{"180":{"id":"180","code":"size","label":"Beden","options":[
    {"id":"10","label":"S","products":[]},
    {"id":"11","label":"M","products":["5001","5002"]},
    {"id":"12","label":"L","products":[]}]}}}}}}
    </script>
    """
    cfgs = extract_jsonconfigs(sample)
    assert len(cfgs) == 1, "jsonConfig ayrıştırılamadı"
    assert size_state_from_config(cfgs[0], "M") is True, "M stokta olmalı"
    assert size_state_from_config(cfgs[0], "S") is False, "S stokta olmamalı"
    assert size_state_from_config(cfgs[0], "XL") is None, "XL listede yok -> None"
    print("selftest: TÜM TESTLER GEÇTİ ✓")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
        sys.exit(0)
    if "--test-notify" in sys.argv:
        notify({"label": "TEST ürünü", "url": PRODUCTS[0]["url"]}, TARGET_SIZE)
        sys.exit(0)
    if "--loop" in sys.argv:
        idx = sys.argv.index("--loop")
        interval = int(sys.argv[idx + 1]) if len(sys.argv) > idx + 1 else 180
        print(f"Döngü modu: her {interval} sn'de bir kontrol. (Ctrl+C ile çıkış)")
        while True:
            try:
                check_all()
            except Exception as e:
                print(f"Döngü hatası: {e}", file=sys.stderr)
            time.sleep(interval)
    else:
        check_all()
