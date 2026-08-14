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

Bu, tek tek ürünlerde eksik gözlem olabileceği anlamına gelir. Ancak endeks tasarımı tek bir SKU'nun varlığına bağlı değildir: aynı kategori içinde yeterli sayıda karşılaştırılabilir ürün kaldığında kategori endeksi mevcut ürünlerin fiyat relatifleri üzerinden hesaplanmaya devam eder.

Bu yaklaşımın amacı iki riski aynı anda azaltmaktır:

1. farklı bir SKU'ya geçip ürün kalitesi/gramaj farkını yanlışlıkla fiyat değişimi sanmamak,
2. tek bir ürün geçici olarak bulunamadı diye bütün kategoriyi kaybetmemek.

## Hesap

Her ürünün günlük fiyatı, mevcut sabit kaynak fiyatlarının medyanıdır. Baz gündeki fiyat 100 kabul edilir. Grup içinde ürünler eşit pay alır; gruplar daha sonra `config/categories.json` içindeki araştırma ağırlıklarıyla birleştirilir.

Günlük ana endeks, hem baz hem güncel günde fiyatı bulunan ürünlerin ağırlıklı fiyat relatiflerinin ortalamasıdır. Eksik ürünlerin payı yeniden normalize edilir ve kapsama ayrıca yayımlanır.

### Kategori kapsaması

Her kategori alt endeksi için baz ve güncel günde birlikte gözlenebilen ürünlerin oranı hesaplanır.

- kategori endeksi için minimum kapsama: **%60**,
- ana seri için minimum ağırlıklı kapsama: **%60**,
- birleşik gıda endeksi yalnızca yeterli kapsamalı gıda gruplarını kullanır ve kalan grup ağırlıklarını yeniden normalize eder.

Örneğin 18 ürünlük bir kategoride 15 ürün karşılaştırılabiliyorsa kategori endeksi bu 15 ürünün fiyat relatiflerinden hesaplanır. Bir SKU'nun eksikliği otomatik olarak başka bir SKU ile doldurulmaz.

Bu nedenle günlük `136/150` gibi bir toplam kapsama değeri tek başına veri kalitesi sorunu anlamına gelmez. Daha önemli sinyaller şunlardır:

- kategori bazında kapsamanın eşik altına düşmesi,
- bir önceki güne göre yeni kaybolan ürün sayısının yükselmesi,
- sabit SKU/depot eşleşmelerinin değişmesi.

README'deki **Son 24 saatte** bölümü bu günlük kayıp/geri dönüş hareketlerini ayrıca raporlar.

## Birim fiyat ve ikame

Mevcut v0.2 sürümünde farklı SKU'lar arasında otomatik birim-fiyat ikamesi yapılmaz. Aynı SKU'nun zaman içindeki fiyat relatifi izlendiği için paket boyutu sabit kaldığı sürece endeks karşılaştırması doğrudan yapılabilir.

İleride güvenilir gramaj/adet/litre normalizasyonu eklendiğinde, aynı dar ürün sınıfı içinde birim fiyat temelli daha geniş bir elementary-index yaklaşımı uygulanabilir. Böyle bir değişiklik metodoloji ve sepet versiyonu güncellemesi gerektirir.

## Eksik gözlem

Eksik fiyatlara şu aşamada model tabanlı imputasyon yapılmaz. Kategori ve ana endeks, yayımlanan kapsama değerleriyle birlikte yalnızca mevcut karşılaştırılabilir gözlemlerden hesaplanır.

## Sınırlamalar

Bu çalışma genel tüketici fiyat endeksi değildir. Kira, konut, ulaşım, sağlık, eğitim ve hizmetleri kapsamaz. Şehir ve mağaza örneklemesi ileriki sürümlerde genişletilecektir.

Sepet veya ağırlık metodolojisi anlamlı biçimde değiştiğinde yeni bir sepet versiyonu ve yeni baz dönemi başlatılır.
