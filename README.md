# Açık Sepet

Türkiye'deki zincir market fiyatlarını **ürün tipi → çoklu SKU → kategori → ana endeks** hiyerarşisiyle günlük izleyen açık ve yeniden üretilebilir deneysel fiyat endeksi.

[![Daily Açık Sepet](https://github.com/onurcan-b/acik-sepet/actions/workflows/daily.yml/badge.svg)](https://github.com/onurcan-b/acik-sepet/actions/workflows/daily.yml)
![Python](https://img.shields.io/badge/Python-3.12+-blue)
![Data](https://img.shields.io/badge/data-daily-informational)

> **Açık Sepet resmî TÜFE değildir.** Kira, konut, ulaşım, sağlık, eğitim ve hizmetleri kapsamaz. Amaç, markette satılan malların fiyat hareketini yüksek frekansta, şeffaf bir metodolojiyle ölçmektir.

![Açık Sepet günlük endeksi](charts/index.svg)

<!-- STATS_START -->
- **Durum:** İlk v0.3 gözlemi bekleniyor.
<!-- STATS_END -->

## Son 24 saatte

<!-- MOVERS_START -->
İkinci v0.3 gözlemi geldikten sonra ürün tipi hareketleri burada gösterilecek.
<!-- MOVERS_END -->

## Veri kalitesi

<!-- QUALITY_START -->
İlk kalite ölçümü bekleniyor.
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
Gramaj / litre / adet normalizasyonu
    ↓
Aynı SKU'nun zaman içindeki birim-fiyat relatifi
    ↓
Ürün tipi elementary endeksi
    ↓
12 ana market kategorisi
    ↓
Açık Sepet Market Endeksi
```

## Temel metodoloji

### 1. Ürün tipi paneli

Ürün tipleri `config/product_types.tsv` dosyasında tanımlanır. Her ürün tipi için:

- arama sorgusu,
- beklenen ölçü birimi (`mass`, `volume`, `count`),
- hedef SKU sayısı,
- minimum SKU sayısı,
- dahil / hariç kelime kuralları

saklanır.

İlk başarılı v0.3 çalışmasında her ürün tipi için bir SKU paneli oluşturulur ve `state/v0.3-panels.json` içinde sabitlenir. Günlük çalışmalarda panel başka ürünlerle sessizce doldurulmaz. Panel değişikliği bilinçli bir metodoloji güncellemesi gerektirir.

### 2. Birim fiyat

Paket bilgileri başlıktan normalize edilir:

```text
500 g       → 0.5 kg
2 x 160 g   → 0.32 kg
750 ml      → 0.75 L
6 x 200 ml  → 1.2 L
12'li       → 12 adet
```

Böylece aynı SKU'nun paket boyutu değişirse bu değişim fiyat sinyaline yansıyabilir.

**Farklı markaların TL/kg veya TL/L seviyeleri doğrudan ortalanmaz.** Birim fiyat, aynı SKU'nun baz döneme göre fiyat relatifini hesaplamak için kullanılır.

### 3. Ürün tipi endeksi

Bir SKU için:

```text
relative(i,t) = unit_price(i,t) / unit_price(i,base)
```

Ürün tipi endeksi, hem bazda hem güncel günde bulunan sabit panel SKU'larının fiyat relatiflerinin geometrik ortalamasıdır:

```text
I(type,t) = 100 × geometric_mean(relative(i,t))
```

Bu sayede tek bir şampuandaki `%40` kampanya, şampuan kategorisini tek başına `%40` aşağı çekmez; çoklu-SKU panelindeki bir gözlem olur.

Bir ürün tipinin yayımlanabilmesi için:

- kendi `min_skus` eşiğini karşılaması,
- baz panelinin en az `%50`'sinin güncel günde karşılaştırılabilir olması

gerekir.

### 4. Kategori ve ana endeks

Ürün tipi endeksleri önce 12 ana market kategorisine toplanır. Kategori içinde ürün tipleri şimdilik eşit araştırma payına sahiptir. Ana kategoriler `config/categories.json` içindeki araştırma ağırlıklarıyla birleştirilir.

Ana endeks ve kategori endeksleri en az `%60` ağırlık kapsamasıyla yayımlanır. Eksik gözlemlerin ağırlıkları mevcut karşılaştırılabilir panel üzerinde yeniden normalize edilir; model tabanlı fiyat imputasyonu yapılmaz.

Ağırlıklar **TÜİK'in resmî tüketim ağırlıkları değildir**.

Ayrıntılar: [`METHOD.md`](METHOD.md).

## Üretilen veriler

v0.3 verileri ayrı bir namespace altında tutulur:

```text
data/v0.3/
├── snapshots/
│   └── YYYY-MM-DD.csv
├── type_indices.csv
├── category_indices.csv
├── index.csv
└── latest-errors.json
```

### Günlük SKU snapshot

Her satır yaklaşık olarak şunları içerir:

```text
date, group, type_id, product_key, title,
quantity, unit, price, unit_price, offer_count
```

### Ürün tipi endeksleri

`data/v0.3/type_indices.csv`

```text
date,type_id,label,group,index,coverage,skus,baseline_skus,baseline_date
```

### Kategori endeksleri

`data/v0.3/category_indices.csv`

### Ana endeks

`data/v0.3/index.csv`

## Panel sürekliliği ve eksik ürünler

Açık Sepet karşılaştırılabilirliği ham SKU sayısından önce tutar.

Bir panel SKU'su bir gün bulunamazsa:

1. başka marka otomatik olarak onun yerine geçirilmez,
2. ürün tipi yeterli sayıda aynı-SKU gözlemine sahipse kalan panelle hesaplanır,
3. panel kapsaması ayrıca yayımlanır,
4. minimum eşik altına düşerse ürün tipi o gün endekse girmez.

Bu yaklaşım katalog değişimini fiyat değişimi sanma riskini azaltırken tekil stok kayıplarına karşı paneli dayanıklı tutar.

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

Pipeline sırası:

```text
pytest
  ↓
ürün tipi aramaları + sabit panel gözlemi
  ↓
kalite doğrulama
  ↓
ürün tipi endeksleri
  ↓
kategori + ana endeks
  ↓
README + grafik
  ↓
bot commit
```

Workflow ayrıca GitHub arayüzünden manuel tetiklenebilir:

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
python -m acik_sepet.collect_v03
python -m acik_sepet.validate_v03
python -m acik_sepet.index_v03
python -m acik_sepet.report_v03
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

## v0.2 geçmişi

v0.3 yeni bir metodoloji ve yeni baz dönemidir. Eski 150-SKU serisi yeni metodolojiyle geriye dönük yeniden yazılmaz. v0.2 gözlemleri Git geçmişinde korunur; v0.3 serisi kendi `data/v0.3/` dizininde başlar.

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

MVP, [`marketfiyati.org.tr`](https://marketfiyati.org.tr/) arayüzünün kullandığı veri servisine düşük ve kontrollü hacimde ürün-tipi sorguları gönderir. Repo kaynağın toplu aynasını oluşturmaz; yalnızca sabit paneller için gerekli günlük gözlemleri saklar.

Kaynak ve yeniden kullanım notları: [`NOTICE.md`](NOTICE.md).

## Katkı

Kod, ürün tipi sınıflandırması, parser testleri ve metodoloji geliştirmeleri pull request ile yapılabilir.

Otomatik üretilen `data/` ve `state/` dosyalarının elle değiştirilmesi yerine problemi üreten toplama veya sınıflandırma katmanının düzeltilmesi tercih edilir.

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
