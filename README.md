# PyPkg Compare: otonom programatik SEO sitesi

Her gün GitHub Actions üzerinde kendi kendine çalışır: PyPI verisini çeker, snapshot'ı
depoya yazar, statik siteyi yeniden üretir ve yayınlar. Sunucu, veritabanı ve ücretli API yok.

## Tek seferlik kurulum (yaklaşık 15 dakika)

1. GitHub'da **public** bir depo aç (örn. `pypkg-compare`) ve bu klasördeki her şeyi yükle
   (`.github/` klasörü dahil).
2. Depoda **Settings → Pages → Source: GitHub Actions** seç.
3. **Actions** sekmesinden `build-and-deploy` iş akışını bir kez elle çalıştır (Run workflow).
   Site `https://KULLANICI.github.io/DEPO/` adresinde açılır.
4. Google Search Console'a siteyi ekle ve `sitemap.xml` adresini gönder.
   Doğrulama etiketini `config.json` içindeki `head_html` alanına yapıştır.

Bundan sonra tıklama gerekmez; iş akışı her gün 03:17 UTC'de çalışır.

## Para kazanma (trafik gelince)

- `config.json` → `affiliate_links`: `[{"text": "...", "url": "..."}]` biçiminde ekle.
  Link eklediğinde `disclosure` alanına da açıklama yaz
  (örn. "Some links are affiliate links.").
- Reklam ağı kodu `head_html` alanına girer. AdSense ve geliştirici odaklı reklam ağları
  genellikle kendi alan adını ve belirli bir trafiği şart koşar; ilk gelirle alan adı almak mantıklı.

## Ayarlar

- `top_n`: izlenen paket sayısı. 300 ile başla; site indekslenmeye başlayınca kademeli artır.
- `pairs_per_topic`: her konuda birbirine karşı karşılaştırılan ilk N paket.

## Yerelde deneme

    python build.py
    python -m http.server -d site 8000

## Bilinen sınırlar

- İndirme sayıları `hugovk.github.io/top-pypi-packages` veri setinden gelir. Bu kaynak
  erişilemezse betik `seeds.txt` listesine düşer ve indirme sayıları "n/a" görünür.
- "30-day change" sütunu, depoda en az 30 günlük snapshot birikince dolar.
- GitHub Pages ağırlıklı olarak ticari amaçlı siteler için tasarlanmamıştır. Gelir ciddileşirse
  aynı `site/` çıktısını Cloudflare Pages gibi bir servise taşı.
