# Metodoloji — MVP v0.1

Açık Sepet şu aşamada **deneysel bir teknik MVP**'dir; resmi TÜFE değildir ve TÜİK TÜFE'sinin yerine geçmez.

## Veri akışı

1. Küçük ve sabit bir ürün sepeti için Market Fiyatı araması yapılır.
2. Bir ürün ilk kez eşleştiğinde dönen gerçek ürün/SKU başlığı `state/product-map.json` içinde sabitlenir.
3. Sonraki günlerde sabitlenmiş ürün bulunamazsa sessizce başka ürüne geçilmez; o gözlem eksik sayılır.
4. Her ürün için dönen zincir market tekliflerinin medyanı günlük MVP fiyatı olarak alınır.
5. İlk yeterli snapshot baz gün = 100 olur.
6. Endeks, baz güne göre ürün fiyat relatiflerinin eşit ağırlıklı ortalamasıdır. Eksik ürünlerde ağırlıklar kalan ürünler üzerinde yeniden normalize edilir.
7. Kapsama %50'nin altına düşerse o gün için endeks değeri yayımlanmaz.

## Bilinen sınırlamalar

- Sepet küçük ve eşit ağırlıklıdır; tüketim harcaması ağırlıkları kullanılmıyor.
- SKU eşleştirme ilk koşuda otomatik yapılır ve manuel denetim gerektirebilir.
- Market Fiyatı API'si dokümante edilmiş, garanti edilmiş bir kamusal API değildir; endpoint değişebilir veya bot koruması devreye girebilir.
- API'nin döndürdüğü temsilci mağaza/şube zaman içinde değişebilir. Bu nedenle `depot_id` ve `depot_name` snapshot içinde saklanır.
- Bu MVP ham Market Fiyatı verisinin toplu bir aynası değildir; yalnızca küçük, sabit bir sepet için gerekli gözlemleri tutar.

## Sonraki metodoloji adımları

- Barkod/SKU kimliklerini doğrulayıp ilk sepeti elle dondurmak.
- Tüketim ağırlıkları için açık ve savunulabilir bir kaynak belirlemek.
- Coğrafi/şehir bazlı örneklemeyi güvenilir biçimde eklemek.
- Zincir/şube sabitlemesini güçlendirmek.
- TÜİK aylık gıda TÜFE serisiyle karşılaştırmalı grafik üretmek.
