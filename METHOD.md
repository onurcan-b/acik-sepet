# Metodoloji — v0.4

Açık Sepet, zincir marketlerde satılan malların günlük fiyat hareketini izleyen deneysel bir çoklu-SKU panel endeksidir. v0.4, ürün sınıflandırmasını sıkılaştırdığı için **2026-09-02 = 100** ile yeni seri başlatır. v0.3 geçmişi değiştirilmez.

## 1. Ürün tipi ve sınıflandırma

Temel ekonomik gözlem birimi ürün tipidir: pirinç, yoğurt, domates, şampuan gibi. Her ürün tipi birden fazla gerçek SKU ile temsil edilir.

Kurallar iki açık dosyada tutulur:

- `config/product_types.tsv`: sorgu, beklenen birim, hedef/minimum SKU, zorunlu ve hariç başlık kuralları,
- `config/api_categories.json`: Market Fiyatı kategori ağacındaki `menu_category`, `main_category` veya `sub_category` filtresi.

Bir adayın kabul edilmesi için sırasıyla:

1. API isteğinin tanımlı kategori filtresiyle yapılması,
2. dönen ürünün kategori alanlarının filtreyi gerçekten doğrulaması,
3. başlıktaki **bütün** zorunlu kuralların eşleşmesi,
4. hiçbir hariç kuralın eşleşmemesi,
5. beklenen miktar/birim bilgisinin çözülebilmesi,
6. en az bir pozitif fiyat teklifinin bulunması

gerekir.

Zorunlu kuralların yarısını geçmek gibi bir eşik yoktur. Alternatifler `|` ile yazılabilir; örneğin `cherry|çeri|kokteyl,domates`. Kısa kelimeler tam kelime olarak eşleşir; böylece `bal`, `balık` kelimesine eşleşmez. Dört veya daha uzun köklerde Türkçe ekler için önek eşleşmesine izin verilir.

Kategori ağacı da hatasız kabul edilmez. Kategori, başlık ve birim kontrolleri birbirinin yerine geçmez; birlikte uygulanır.

## 2. Miktar ve birim fiyat

Paket miktarında öncelik API'nin normalize `refinedVolumeOrWeight` alanındadır. Bu alan kullanılamazsa ürün başlığı parse edilir.

Ortak birimler:

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
```

Paket fiyatından hesaplanan birim fiyat:

```text
unit_price = package_price / package_quantity
```

Her teklif için API'nin `unitPriceValue` alanı varsa hesaplanan değerle karşılaştırılır. Medyan düzeyinde fark `%5` sınırını aşarsa aday panele alınmaz. Snapshot'ta miktarın kaynağı, API birim fiyatı ve fark ayrıca saklanır.

## 3. Sabit panel ve SKU sahipliği

İlk başarılı v0.4 toplamasında ürün tipi panelleri oluşturulur ve `state/v0.4-panels.json` içinde sabitlenir. Aynı gerçek SKU iki ürün tipine ait olamaz.

Gerçek ürün kimliği `product_key`, endeks sürekliliği kimliği `slot_id` alanıdır. Başlangıçta ikisi aynıdır. Kontrollü ikamede ürün değişebilir ama slot devam eder.

Minimum SKU eşiği ürün tipine göre değişir. Kaynakta yeterli ürün yoksa tip yayımlanmaz; hedefi doldurmak amacıyla daha düşük kaliteli eşleşme alınmaz.

## 4. Depot/kaynak sürekliliği

Bir SKU için birden fazla market/depot teklifi bulunabilir. İlk gözlemde kararlı `depotId` değerleri sabitlenir ve her kaynak için anchor fiyatı tutulur.

```text
r(s,t) = p(s,t) / p(s,anchor)

P_linked(t)
  = P_all_offers(anchor)
    × geometric_mean(r(s,t) for observed pinned sources)
```

Sonraki günlerde yeni depotlar otomatik olarak fiyat seviyesine girmez. Sabit depolardan biri geçici kaybolduğunda, kalan depoların kendi fiyat relatifleri değişmediyse SKU seviyesi yalnızca kaynak kompozisyonu nedeniyle oynamaz.

Hiçbir sabit kaynak yeniden görünmezse SKU o gün eksik sayılır.

## 5. Ürün tipi endeksi

Aynı panel slotunun bağlı birim fiyat relatifi:

```text
r(i,t) = linked_unit_price(i,t) / linked_unit_price(i,base)
```

Ürün tipi endeksi Jevons-benzeri geometrik ortalamadır:

```text
I(k,t) = 100 × exp(mean(log(r(i,t))))
```

Yayın için:

- bazda ve güncel günde en az `min_skus` ortak slot,
- baz slotlarının en az `%50` güncel kapsaması

gerekir.

## 6. Kategori ve ana endeks

130 ürün tipi 12 araştırma kategorisine ayrılır. Kategori içinde uygun ürün tipleri eşit payla birleştirilir. Ana kategoriler `config/categories.json` içindeki araştırma ağırlıklarıyla toplanır.

Önemli v0.4 değişikliği: kategori kapsamasının paydası yalnızca baseline'da yayımlanabilen tipler değil, o kategori için **konfigüre edilmiş bütün ürün tipleridir**.

```text
category_coverage
  = sufficient_configured_types / all_configured_types
```

Kategori en az `%60` tip ağırlık kapsamasıyla yayımlanır. Ana endeks de en az `%60` kategori ağırlık kapsaması ister. Eksik paylar mevcut gözlemler üzerinde yeniden normalize edilir; model tabanlı imputasyon yapılmaz.

Bu ağırlıklar TÜİK tüketim harcaması ağırlıkları değildir.

## 7. Kontrollü panel yenileme

Geçici stok kaybı günlük ikameye yol açmaz. Otomatik yenileme ancak:

1. aktif panel kapsaması `%80` altına 7 gün üst üste düşerse,
2. eski slot en az 7 gündür kayıpsa,
3. yeni aday en az 3 ardışık gün görünmüşse

başlayabilir. Bir çalışmada panelin en fazla `%20`'si yenilenir.

Yeni SKU eski slotun son bağlı birim fiyat seviyesine bridge edilir:

```text
replacement_bridge
  = old_slot_last_linked_price / new_sku_initial_linked_unit_price
```

Güvenilir eski seviye yoksa ikame yapılmaz.

## 8. Doğrulama ve yayın

Günlük doğrulama şunları sert hata olarak kabul eder:

- aynı SKU veya slotun birden fazla tipe yazılması,
- pozitif/sonlu olmayan fiyat,
- `price / quantity` formülünün snapshot birim fiyatıyla uyuşmaması,
- API birim fiyat farkının `%5` sınırını aşması,
- başlık veya kategori kuralını artık geçmeyen ürün,
- minimum toplam SKU veya ürün tipi kapsamasının altına düşülmesi.

CI, v0.4 baseline değerini ve üç README grafiğinin üretilebildiğini de kilitler.

## 9. Kapsam ve yorum

Açık Sepet genel tüketici fiyat endeksi değildir. Kira, konut, ulaşım, sağlık, eğitim ve hizmetleri kapsamaz. Şehir/mağaza örneklemi nüfus ağırlıklı değildir; kategori ağırlıkları gerçek tüketim payı değildir; kampanyalar gözlenen fiyat sayılır; resmî istatistik düzeyinde mevsimsellik veya kalite düzeltmesi yapılmaz.

Bu seri yüksek frekanslı, açık ve deneysel bir market fiyat göstergesi olarak yorumlanmalıdır.
