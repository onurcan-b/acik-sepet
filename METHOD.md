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

Her ürün tipi birden fazla SKU'dan oluşan panel ile ölçülür. Ürün tipleri `config/product_types.tsv` içinde tanımlanır.

## 2. Sabit panel slotları

İlk başarılı v0.3 toplamasında her ürün tipi için arama sonuçlarından uygun SKU'lar seçilir. Seçim sırasında:

- dahil / hariç kelime kuralları,
- beklenen ölçü biriminin parse edilebilmesi,
- geçerli fiyat teklifi bulunması,
- aynı SKU'nun başka bir ürün tipinde sahiplenilmemiş olması

kontrol edilir.

Panel `state/v0.3-panels.json` içinde saklanır. Her başlangıç SKU'su aynı zamanda kalıcı bir **slot_id** oluşturur. Endeks kimliği gerçek SKU kimliğinden ayrıdır; bu ayrım daha sonra kalıcı ürün kaybında kontrollü ikame yapılırken serinin kopmamasını sağlar.

## 3. Kaynak/depot sürekliliği

Bir SKU için aynı gün birden fazla market/depot fiyatı bulunabilir. Collector her teklif için mümkünse `depotId`; bu yoksa market/depot adından türetilen kararlı bir kaynak kimliği kullanır.

Source-aware toplama devreye girdiğinde SKU'nun mevcut kaynak kümesi sabitlenir. Sonraki günlerde:

- yeni görünen kaynaklar otomatik olarak fiyat hesabına eklenmez,
- sabit kaynakların mevcut olanları kullanılır,
- sabit kaynaklardan hiçbiri görünmezse SKU o gün eksik sayılır.

Bu, temsilci mağaza/depot rotasyonunun fiyat değişimi sanılması riskini azaltır.

Kaynak sabitlemenin ilk gününde eski tüm-teklif medyanı ile sabit-kaynak medyanı arasında:

```text
source_bridge = old_all_offer_price / pinned_source_price
```

hesaplanır. Endekste kullanılan bağlı fiyat seviyesi bu katsayıyla ölçeklenir. Böylece yalnızca kaynak politikası değiştiği için seri sıçramaz.

## 4. Birim normalizasyonu

Ürün başlığındaki paket miktarı ortak birime çevrilir:

- kütle → kg,
- hacim → litre,
- adetli ürün → count.

Örnekler:

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

Birim fiyat seviyeleri farklı markalar arasında doğrudan ortalanmaz. Normalizasyonun amacı aynı panel slotunun zaman içindeki fiyat relatifini ve paket küçülmesi/büyümesini ölçmektir.

## 5. Günlük SKU fiyatı

Bir SKU için sabitlenmiş kaynaklardan gelen geçerli fiyatların medyanı alınır. Snapshot'ta hem gerçek sabit-kaynak birim fiyatı (`unit_price`) hem de metodoloji sürekliliği için bridge edilmiş değer (`linked_unit_price`) tutulur.

Legacy v0.3 snapshot'larında `slot_id` ve `linked_unit_price` alanları yoktur. Index loader bu satırlarda:

```text
slot_id = product_key
linked_unit_price = unit_price
```

kabul eder. Böylece daha önce yayımlanmış v0.3 geçmişi yeniden yorumlanmaz.

## 6. Elementary ürün tipi endeksi

Baz gününde ve güncel günde birlikte gözlenen aynı panel slotları için:

```text
r(i,t) = linked_unit_price(i,t) / linked_unit_price(i,0)
```

hesaplanır.

Ürün tipi endeksi fiyat relatiflerinin geometrik ortalamasıdır:

```text
I(k,t) = 100 × exp(mean(log(r(i,t))))
```

Bu Jevons-benzeri elementary yaklaşım, tek bir SKU'daki büyük kampanyanın bütün ürün tipini tek başına belirlemesini engeller.

Bir ürün tipinin yayımlanması için:

- baz gününde en az kendi `min_skus` sayısı kadar slot bulunması,
- güncel günde en az `min_skus` slotun karşılaştırılabilmesi,
- baz panel slotlarının en az %50'sinin güncel günde karşılaştırılabilir olması

gerekir.

## 7. Kategori endeksi

Ürün tipleri 12 market grubuna ayrılır. Aynı kategori içindeki uygun ürün tipleri v0.3'te eşit araştırma payıyla birleştirilir.

Kategori endeksi mevcut ürün tipi relatiflerinin ağırlıklı aritmetik ortalamasıdır. Kategori en az %60 ürün-tipi ağırlık kapsamasıyla yayımlanır.

Kategori-içi ağırlıklar tüketim harcaması ağırlıkları değildir.

## 8. Ana Açık Sepet endeksi

12 ana grup `config/categories.json` içindeki araştırma ağırlıklarıyla birleştirilir.

Ana endeks için en az %60 kategori ağırlık kapsaması gerekir. Eksik kategori/ürün tipi payları mevcut karşılaştırılabilir panel üzerinde yeniden normalize edilir.

Model tabanlı fiyat imputasyonu yapılmaz.

## 9. Eksik gözlem

Bir SKU geçici olarak bulunamazsa başka bir SKU ile günlük ikame yapılmaz. Ürün tipi yeterli paneli koruyorsa kalan slotlarla hesaplanmaya devam eder. Eşik altına düşerse ürün tipi ilgili gün yayımlanmaz.

İzlenen kalite göstergeleri:

- aktif ürün tipi sayısı,
- karşılaştırılabilir panel slotu/SKU sayısı,
- ürün tipi panel kapsaması,
- kategori ağırlık kapsaması,
- sabit kaynak kimliği bulunan gözlemler,
- parser/API hataları,
- yapılan bridge edilmiş panel yenilemeleri.

## 10. Otomatik ama bridge edilmiş panel yenileme

Panelin doğal olarak yaşlanması beklenir. Kalıcı olarak kaybolan SKU'lar hiçbir zaman yenilenmezse coverage zaman içinde tek yönlü azalır. Buna karşılık günlük serbest ikame de kompozisyon değişimini fiyat değişimi sanabilir.

v0.3 bu ikisi arasında kontrollü bir kural kullanır. Bir ürün tipi için otomatik yenileme ancak:

1. aktif panel kapsaması `%80` altına **7 ardışık gün** düşerse,
2. yenilenecek eski slot en az 7 gündür gözlenmiyorsa,
3. yeni aday SKU en az 3 ardışık gün görünmüşse

başlar.

Bir çalışmada panelin en fazla `%20`'si yenilenebilir.

Yeni SKU, kaybolan SKU'nun **slot_id** değerini devralır. Aktivasyon gününde:

```text
replacement_bridge = old_slot_last_linked_price / new_sku_source_adjusted_unit_price
```

hesaplanır. Böylece yeni ürünün farklı fiyat seviyesi endekste tek seferlik artış/düşüş oluşturmaz. Yeni SKU'nun sonraki fiyat hareketleri aynı slot üzerinden ölçülür.

Bu yenileme gerçek SKU kimliğini gizlemez: snapshot'ta `product_key` güncel SKU'yu, `slot_id` ise zincirlenmiş endeks kimliğini gösterir; panel state önceki SKU kimliğini ve yenileme tarihini saklar.

## 11. Yayın geçmişi koruması

Source-aware toplama ve bridge edilmiş panel yenileme mevcut v0.3 serisini sıfırlamaz. İlk yayımlanmış değerler CI içinde regression anchor olarak kilitlenmiştir:

```text
2026-08-16 = 100.0000
2026-08-17 = 100.1338
```

Pull request validation ve günlük workflow endeksi/`charts/index.svg` grafiğini yeniden üretir; bu anchor'lar değişirse job başarısız olur ve bot commit atmaz.

## 12. v0.2 ile karşılaştırılabilirlik

v0.3 farklı bir elementary endeks metodolojisine sahiptir. v0.2'nin 150-SKU serisi v0.3 ile geriye dönük yeniden hesaplanmaz. Eski seri Git geçmişinde korunur; v0.3 kendi `data/v0.3/` namespace'inde 2026-08-16 baz tarihiyle başlar.

## 13. Sınırlamalar

Açık Sepet genel tüketici fiyat endeksi değildir. Özellikle:

- kira, konut, ulaştırma, sağlık, eğitim ve hizmetleri kapsamaz,
- şehir/mağaza örneklemesi nüfus ağırlıklı ulusal örneklem değildir,
- ürün başlığındaki gramaj/hacim/adet bilgisinin doğruluğuna bağlıdır,
- promosyon fiyatlarını gözlenen tüketici fiyatı olarak kabul eder,
- kategori içindeki ürün tipi ağırlıkları henüz gerçek harcama paylarına dayanmaz,
- kalite değişimi ve mevsimsellik için resmî istatistiklerdeki düzeyde düzeltme uygulamaz.

Seri araştırma ve yüksek frekanslı market fiyatı göstergesi olarak yorumlanmalıdır.
