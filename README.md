# Açık Sepet

Markette fiyatlar gerçekten ne kadar oynuyor? “Bana öyle geliyor” kısmını bilgisayara bırakan, günlük ve açık bir market fiyat endeksi.

[![Daily Açık Sepet](https://github.com/onurcan-b/acik-sepet/actions/workflows/daily.yml/badge.svg)](https://github.com/onurcan-b/acik-sepet/actions/workflows/daily.yml)
[![Validate Açık Sepet](https://github.com/onurcan-b/acik-sepet/actions/workflows/validate.yml/badge.svg)](https://github.com/onurcan-b/acik-sepet/actions/workflows/validate.yml)
![Python](https://img.shields.io/badge/Python-3.12+-blue)
![Method](https://img.shields.io/badge/matching-deterministic-0f766e)

> Bu resmî TÜFE değil. Kira, ulaşım, sağlık, eğitim ve hizmetler yok. Burada yalnızca market rafındaki malların fiyat hareketini olabildiğince temiz ve denetlenebilir biçimde ölçüyoruz.

<!-- STATUS_START -->
> **Veri durumu: Eksik kapsam.** Son seri noktası: **2026-09-23**. Kategori ağırlığı kapsaması: **%74**.
> Son tarama girişimi: 2026-09-23T02:44:24.718731+03:00.
> Yayımlanamayan kategoriler: Et ve et ürünleri; Sebze.
> Kaynak tarihi seri günüyle aynı olan SKU: **0/1475**. Yatay çizgi, raf fiyatlarının bugün yeniden teyit edildiğini göstermez.
> Baz korunuyor: **2026-09-05 = 100**. 5–14 Eylül geçmişi kilitli; sınıflandırma düzeltmeleri 15 Eylül'den itibaren geçerli.
<!-- STATUS_END -->

![Açık Sepet v0.4 günlük endeksi](charts/index.svg)

<!-- STATS_START -->
| Endeks | Tarih | Aktif tip | Aktif tiplerde SKU | Kategori ağırlığı kapsaması | 7 gün | 30 gün | Baz |
|---:|---|---:|---:|---:|---:|---:|---|
| **101.03** | 2026-09-23 | 101 | 1398 | %74 | +1.08% | — | 2026-09-05 = 100 |
<!-- STATS_END -->

## Kısaca ne yapıyor?

130 ürün tipi tanımlı: ekmek, kıyma, muz, domates, şampuan, çöp torbası… Her tip için birden fazla gerçek ürün ve market/depot fiyatı izleniyor. Paketler kg, litre veya adede çevriliyor; fiyat relatifleri önce ürün tipine, sonra 12 ana kategoriye, en son Açık Sepet endeksine çıkıyor.

```mermaid
flowchart TD
    A[Market Fiyatı verisi] --> B[API kategori filtresi]
    B --> C[Başlık ve birim kontrolü]
    C --> D[Sabit SKU ve depot paneli]
    D --> E[Ürün tipi endeksi]
    E --> F[Kategori ve Açık Sepet]
```

Modelin hoşumuza gitmeyen ürünü dışarı atmasını ummuyoruz: eşleştirme tamamen deterministik. Aynı veri ve aynı kurallar, aynı sonucu verir. LLM yok.

## v0.4 neden yeniden 100’den başladı?

v0.3’te başlık eşleştirmesi fazla cömertti. “Muz” ararken muzlu gofret, “çilek” ararken reçel, “salatalık” ararken turşu panele girebiliyordu. Paket fiyatı ve matematik doğru olsa bile ölçülen ürün yanlışsa sonuç da yanlış olur.

v0.4 bu yüzden eski seriyi makyajlamıyor. ilk olarak 2 Eylül’de temiz bir baseline açtı; 5 Eylül sıfırlamasıyla **2026-09-05 = 100** üzerinden devam ediyor; v0.3 verileri `data/v0.3/` altında olduğu gibi kalıyor.

Yeni eşleştirme sırası:

1. Market Fiyatı’nın `menu_category`, `main_category` veya `sub_category` filtresi uygulanır.
2. Başlıktaki bütün zorunlu kelime kuralları geçmek zorundadır. Yarım eşleşme yok.
3. Hariç kelimeler sert veto verir.
4. Miktarda önce API’nin `refinedVolumeOrWeight` alanı, gerekirse başlık parser’ı kullanılır.
5. Hesaplanan birim fiyat, API’nin `unitPriceValue` alanıyla ayrıca karşılaştırılır.
6. Yeterli gerçek SKU yoksa ürün tipi yayımlanmaz. Boşluğu yanlış ürünle doldurmak yasak.

Kategori eşlemeleri açıkça [`config/api_categories.json`](config/api_categories.json), başlık ve eşik kuralları [`config/product_types.tsv`](config/product_types.tsv) içinde.

## Sepetin içi

![Kategori başına sıkı eşleşmiş SKU](charts/basket.svg)

<!-- CATEGORY_TABLE_START -->
| Kategori | Endeks | Yeterli tip | Kapsama | SKU |
|---|---:|---:|---:|---:|
| Ekmek, tahıllar ve makarna | 101.81 | 10/12 | %83 | 143 |
| Et ve et ürünleri | — | 6/10 | %60 | 86 |
| Balık ve deniz ürünleri | 109.18 | 4/6 | %67 | 31 |
| Süt ürünleri ve yumurta | 99.42 | 12/13 | %92 | 200 |
| Yağlar | 100.43 | 4/5 | %80 | 77 |
| Meyve | 101.61 | 8/13 | %62 | 31 |
| Sebze | — | 9/17 | %53 | 44 |
| Şeker, tatlı ve atıştırmalık | 101.37 | 12/12 | %100 | 211 |
| Diğer gıda | 99.72 | 9/10 | %90 | 174 |
| Alkolsüz içecekler | 102.69 | 8/11 | %73 | 158 |
| Ev temizlik sarf malzemeleri | 102.45 | 9/10 | %90 | 127 |
| Kişisel bakım ve kağıt ürünleri | 99.32 | 10/11 | %91 | 193 |
<!-- CATEGORY_TABLE_END -->

## Kapsama dürüstlüğü

v0.3 kategori kapsamasını yalnızca baseline’da hayatta kalan ürün tipleri üzerinden hesaplıyordu. Bu, örneğin altı balık tipinden ikisi kalmışken kategoriyi `%100` gösterebiliyordu. v0.4’te payda, konfigürasyondaki bütün ürün tipleri. Eksik olan gerçekten eksik görünüyor.

![Kategori ürün tipi kapsaması](charts/coverage.svg)

<!-- GAPS_START -->
**29 ürün tipi** yeterli gözlem veya ortak panel bağlantısı olmadığı için yayımlanamadı. Tarama hataları ve kaynak güncelliği ayrıca raporlanır.

| Ürün tipi | Gözlenen | Minimum | API kategori filtresi |
|---|---:|---:|---|
| Meyve suyu | 0 | 8 | Meyve Suyu |
| Tavuk göğüs | 0 | 5 | Tavuk Göğüs |
| Toz çamaşır deterjanı | 2 | 7 | Toz Deterjanlar |
| Beyaz ekmek | 1 | 5 | Somun Ekmek |
| Hindi eti | 0 | 4 | Hindi Eti |
| Konserve sebze | 2 | 5 | Mısır Konservesi |
| Balık parmak | 0 | 2 | Balık Kroket |
| Brokoli | 0 | 2 | Karnabahar ve Brokoli |
| Cherry domates | 0 | 2 | Domates |
| Ispanak | 0 | 2 | Yeşillikler |
| Karnabahar | 0 | 2 | Karnabahar ve Brokoli |
| Kivi | 0 | 2 | Kivi |
| Marul | 0 | 2 | Yeşillikler |
| Mısırözü yağı | 0 | 2 | Mısırözü Yağı |
| Çilek | 0 | 2 | Çilek |
| Havuç | 1 | 2 | Kök Sebzeler |
| Konserve sardalya | 1 | 2 | Deniz Ürünleri |
| Mandalina | 1 | 2 | Narenciye |

Tabloda en zayıf 18 tip var; toplam eksik tip sayısı 29.
<!-- GAPS_END -->

## Bugün ne oynadı?

<!-- MOVERS_START -->
2026-09-22 → 2026-09-23: **1 yukarı**, **0 aşağı**, **100 değişim gözlenmedi**. Karşılaştırılan tip: 101. Kaynak güncelliği aşağıda ayrıca gösterilir.

| Ürün tipi | SKU | Değişim |
|---|---:|---:|
| Bütün piliç | 8 | +2.71% |
| Elma | 5 | +0.00% |
| Avokado | 2 | +0.00% |
| Ayran | 22 | +0.00% |
| Muz | 2 | +0.00% |
| Kuru fasulye | 21 | +0.00% |
| Dana kuşbaşı / sote | 7 | +0.00% |
| Bisküvi | 21 | +0.00% |
| Siyah çay | 21 | +0.00% |
| Çamaşır suyu | 14 | +0.00% |
<!-- MOVERS_END -->

## Veri kalitesi

<!-- QUALITY_START -->
- **Güncellik uyarısı:** Gözlemlerin çoğunda kaynak güncelleme tarihi bugünden eski veya bilinmiyor.
- **0/1475** SKU için en yeni kaynak tarihi gözlem günüyle aynı; ayrıntı: [health.json](data/v0.4/health.json)
- **1475** sıkı eşleşmiş SKU, **7** market etiketi
- **1342/1475** miktar doğrudan API'nin normalize alanından
- **1475/1475** satırda birim fiyat API değeriyle ayrıca kontrol edildi
- **1475/1475** gözlem sabit depot relatifleriyle bağlı
- **1200/1475** SKU yalnızca bir depot üzerinden izleniyor; market etiketleri ulusal temsiliyet sağlamaz
- **1475/1475** SKU için depot fiyatları, kaynak tarihleri ve bağlantı girdileri saklanıyor (15 Eylül'den itibaren)
- **203** bridge edilmiş panel yenilemesi (yeni baseline'da doğal olarak sıfır)
<!-- QUALITY_END -->

Her günlük çalışmada şunlar da kontrol ediliyor:

- aynı SKU veya panel slotu iki ürün tipine yazılmış mı,
- paket fiyatı / miktar = birim fiyat mı,
- API birim fiyatıyla fark `%5` sınırını aşıyor mu,
- ürün başlığı hâlâ zorunlu kuralları geçiyor mu,
- API kategori etiketi beklenen eşlemeyle aynı mı,
- ürün tipi ve toplam SKU kapsaması yayın eşiğini koruyor mu.

## Endeksin kısa matematiği

**15 Eylül kalite düzeltmesi:** Baz yine **5 Eylül 2026 = 100**. 5–14 Eylül gözlemleri ve yayımlanan tip/kategori/ana endekslerin tamamı kilitlidir; eski grafik yeniden hesaplanıp değiştirilmez. Eski sınıflandırma kusurları geçmişte kalır ve bu dönem yeni kurallarla toplanmış gibi sunulmaz.

- API hatası devam eden tarama yayımlanmaz; son başarılı snapshot ve panel state korunur. Aynı gün ciddi tip kapsaması kaybında yalnızca ilgili tipin önceki ölçümü ve gerçek tarama zamanı korunur; diğer tipler güncellenir. Minimumu bozmayan tek SKU kaybı tüm yayını durdurmaz. Hata durumu grafiğin üzerinde görünür ve günlük workflow başarısız biter.
- Beyaz ekmekte kepekli/çok tahıllı/aromalı ekmekler; genel süt panelinde laktozsuz ve aromalı sütler dışarıda bırakılır. Dana kuşbaşı, bütün piliç ve normal domates tanımları da daraltılır. Yanlış eşleşen slotlar üç günlük aday teyidinden sonra kontrollü ikameye alınabilir; ilk ikame fiyat farkı hareket üretmez.
- Her yeni SKU gözleminde kullanılan depot fiyatları, kaynak tarihleri ve zincir hesabının önceki fiyat/seviye girdileri saklanır ve bağlı fiyat bunlardan yeniden doğrulanır.
- Kategori ağırlığı kapsaması, ürün kapsamıyla aynı ölçü değildir. Eksik kategoriler ve tek depot üzerinden izlenen ürünlerin payı açıkça raporlanır.

**5 Eylül düzeltmesi:** İlk 25 sonuç sınırı 200'e çıktı. “Ekmeği”, “unu”, “jeli” gibi Türkçe çekimler artık gerçek ürünü elemek için sebep değil. Eksilen SKU/depotların geçmiş fiyat farkını endeksten silen kompozisyon hatası da düzeltildi.

Her adım iki ölçümde ortak kalan kimlikleri karşılaştırır:

```text
SKU fiyatı(t) = önceki bağlı fiyat × geo_mean(ortak depot fiyat değişimleri)
Tip endeksi(t) = önceki endeks × geo_mean(ortak slot birim fiyat değişimleri)
Kategori / ana endeks(t) = önceki endeks × ağırlıklı_mean(ortak üyelerin endeks değişimleri)
```

Bir ürünün veya kategorinin kaybolması, önceki zamlarını geri almaz. Yeni gelen ürün ilk bağlantıda fiyat değişimi üretmez. Yeterli ortak gözlem yoksa o nokta yayımlanmaz; eksik fiyatı tahmin edip gerçek gözlem diye yazmıyoruz. Bunun bedeli: ürünün kayıp olduğu aralıktaki hareketi kaçırabiliriz.

**5 Eylül = 100:** Grafik 5 Eylül’de yeniden başlatıldı; daha eski gözlemler saklanıyor. Ham günlük gözlemler silinmedi. Önceki hesaplar [`revisions/pre-2026-09-05-method/`](data/v0.4/revisions/pre-2026-09-05-method/) altında. Eski snapshot'lar depot bazında tüm fiyatları saklamadığından geçmiş depot kompozisyon hatası tam olarak yeniden hesaplanamaz; depot düzeltmesi yeni ölçümlerle devreye giriyor.

Kaynak güncellenmemişse rapor bunu açıkça gösterir. “7 gün” ve “30 gün” gerçekten takvim günüdür; ilgili günün ölçümü yoksa oran da yoktur. Aynı gün yeniden taramada önceki snapshot arşivlenir; baseline üzerine yazılmaz.

Ayrıntı: [`METHOD.md`](METHOD.md).

## Dosyalar

```text
config/
├── api_categories.json   # Market Fiyatı kategori eşlemeleri
├── product_types.tsv     # başlık, birim ve SKU eşikleri
└── categories.json       # araştırma ağırlıkları

data/v0.4/
├── snapshots/YYYY-MM-DD.csv
├── type_indices.csv
├── category_indices.csv
├── index.csv
└── latest-errors.json

state/v0.4-panels.json    # sabit SKU/depot paneli
charts/                   # README grafikleri
```

`product_key` gerçek ürünü, `slot_id` ise zaman içinde devam eden endeks kimliğini anlatır. Ham fiyat kaynağını topluca aynalamıyoruz; yalnızca panel hesabı için gereken günlük gözlemleri saklıyoruz.

## Çalıştırmak istersen

Python 3.12+ ile:

```bash
git clone https://github.com/onurcan-b/acik-sepet.git
cd acik-sepet
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
python -m acik_sepet.collect
python -m acik_sepet.validate
python -m acik_sepet.health
python -m acik_sepet.index
python -m acik_sepet.report
```

Windows PowerShell aktivasyonu:

```powershell
.\.venv\Scripts\Activate.ps1
```

Kod değişiklikleri de test ve tarama akışını başlatır. GitHub Actions **8 saatte bir**, `05:17 / 13:17 / 21:17 UTC` için planlı (**Türkiye: 08:17 / 16:17 / 00:17**). Kaynak fiyatlar değişmediyse yeni bir fiyat hareketi üretilmez. Günlük grafikte her günün son başarılı taraması kullanılır; baz günü sabit tutulur. GitHub yoğun olduğunda cron’un geç başlaması mümkün; veri tarihi Türkiye saatine göre yazılıyor.

## Sınırlar

- Ağırlıklar TÜİK tüketim ağırlıkları değil; araştırma ağırlıkları.
- Mağaza/şehir örneklemi nüfusa göre tasarlanmış ulusal bir örneklem değil.
- Kampanyalar gözlenen tüketici fiyatı sayılıyor.
- Mevsimsellik, kalite değişimi ve hedonik düzeltme yok.
- Kaynak katalogdaki hatalar bize de yansıyabilir; bu yüzden kategori, başlık ve birim fiyatı ayrı ayrı kontrol ediyoruz.

Kısacası: yüksek frekanslı bir market göstergesi. Daha fazlası gibi davranmıyor.

## Kredi ve kaynak

Fiyat ve kategori verisi [Market Fiyatı](https://marketfiyati.org.tr/) arayüzünün kullandığı servisten geliyor. Market Fiyatı, [uygulamanın kendi açıklamasına göre](https://marketfiyati.org.tr/uygulama-hakkinda) **TÜBİTAK BİLGEM** tarafından geliştirildi; ilgili kamu kurumları ve fiyat verisini sağlayan zincir marketler olmasa bu çalışma da olmazdı. Kaynak verinin sahibi olduğumuzu veya onu yeniden lisansladığımızı iddia etmiyoruz.

Proje, kod ve metodoloji: **Onurcan Büyükkalkan** — [buyukkalkan.net](https://buyukkalkan.net/)

Daha net hukuk/veri notu: [`NOTICE.md`](NOTICE.md). Kod MIT lisanslı: [`LICENSE-CODE`](LICENSE-CODE).

Katkı için [`CONTRIBUTING.md`](CONTRIBUTING.md) açık. Özellikle yanlış kategori, eksik ürün tipi ve parser vakaları makbule geçer.
