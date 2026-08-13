# Metodoloji — MVP v0.1

Açık Sepet şu aşamada **deneysel bir teknik MVP**'dir; resmi TÜFE değildir ve TÜİK TÜFE'sinin yerine geçmez.

## Veri akışı

1. Üç sabit şehir koordinatında (İstanbul, Ankara, İzmir) küçük bir ürün sepeti için Market Fiyatı araması yapılır.
2. Bir ürün ilk kez eşleştiğinde dönen gerçek ürün/SKU başlığı `state/product-map.json` içinde sabitlenir.
3. Sonraki günlerde sabitlenmiş ürün bulunamazsa sessizce başka ürüne geçilmez; o gözlem eksik sayılır.
4. Her ürün/şehir için mevcut zincir market tekliflerinin medyanı hesaplanır.
5. Her ürün için şehir medyanlarının medyanı ulusal MVP fiyatı olarak alınır.
6. İlk yeterli snapshot baz gün = 100 olur.
7. Endeks, baz güne göre ürün fiyat relatiflerinin eşit ağırlıklı ortalamasıdır. Eksik ürünlerde ağırlıklar kalan ürünler üzerinde yeniden normalize edilir.
8. Kapsama %50'nin altına düşerse o gün için endeks değeri yayımlanmaz.

## Bilinen sınırlamalar

- Sepet küçük ve eşit ağırlıklıdır; tüketim harcaması ağırlıkları kullanılmıyor.
- SKU eşleştirme ilk koşuda otomatik yapılır ve manuel denetim gerektirebilir.
- Market Fiyatı API'si dokümante edilmiş, garanti edilmiş bir kamusal API değildir; endpoint değişebilir veya bot koruması devreye girebilir.
- Şube seçimi ve stok bulunurluğu zaman içinde gözlemleri etkileyebilir. Depot kimlikleri snapshot içinde saklanır.
- Bu MVP ham Market Fiyatı verisinin toplu bir aynası değildir; yalnızca küçük, sabit bir sepet için gerekli gözlemleri tutar.

## Sonraki metodoloji adımları

- Barkod/SKU kimliklerini doğrulayıp ilk sepeti elle dondurmak.
- Tüketim ağırlıkları için açık ve savunulabilir bir kaynak belirlemek.
- Şehir ağırlıkları eklemek.
- Zincir/şube sabitlemesini güçlendirmek.
- TÜİK aylık gıda TÜFE serisiyle karşılaştırmalı grafik üretmek.
