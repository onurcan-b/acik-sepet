# Metodoloji — v0.2

Açık Sepet, market ürünlerinin günlük fiyat hareketini izleyen deneysel bir sabit-sepet endeksidir.

## Sepet

- 150 ürün
- 12 grup
- grup ağırlıkları `config/categories.json`
- ürün tanımları `config/basket.tsv`

Grup ağırlıkları araştırma amaçlıdır ve resmi kurum ağırlıkları değildir.

## Süreklilik

İlk başarılı eşleşmede ürün kimliği sabitlenir. Mümkün olduğunda temsilci mağaza/depot kimliği de sabitlenir. Sonraki gün başka bir SKU veya kaynak dönerse seri sessizce değiştirilmez; gözlem eksik sayılır.

## Hesap

Her ürünün günlük fiyatı, mevcut sabit kaynak fiyatlarının medyanıdır. Baz gündeki fiyat 100 kabul edilir. Grup içinde ürünler eşit pay alır; gruplar daha sonra `config/categories.json` içindeki araştırma ağırlıklarıyla birleştirilir.

Günlük ana endeks, hem baz hem güncel günde fiyatı bulunan ürünlerin ağırlıklı fiyat relatiflerinin ortalamasıdır. Eksik ürünlerin payı yeniden normalize edilir ve kapsama ayrıca yayımlanır.

Ana seri için en az **%60 ağırlıklı kapsama** gerekir. Eksik fiyatlara şu aşamada model tabanlı imputasyon yapılmaz.

## Sınırlamalar

Bu çalışma genel tüketici fiyat endeksi değildir. Kira, konut, ulaşım, sağlık, eğitim ve hizmetleri kapsamaz. Şehir ve mağaza örneklemesi ileriki sürümlerde genişletilecektir.

Sepet veya ağırlık metodolojisi anlamlı biçimde değiştiğinde yeni bir sepet versiyonu ve yeni baz dönemi başlatılır.
