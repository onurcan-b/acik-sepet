# Metodoloji — v0.3

Açık Sepet, zincir marketlerde satılan malların günlük fiyat hareketini izleyen deneysel bir çoklu-SKU panel endeksidir.

## 1. Ölçüm birimi

v0.2'de temel gözlem birimi tek bir sabit SKU idi. v0.3'te temel ekonomik ölçüm birimi **ürün tipi**dir.

Örnekler:

- şampuan,
- spagetti makarna,
- pirinç,
- yoğurt,
- ayçiçek yağı,
- domates.

Her ürün tipi birden fazla sabit SKU'dan oluşur. Ürün tipleri `config/product_types.tsv` içinde tanımlanır.

## 2. Sabit SKU paneli

İlk başarılı v0.3 toplamasında her ürün tipi için arama sonuçlarından uygun SKU'lar seçilir. Seçim sırasında:

- dahil / hariç kelime kuralları,
- beklenen ölçü biriminin parse edilebilmesi,
- geçerli fiyat teklifi bulunması,
- aynı SKU'nun başka bir ürün tipinde daha önce sahiplenilmemiş olması

kontrol edilir.

Panel `state/v0.3-panels.json` içinde sabitlenir. Günlük çalışmalarda yeni bir SKU otomatik olarak kayıp SKU'nun yerine geçirilmez. Panel kompozisyonu ancak açık bir metodoloji/panel güncellemesiyle değiştirilmelidir.

Bu kural, ürün kalitesi veya marka değişimini yanlışlıkla fiyat değişimi olarak ölçme riskini azaltır.

## 3. Birim normalizasyonu

Ürün başlığındaki paket miktarı ortak birime çevrilir:

- kütle → kg,
- hacim → litre,
- adetli ürün → count.

Desteklenen örnekler:

```text
500 g       → 0.5 kg
2 x 160 g   → 0.32 kg
750 ml      → 0.75 L
6 x 200 ml  → 1.2 L
12'li       → 12 count
10 adet     → 10 count
```

SKU birim fiyatı:

```text
u(i,t) = package_price(i,t) / package_quantity(i,t)
```

olarak hesaplanır.

Birim fiyat seviyeleri farklı markalar arasında doğrudan ortalanmaz. Normalizasyonun temel amacı aynı SKU'nun zaman içindeki relatifi ile paket küçülmesi/büyümesinin fiyat sinyaline yansıyabilmesidir.

## 4. SKU fiyatı

Bir SKU için aynı gün Market Fiyatı sonucunda bulunan geçerli mağaza/depot fiyatlarının medyanı alınır. Günlük snapshot'ta tekliflerin tamamı yerine yalnızca medyan paket fiyatı, birim fiyat ve teklif sayısı saklanır.

Bu tercih günlük veri boyutunu sınırlarken tek bir mağaza fiyatına bağımlılığı azaltır.

## 5. Elementary ürün tipi endeksi

Baz gününde ve güncel günde birlikte gözlenen aynı panel SKU'ları için:

```text
r(i,t) = u(i,t) / u(i,0)
```

hesaplanır.

Ürün tipi endeksi fiyat relatiflerinin geometrik ortalamasıdır:

```text
I(k,t) = 100 × exp(mean(log(r(i,t))))
```

Bu Jevons-benzeri elementary yaklaşım, tek bir SKU'daki büyük kampanyanın bütün ürün tipini tek başına belirlemesini engeller.

Bir ürün tipinin yayımlanması için:

- baz gününde en az kendi `min_skus` sayısı kadar SKU bulunması,
- güncel günde en az `min_skus` aynı SKU'nun bulunması,
- baz panel SKU'larının en az %50'sinin güncel günde karşılaştırılabilmesi

gerekir.

## 6. Kategori endeksi

Ürün tipleri 12 market grubuna ayrılır. Aynı kategori içindeki uygun ürün tipleri v0.3'te eşit araştırma payıyla birleştirilir.

Kategori endeksi, mevcut ürün tipi relatiflerinin ağırlıklı aritmetik ortalamasıdır. Kategori en az %60 ürün-tipi ağırlık kapsamasıyla yayımlanır.

Bu kategori-içi ağırlıklar tüketim harcaması ağırlıkları değildir; ileriki sürümlerde ampirik harcama verisiyle kalibre edilmesi planlanmaktadır.

## 7. Ana Açık Sepet endeksi

12 ana grup `config/categories.json` içindeki araştırma ağırlıklarıyla birleştirilir.

Ana endeks için en az %60 kategori ağırlık kapsaması gerekir. Eksik kategori/ürün tipi payları mevcut karşılaştırılabilir panel üzerinde yeniden normalize edilir.

Model tabanlı fiyat imputasyonu yapılmaz.

## 8. Eksik gözlem

Bir SKU geçici olarak bulunamazsa başka bir SKU ile günlük ikame yapılmaz. Ürün tipi yeterli paneli koruyorsa kalan aynı-SKU relatifleriyle hesaplanmaya devam eder. Eşik altına düşerse o ürün tipi ilgili gün yayımlanmaz.

Bu nedenle veri kalitesinde izlenen temel göstergeler:

- aktif ürün tipi sayısı,
- karşılaştırılabilir SKU sayısı,
- ürün tipi panel kapsaması,
- kategori ağırlık kapsaması,
- parser veya API hatalarıdır.

## 9. Panel yenileme

Yeni ürünler, tamamen kaybolan SKU'lar veya katalog yapısındaki kalıcı değişiklikler zamanla panel yenilemesini gerektirebilir. Panel yenilemesi günlük collector içinde otomatik yapılmaz.

Anlamlı panel/metodoloji değişikliği:

1. yeni sürüm numarası,
2. yeni baz dönemi,
3. değişiklik notu

gerektirir.

## 10. v0.2 ile karşılaştırılabilirlik

v0.3 farklı bir elementary endeks metodolojisine sahiptir. v0.2'nin 150-SKU serisi v0.3 ile geriye dönük yeniden hesaplanmaz. Eski seri Git geçmişinde korunur; v0.3 kendi `data/v0.3/` namespace'inde yeni bazla başlar.

## 11. Sınırlamalar

Açık Sepet genel tüketici fiyat endeksi değildir. Özellikle:

- kira, konut, ulaştırma, sağlık, eğitim ve hizmetleri kapsamaz,
- şehir/mağaza örneklemesi nüfus ağırlıklı ulusal örneklem değildir,
- ürün başlığındaki gramaj/hacim/adet bilgisinin doğruluğuna bağlıdır,
- promosyon fiyatlarını gözlenen tüketici fiyatı olarak kabul eder,
- kategori içindeki ürün tipi ağırlıkları henüz gerçek harcama paylarına dayanmaz,
- kalite değişimi ve mevsimsellik için resmî istatistiklerdeki düzeyde düzeltme uygulamaz.

Seri araştırma ve yüksek frekanslı market fiyatı göstergesi olarak yorumlanmalıdır.
