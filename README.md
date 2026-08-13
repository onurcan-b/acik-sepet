# Açık Sepet

**Türkiye'deki zincir market fiyatlarının günlük hareketini küçük, sabit ve sürümlenebilir bir sepet üzerinden ölçen deneysel açık endeks altyapısı.**

> MVP aşamasındadır. Resmi TÜFE değildir; TÜİK TÜFE'sinin alternatifi veya ikamesi olarak sunulmaz.

![Açık Sepet günlük endeksi](charts/index.svg)

<!-- STATS_START -->
- **Durum:** İlk gerçek snapshot bekleniyor.
- **Grafik:** İlk başarılı GitHub Actions koşusundan sonra otomatik güncellenecek.
<!-- STATS_END -->

## MVP ne yapıyor?

- Market Fiyatı üzerinden küçük ve sabit bir ürün sepeti için günlük fiyat gözlemleri alır.
- İlk bulunan ürünü/SKU'yu sabitler; sonraki gün başka ürüne sessizce geçmez.
- Her SKU için dönen zincir market tekliflerinin medyanını günlük fiyat olarak kullanır.
- Depot/mağaza kimliklerini snapshot içinde saklar.
- Günlük snapshot'ı `data/snapshots/` altında saklar.
- `data/index.csv` içinde baz=100 günlük deneysel endeks üretir.
- `charts/index.svg` ve yukarıdaki README istatistiklerini otomatik yeniler.
- Her gün GitHub Actions ile çalışabilecek şekilde hazırlanmıştır.

## Otomasyon

`.github/workflows/daily.yml` her gün çalışır ve elle de tetiklenebilir:

```text
Market Fiyatı → sabit sepet snapshot'ı → index.csv → SVG grafik → README → commit
```

## Sepet

İlk MVP'de 12 temel ürün sorgusu var: süt, yoğurt, yumurta, makarna, pirinç, ayçiçek yağı, şeker, un, çay, kola, bulaşık deterjanı ve tuvalet kağıdı.

Sepet ve ağırlıklar `config/basket.json` içinde sürümlenir.

## Yerelde çalıştırma

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m acik_sepet.collect
python -m acik_sepet.index
python -m acik_sepet.report
pytest
```

## Metodoloji

Detaylar ve sınırlamalar: [METHOD.md](METHOD.md)

## Veri kaynağı ve kullanım notu

MVP, `marketfiyati.org.tr` arayüzünün kullandığı veri servisine düşük hacimli sorgular gönderir. Bu repo bir toplu veri aynası olarak tasarlanmamıştır. Proje kamuya açılmadan veya kapsam büyütülmeden önce veri yeniden kullanım koşulları ayrıca netleştirilmelidir.
