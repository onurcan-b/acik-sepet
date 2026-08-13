# Açık Sepet

**Türkiye'deki zincir market fiyatlarının günlük hareketini 150 ürünlük sabit bir sepet üzerinden izleyen deneysel açık fiyat endeksi.**

> Açık Sepet resmi TÜFE değildir. Konut, kira, ulaştırma, sağlık, eğitim ve hizmetleri kapsamaz; market malları için yüksek frekanslı bir göstergedir.

![Açık Sepet günlük endeksi](charts/index.svg)

<!-- STATS_START -->
- **Son değer:** 100.00
- **Son güncelleme:** 2026-08-13
- **Kapsama:** %92 (136 ürün)
- **7 günlük değişim:** —
- **30 günlük değişim:** —
- **Baz tarihi:** 2026-08-13 = 100
<!-- STATS_END -->

## v0.2

- **150 ürün**
- **12 tüketim grubu**
- sabit SKU eşleştirmesi
- sabit temsilci mağaza/depot takibi
- iki aşamalı grup ağırlıklandırması
- 12 grup + birleşik **Gıda ve alkolsüz içecekler** alt endeksi
- günlük GitHub Actions güncellemesi

| Grup | Ürün | Araştırma ağırlığı |
|---|---:|---:|
| Ekmek, tahıllar ve makarna | 18 | %14 |
| Et ve et ürünleri | 15 | %15 |
| Balık ve deniz ürünleri | 8 | %4 |
| Süt ürünleri ve yumurta | 18 | %14 |
| Yağlar | 8 | %6 |
| Meyve | 14 | %8 |
| Sebze | 18 | %11 |
| Şeker, tatlı ve atıştırmalık | 14 | %8 |
| Diğer gıda | 10 | %4 |
| Alkolsüz içecekler | 12 | %5 |
| Ev temizlik sarf malzemeleri | 9 | %7 |
| Kişisel bakım ve kağıt ürünleri | 6 | %4 |
| **Toplam** | **150** | **%100** |

Grup içinde ürünler eşit pay alır; gruplar yukarıdaki araştırma ağırlıklarıyla birleştirilir. Bu ağırlıklar **TÜİK'in resmi TÜFE ağırlıkları değildir**. Ayrıntılar [METHOD.md](METHOD.md) içinde.

## Veri akışı

```text
Market Fiyatı → 150 sabit ürün → SKU/depot sabitleme → günlük snapshot
→ grup-ağırlıklı ana endeks → README grafiği → 12 alt endeks + gıda endeksi
```

## Dosyalar

```text
config/basket.tsv
config/categories.json
state/product-map.json
data/snapshots/YYYY-MM-DD.json
data/index.csv
data/subindices.csv
charts/index.svg
```

`data/subindices.csv`, 12 tüketim grubunun yanında `food_total` satırıyla birleşik gıda ve alkolsüz içecekler serisini de içerir.

## Otomasyon

`.github/workflows/daily.yml` günlük fiyat snapshot'ını ve ana endeksi üretir. Başarılı daily run sonrasında `.github/workflows/subindices.yml` alt endeksleri otomatik yeniler. İki workflow da GitHub Actions üzerinden elle tetiklenebilir.

## Veri kaynağı

MVP, `marketfiyati.org.tr` arayüzünün kullandığı veri servisine düşük hacimli sorgular gönderir. Repo ham servisin toplu aynası değildir. Proje kamuya açılmadan veya kapsam büyütülmeden önce veri yeniden kullanım koşulları ayrıca netleştirilmelidir.
