# Metodoloji — v0.4, 5 Eylül 2026 düzeltmesi

Açık Sepet, zincir marketlerde satılan malların günlük fiyat hareketini izleyen deneysel bir çoklu-SKU panel endeksidir. v0.4, ürün sınıflandırmasını sıkılaştırdığı için **2026-09-02 = 100** ile yeni seri başlatır. v0.3 geçmişi değiştirilmez.

## 1. Ürün tipi ve sınıflandırma

Temel ekonomik gözlem birimi ürün tipidir: pirinç, yoğurt, domates, şampuan gibi. Her ürün tipi birden fazla gerçek SKU ile temsil edilir.

Kurallar iki açık dosyada tutulur:

- `config/product_types.tsv`: sorgu, beklenen birim, hedef/minimum SKU, zorunlu ve hariç başlık kuralları,
- `config/api_categories.json`: Market Fiyatı kategori ağacındaki `menu_category`, `main_category` veya `sub_category` filtresi.

Bir adayın kabul edilmesi için sırasıyla:

1. API isteğinin tanımlı kategori filtresiyle yapılması,
2. dönen kategori etiketi veya server-side filtre isteğinin kaydedilmiş provenance alanının eşleşmesi,
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

İlk gözlemde kararlı depot kimlikleri sabitlenir. Yeni depotlar otomatik alınmaz. Son kabul edilen ölçümle ortak depotların fiyat oranları geometrik ortalanır ve önceki bağlı paket fiyatına uygulanır. Bir depoyu düşürmek geçmişteki katkısını geri almaz. Ortak depot yoksa SKU o gün eksiktir. Geri gelen depot ancak karşılaştırılabilir iki ölçümle harekete katılır; kayıp aralıktaki fiyat hareketi yakalanmayabilir.

Eski panel state'i yalnızca anchor fiyatları tutuyordu. İlk geçiş ölçümünde eski anchor formülü kullanılır; sonraki ölçümler `source_last_prices` ve `source_last_level` üzerinden zincirlenir. Eski snapshot'lar tek tek depot fiyatlarını içermediğinden geriye dönük depot düzeltmesi iddia edilmez.

## 5. Ürün tipi endeksi

```text
I(k,t) = I(k,previous) × geometric_mean(P(i,t) / P(i,previous))
```

`previous`, tipin son yayımlanabilir ölçümüdür. Yalnızca iki ölçümde ortak slotlar kullanılır. En az `min_skus` ortak slot ve önceki panelin en az %50'si gerekir. Eşik geçilmezse endeks boş kalır; eski seviye güncel veri olarak sunulmaz. İlk yeterli örneklem o tip için 100'dür; başlangıçta yetersiz tip sonsuza dek dışarıda kalmaz.

## 6. Kategori ve ana endeks

Kategori ve ana endeksler de son yayımlanabilir ölçümle ortak üyelerin **değişim oranlarını** ağırlıklı aritmetik ortalar ve önceki seviyeye uygular. Farklı bir üye setinin bazdan beri seviyelerini yeniden ortalamaz. Yeni üye ilk girdiği gün seviye sıçraması yaratmaz. Yeterli ortak üye kalmazsa bağlantı yayımlanmaz.

Kategori içi ağırlıklar varsayılan olarak eşittir; ana kategori ağırlıkları `config/categories.json` içindedir. Hem güncel kapsam hem iki ölçümün ortak kapsamı, konfigüre edilmiş toplam ağırlığın en az %60'ı olmalıdır. Rapordaki kapsama alanı güncel kullanılabilir üyeleri gösterir; zincir bağının da yeterli olması ayrıca gerekir.

Bunlar TÜİK tüketim ağırlıkları değildir. Değişen örneklemde zincir endeksin sapma ve zincir sürüklenmesi riski vardır; kayıp fiyat hareketleri tahmin edilmez.

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


## 10. Güncellik, yeniden çalıştırma ve denetim

`health.json` her snapshot için kaynak tarihi dağılımını, kayıp/yeni/ortak slotları ve %20 üzeri birim fiyat hareketlerini kaydeder. Büyük hareketler inceleme sinyalidir; otomatik olarak yanlış kabul edilip silinmez. Kaynak tarihi her SKU'nun kullanılan depotları arasındaki **en yeni** tarihtir; her deponun güncel olduğunu kanıtlamaz. SKU'ların en az %60'ında bu tarih gözlem gününden en fazla 3 gün eski olmalıdır; gelecek tarih de yayın hatasıdır. Bugün güncellenmiş SKU payı %50 altındaysa rapor uyarı verir.

7/30 günlük değişim tam takvim tarihindeki ölçümü gerektirir. Aynı gün normal tekrar mevcut snapshot'ı korur; `--refresh` eski snapshot'ı `data/v0.4/revisions/` altında arşivleyip yeniden tarar. İlk baseline günü değiştirilemez. Aynı gün tekrarları aday/eksik gün sayaçlarını ilerletmez. Başlangıçta minimuma ulaşamamış paneller üç ardışık günde görülen adaylarla tamamlanabilir.

Arama en fazla 8 × 25 sonucu tarar; bu bütün katalogun eksiksiz tarandığı anlamına gelmez. Ürün başlığı kuralları ve birim doğrulaması bütün sayfalarda korunur. Sorgu ve kategori taksonomisi kaynak tarafında değişebilir.
