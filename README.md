# Açık Sepet

Türkiye'deki zincir market fiyatlarını **ürün tipi → çoklu SKU → kategori → ana endeks** hiyerarşisiyle günlük izleyen açık ve yeniden üretilebilir deneysel fiyat endeksi.

[![Daily Açık Sepet](https://github.com/onurcan-b/acik-sepet/actions/workflows/daily.yml/badge.svg)](https://github.com/onurcan-b/acik-sepet/actions/workflows/daily.yml)
[![Validate Açık Sepet](https://github.com/onurcan-b/acik-sepet/actions/workflows/validate.yml/badge.svg)](https://github.com/onurcan-b/acik-sepet/actions/workflows/validate.yml)
![Python](https://img.shields.io/badge/Python-3.12+-blue)
![Data](https://img.shields.io/badge/data-daily-informational)

> **Açık Sepet resmî TÜFE değildir.** Kira, konut, ulaşım, sağlık, eğitim ve hizmetleri kapsamaz. Amaç, markette satılan malların fiyat hareketini yüksek frekansta, şeffaf bir metodolojiyle ölçmektir.

![Açık Sepet günlük endeksi](charts/index.svg)

<!-- STATS_START -->
- **Son değer:** 101.70
- **Son güncelleme:** 2026-08-26
- **Aktif ürün tipi:** 109
- **Karşılaştırılabilir SKU:** 1758
- **Kategori ağırlık kapsaması:** %100
- **7 günlük değişim:** +0.87%
- **30 günlük değişim:** —
- **Baz tarihi:** 2026-08-16 = 100
<!-- STATS_END -->

## Son 24 saatte

<!-- MOVERS_START -->
- **Dönem:** 2026-08-25 → 2026-08-26
- **↑ Yükselen ürün tipi:** 55 · **↓ Düşen:** 28 · **= Yatay:** 26
- **Karşılaştırılan ürün tipi:** 109

| Ürün tipi | SKU | Değişim |
|---|---:|---:|
| Havuç | 12 | +6.22% |
| Muz | 13 | +5.73% |
| Tavuk göğüs | 5 | +5.48% |
| Armut | 7 | +5.38% |
| Zeytinyağı | 13 | +4.80% |
| Sıvı sabun | 19 | +4.22% |
| Kabak | 12 | -3.53% |
| Hazır çorba | 14 | -3.50% |
| Diş fırçası | 23 | +3.42% |
| Üzüm | 12 | +3.14% |
<!-- MOVERS_END -->

## Veri kalitesi

<!-- QUALITY_START -->
- **Aktif ürün tipi:** 109/130
- **SKU panel kapsaması:** 1758/2092 (84.0%)
- **%70'in altında panel kapsaması olan tip:** 12
- **Yayımlanan ana kategori:** 12
- **Depot-relative kaynak takibi olan gözlem:** 1778/1778
- **Köprülenmiş otomatik SKU yenilemesi:** 11
- Yeni depotlar sessizce panele girmez; mevcut depotların fiyat relatifleri ayrı izlenir. Bir depot geçici kaybolduğunda yalnızca kaynak kompozisyonu değişti diye seviye sıçraması oluşmaz.
<!-- QUALITY_END -->

## Neden v0.3?

Açık Sepet'in ilk sürümleri yaklaşık 150 sabit SKU izliyordu. Bu yaklaşım teknik olarak basitti ancak tek bir markadaki kampanya, stok kaybı veya paket değişimi bir ürün grubunu gereğinden fazla oynatabiliyordu.

v0.3'te gözlem birimi artık tek ürün değil **ürün tipi panelidir**. Örneğin `şampuan`, `spagetti makarna`, `yoğurt` veya `pirinç` için birden fazla marka ve paket ayrı SKU olarak izlenir. Panel hedefi ürün tipine göre değişir; geniş kategorilerde 20–30 veya daha fazla SKU bulunabilir. Toplam panel kapasitesi birkaç bin SKU düzeyindedir.

```text
Market Fiyatı
    ↓
100+ ürün tipi
    ↓
Her tip için sabit çoklu-SKU paneli
    ↓
SKU içinde sabit market/depot relatifleri
    ↓
Gramaj / litre / adet normalizasyonu
    ↓
Kalıcı panel slotunun bağlı birim fiyat relatifi
    ↓
Ürün tipi elementary endeksi
    ↓
12 ana market kategorisi
    ↓
Açık Sepet Market Endeksi
```

## Temel metodoloji

### 1. Ürün tipi ve panel slotları

Ürün tipleri `config/product_types.tsv` dosyasında tanımlanır. Her ürün tipi için arama sorgusu, beklenen ölçü birimi (`mass`, `volume`, `count`), hedef/minimum SKU sayısı ve dahil/hariç kelime kuralları saklanır.

İlk başarılı v0.3 çalışmasında her ürün tipi için bir SKU paneli oluşturulur ve `state/v0.3-panels.json` içinde sabitlenir. Her SKU aynı zamanda kalıcı bir **panel slotuna** sahiptir. Normal günlük çalışmada panel başka ürünlerle doldurulmaz.

### 2. Kaynak/depot sürekliliği

Bir SKU'nun Market Fiyatı sonucunda birden fazla market/depot teklifi bulunabilir. Source-aware collector ilk gözlemde mevcut kaynak kimliklerini SKU'ya sabitler ve her depot için başlangıç fiyatını kaydeder. Sonraki günlerde yeni görünen depotlar otomatik olarak fiyat hesabına girmez.

SKU'nun kaynak-ayarlı paket fiyatı, o gün mevcut olan **aynı sabit depotların kendi başlangıç fiyatlarına göre relatiflerinin geometrik ortalaması** ile ilerletilir:

```text
source_relative(s,t) = price(s,t) / price(s,anchor)
linked_package_price(t)
    = adoption_day_all_offer_median × geometric_mean(source_relative(s,t))
```

Böylece sabit depotlardan biri geçici olarak kaybolursa diğer depotların fiyatı değişmediği sürece SKU seviyesi sırf kaynak kompozisyonu değişti diye oynamaz. Yeni bir depot da sessizce panele giremez. Aynı depotlarda gerçek fiyat hareketi olduğunda ise relatif doğrudan ölçülür.

### 3. Birim fiyat

Paket bilgileri başlıktan normalize edilir:

```text
500 g       → 0.5 kg
2 x 160 g   → 0.32 kg
750 ml      → 0.75 L
6 x 200 ml  → 1.2 L
12'li       → 12 adet
```

**Farklı markaların TL/kg veya TL/L seviyeleri doğrudan ortalanmaz.** Birim fiyat, aynı panel slotunun zaman içindeki fiyat relatifini hesaplamak için kullanılır. Paket küçülmesi/büyümesi de böylece sinyale yansıyabilir.

### 4. Ürün tipi endeksi

Bir panel slotu için:

```text
relative(i,t) = linked_unit_price(i,t) / linked_unit_price(i,base)
```

Legacy v0.3 snapshot'larında `linked_unit_price` yoktur; bu satırlarda mevcut `unit_price` aynen kullanılır. Bu geriye uyumluluk, **2026-08-16 = 100** bazını ve yayımlanmış endeks geçmişini korur.

Ürün tipi endeksi fiyat relatiflerinin geometrik ortalamasıdır:

```text
I(type,t) = 100 × geometric_mean(relative(i,t))
```

Bir ürün tipinin yayımlanabilmesi için kendi `min_skus` eşiğini ve baz panelinin en az `%50` karşılaştırılabilir kapsamasını koruması gerekir.

### 5. Kontrollü panel yenileme

Geçici stok kaybı günlük SKU ikamesine yol açmaz. Bir ürün tipi:

- panelinin `%80`'inden azını **7 gün üst üste** gözlemliyorsa,
- ilgili eski slot en az 7 gündür kayıpsa,
- yeni aday SKU en az 3 ardışık gün görünmüşse,

collector paneli kontrollü biçimde yenileyebilir. Bir günde panelin en fazla `%20`'si yenilenir.

Yeni SKU eski slot kimliğini devralır. Aktivasyon gününde yeni SKU'nun bağlı birim fiyatı eski slotun **son bilinen bağlı fiyat seviyesine** bir bridge factor ile bağlanır. Bu son seviye, legacy snapshot'lar dahil geçmiş snapshot'lardan seed edilir; güvenilir eski seviye yoksa otomatik ikame yapılmaz. Böylece marka/SKU değişiminin kendisi fiyat artışı veya düşüşü olarak yazılmaz; bundan sonraki gerçek fiyat hareketi izlenir.

### 6. Kategori ve ana endeks

Ürün tipi endeksleri 12 ana market kategorisine toplanır. Kategori içinde ürün tipleri şimdilik eşit araştırma payına sahiptir. Ana kategoriler `config/categories.json` içindeki araştırma ağırlıklarıyla birleştirilir.

Ana endeks ve kategori endeksleri en az `%60` ağırlık kapsamasıyla yayımlanır. Eksik gözlemlerin ağırlıkları mevcut karşılaştırılabilir panel üzerinde yeniden normalize edilir; model tabanlı fiyat imputasyonu yapılmaz.

Ağırlıklar **TÜİK'in resmî tüketim ağırlıkları değildir**.

Ayrıntılar: [`METHOD.md`](METHOD.md).

## Üretilen veriler

```text
data/v0.3/
├── snapshots/
│   └── YYYY-MM-DD.csv
├── type_indices.csv
├── category_indices.csv
├── index.csv
└── latest-errors.json
```

Yeni source-aware günlük snapshot satırları yaklaşık olarak şunları içerir:

```text
date, group, type_id, slot_id, product_key, title,
quantity, unit, price, unit_price, linked_unit_price,
offer_count, raw_offer_count, source_count, source_ids,
markets, source_mode, generation
```

`product_key` gerçek SKU'yu, `slot_id` ise endeks sürekliliğini sağlayan panel kimliğini temsil eder. `unit_price` gözlenen sabit-depot fiyat seviyesini, `linked_unit_price` ise endekste kullanılan kaynak/panel sürekliliği ayarlı seviyeyi tutar.

## Otomasyon

Ana workflow:

```text
.github/workflows/daily.yml
```

Her gün:

```text
05:45 UTC
```

çalışır. Bu saat Türkiye'de **08:45**, Berlin'de yaz saatinde **07:45 CEST**, kış saatinde **06:45 CET**'tir. GitHub Actions planlanan işleri yoğunluk nedeniyle gecikmeli başlatabilir.

Pipeline:

```text
pytest
  ↓
source-aware ürün tipi / SKU toplama
  ↓
panel kalite doğrulaması
  ↓
ürün tipi + kategori + ana endeks
  ↓
README + enflasyon grafiği
  ↓
yayımlanmış tarih ve grafik regression guard
  ↓
bot commit
```

Kod değişikliklerinde ayrıca `.github/workflows/validate.yml` çalışır. Bu workflow önce mevcut snapshot'lardan seriyi ve `charts/index.svg` dosyasını yeniden üretir, **2026-08-16 = 100.0000** ve **2026-08-17 = 100.1338** değerlerini regression anchor olarak doğrular; ardından gerçek Market Fiyatı API'siyle **commit atmayan canlı collector smoke testi** yapar.

Workflow GitHub arayüzünden manuel de tetiklenebilir:

**Actions → Daily Açık Sepet → Run workflow**

## Yerelde çalıştırma

Python 3.12+ önerilir.

```bash
git clone https://github.com/onurcan-b/acik-sepet.git
cd acik-sepet
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
python -m acik_sepet.collect
python -m acik_sepet.validate
python -m acik_sepet.index
python -m acik_sepet.report
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

## v0.2 geçmişi ve v0.3 sürekliliği

v0.3 yeni bir metodoloji ve yeni baz dönemidir. Eski 150-SKU serisi geriye dönük yeniden yazılmaz. v0.2 gözlemleri Git geçmişinde korunur.

v0.3 içinde source-aware toplama ve kontrollü panel yenileme **aynı seri içinde bridge edilerek** uygulanır; başlangıç baz tarihi değişmez. CI regression guard yayımlanmış ilk değerlerin değişmesini engeller.

## Sınırlamalar

Açık Sepet şu anda:

- yalnızca markette satılan mallara odaklanır,
- resmî TÜFE kapsamını temsil etmez,
- şehir ve mağaza örneklemesini nüfus ağırlıklı ulusal bir tasarımla modellemez,
- ürün başlığından gramaj/hacim/adet ayrıştırdığı için hatalı katalog başlıklarından etkilenebilir,
- promosyonları gerçek tüketici fiyatı olarak gözlemler,
- kategori içindeki ürün tipi ağırlıklarını henüz tüketim harcaması verisiyle kalibre etmez,
- mevsimsellik ve kalite değişimi için hedonik düzeltme uygulamaz.

Bu nedenle seri **araştırma ve yüksek frekanslı market fiyatı göstergesi** olarak değerlendirilmelidir.

## Veri kaynağı

Proje [`marketfiyati.org.tr`](https://marketfiyati.org.tr/) arayüzünün kullandığı veri servisine düşük ve kontrollü hacimde ürün-tipi sorguları gönderir. Repo kaynağın toplu aynasını oluşturmaz; yalnızca sabit/bridge edilmiş paneller için gerekli günlük gözlemleri saklar.

Kaynak ve yeniden kullanım notları: [`NOTICE.md`](NOTICE.md).

## Katkı

Kod, ürün tipi sınıflandırması, parser testleri ve metodoloji geliştirmeleri pull request ile yapılabilir. Otomatik üretilen `data/` ve `state/` dosyalarını elle değiştirmek yerine problemi üreten toplama veya sınıflandırma katmanının düzeltilmesi tercih edilir.

Katkı rehberi: [`CONTRIBUTING.md`](CONTRIBUTING.md)

## Lisans ve veri hakları

- Özgün Python kodu, otomasyon ve proje yapılandırması MIT lisansı altındadır: [`LICENSE-CODE`](LICENSE-CODE).
- Kaynak fiyat verileri üzerinde proje ayrıca bir telif veya yeniden lisanslama iddiasında bulunmaz.
- Ayrıntılar: [`LICENSE`](LICENSE) ve [`NOTICE.md`](NOTICE.md).

## Proje sahibi

**Onurcan Büyükkalkan**  
[buyukkalkan.net](https://buyukkalkan.net/)

---

Açık Sepet bağımsız ve deneysel bir projedir; herhangi bir kamu kurumunun resmî istatistik yayını değildir.
