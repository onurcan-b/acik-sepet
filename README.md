# Açık Sepet

Türkiye'deki zincir market fiyatlarının günlük hareketini **150 ürünlük sabit bir tüketim sepeti** üzerinden izleyen, yeniden üretilebilir deneysel fiyat endeksi.

[![Daily Açık Sepet](https://github.com/onurcan-b/acik-sepet/actions/workflows/daily.yml/badge.svg)](https://github.com/onurcan-b/acik-sepet/actions/workflows/daily.yml)
![Python](https://img.shields.io/badge/Python-3.12+-blue)
![Data](https://img.shields.io/badge/data-daily-informational)

> **Açık Sepet resmî TÜFE değildir.** Kira, konut, ulaştırma, sağlık, eğitim ve hizmetler gibi tüketim kalemlerini kapsamaz. Amaç, zincir marketlerde satılan malların fiyat hareketini yüksek frekansta, şeffaf ve sürümlenebilir bir veri hattıyla izlemektir.

![Açık Sepet günlük endeksi](charts/index.svg)

<!-- STATS_START -->
- **Son değer:** 100.00
- **Son güncelleme:** 2026-08-14
- **Kapsama:** %92 (136 ürün)
- **7 günlük değişim:** —
- **30 günlük değişim:** —
- **Baz tarihi:** 2026-08-13 = 100
<!-- STATS_END -->

## Neden Açık Sepet?

Günlük market fiyatları kamuoyunun en sık gözlemlediği fiyatlardan biri olmasına rağmen, ürün eşleştirmesi ve zaman içindeki değişimleri yeniden üretilebilir biçimde takip etmek kolay değildir.

Açık Sepet bu problemi küçük ama disiplinli bir veri ürünü olarak ele alır:

- aynı ürünleri günler arasında mümkün olduğunca **aynı SKU** üzerinden izler,
- mümkün olduğunda aynı **temsilci mağaza/depot** kaynaklarını korur,
- ham günlük gözlemleri Git içinde sürümler,
- sepet ve kategori ağırlıklarını açık dosyalarda tutar,
- ana endeks ve alt endeksleri otomatik yeniden hesaplar,
- veri kalitesi yeterli değilse gözlemi sessizce başka ürünle değiştirmek yerine eksik bırakır.

Böylece endeksin yalnızca bugünkü değeri değil, **hangi ürünlerden ve hangi kurallarla üretildiği** de incelenebilir.

## Nasıl çalışıyor?

Her günlük çalışmada GitHub Actions:

1. `config/basket.tsv` içindeki 150 ürün tanımını okur.
2. Market Fiyatı servisinde her ürün için adayları arar.
3. İlk başarılı eşleşmede ürün kimliğini `state/product-map.json` içinde sabitler.
4. Mümkün olduğunda temsilci mağaza/depot kaynaklarını da sabit tutar.
5. Geçerli fiyat gözlemlerini `data/snapshots/YYYY-MM-DD.json` dosyasına yazar.
6. Minimum kapsama eşiğini doğrular.
7. Grup ağırlıklı ana **Açık Sepet Market Endeksi**ni üretir.
8. 12 tüketim grubu ile birleşik **Gıda ve alkolsüz içecekler** alt endeksini hesaplar.
9. README grafiğini ve istatistiklerini günceller.
10. Gerçek bir veri değişikliği varsa bot commit'i oluşturup `main` branch'ine gönderir.

```text
Market Fiyatı
    ↓
150 sabit ürün
    ↓
SKU + temsilci depot sabitleme
    ↓
Günlük snapshot
    ↓
Kapsama kontrolü
    ↓
Ana Market Endeksi
    ↓
12 kategori endeksi + Gıda Endeksi
    ↓
Grafik + Git geçmişi
```

## Sepet — v0.2

| Grup | Ürün | Araştırma ağırlığı |
|---|---:|---:|
| Ekmek, tahıllar ve makarna | 18 | %14 |
| Et ve et ürünleri | 15 | %15 |
| Balık ve deniz ürünleri | 8 | %4 |
| Süt ürünleri ve yumurta | 18 | %14 |
| Yağlar | 8 | %6 |
| Meyve | 14 | %8 |
| Sebze | 18 | %11 |
| Şeker, tatlı ve atıştırmalık | 14 | %8 |
| Diğer gıda | 10 | %4 |
| Alkolsüz içecekler | 12 | %5 |
| Ev temizlik sarf malzemeleri | 9 | %7 |
| Kişisel bakım ve kağıt ürünleri | 6 | %4 |
| **Toplam** | **150** | **%100** |

Grup içinde ürünler eşit pay alır; gruplar yukarıdaki araştırma ağırlıklarıyla birleştirilir.

**Bu ağırlıklar TÜİK'in resmî TÜFE ağırlıkları değildir.** Endeksin amacı resmî TÜFE'yi yeniden üretmek değil, market malları için açık ve yüksek frekanslı bir gösterge oluşturmaktır. Ayrıntılı hesaplama kuralları için [`METHOD.md`](METHOD.md) dosyasına bakın.

## Üretilen seriler

### Ana seri

`data/index.csv`

```text
date,index,coverage,items,baseline_date
2026-08-13,100.0,0.92,136,2026-08-13
```

### Alt endeksler

`data/subindices.csv`, 12 tüketim grubuna ek olarak birleşik `food_total` serisini içerir.

Örnek grup kimlikleri:

- `bread_cereals`
- `meat`
- `dairy_eggs`
- `fruit`
- `vegetables`
- `household_cleaning`
- `personal_paper`
- `food_total`

## Veri yapısı

```text
acik-sepet/
├── acik_sepet/                 # veri toplama ve endeks kodu
├── config/
│   ├── basket.tsv              # 150 ürünlük sepet
│   └── categories.json         # kategori ağırlıkları
├── data/
│   ├── snapshots/
│   │   └── YYYY-MM-DD.json     # günlük ham gözlem
│   ├── index.csv               # ana market endeksi
│   └── subindices.csv          # kategori + gıda endeksleri
├── state/
│   └── product-map.json        # sabit SKU/depot eşleştirmeleri
├── charts/
│   └── index.svg               # README grafiği
├── tests/
├── METHOD.md
└── .github/workflows/
```

### Günlük snapshot

Her ürün gözlemi, seçilen ürün başlığını, hesaplanan medyan fiyatı ve kullanılan kaynak tekliflerini saklar. Eşleşmeyen ürünler `errors` alanında açıkça raporlanır; başka bir ürüne sessiz fallback yapılmaz.

## Otomasyon

Ana workflow:

```text
.github/workflows/daily.yml
```

Zamanlama:

```text
05:45 UTC — her gün
```

Bu saat:

- Türkiye'de **08:45**,
- Berlin'de yaz saatinde **07:45 CEST**,
- Berlin'de kış saatinde **06:45 CET**

anlamına gelir. GitHub Actions zamanlanmış işleri yoğunluk durumuna göre birkaç dakika gecikmeli başlatabilir.

Ana workflow başarılı olduktan sonra `.github/workflows/subindices.yml` alt endeksleri günceller.

Her iki akış da GitHub arayüzünden manuel olarak tetiklenebilir:

**Actions → ilgili workflow → Run workflow**

## Yerelde çalıştırma

Python 3.12+ önerilir.

```bash
git clone https://github.com/onurcan-b/acik-sepet.git
cd acik-sepet
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Testler:

```bash
pytest -q
```

Günlük fiyat toplama:

```bash
python -m acik_sepet.collect
python -m acik_sepet.validate --min-coverage 0.60
python -m acik_sepet.index
python -m acik_sepet.subindices
python -m acik_sepet.report
```

## Metodoloji ilkeleri

Açık Sepet'in temel tasarım tercihi **karşılaştırılabilirliği ürün sayısından önce tutmaktır**.

- Ürün kimliği ilk güvenilir eşleşmeden sonra sabitlenir.
- Temsilci kaynak kaybolursa mümkün olduğunca seri başka bir mağazaya sessizce taşınmaz.
- Ürün bulunamazsa gözlem eksik kalabilir.
- Ana seri yalnızca yeterli ağırlıklı kapsama olduğunda yayımlanır.
- Mevcut sürümde model tabanlı fiyat imputasyonu yapılmaz.
- Sepet veya ağırlık metodolojisi anlamlı biçimde değişirse yeni sepet versiyonu ve yeni baz dönemi açılmalıdır.

Detaylar: [`METHOD.md`](METHOD.md).

## Sınırlamalar

Açık Sepet şu anda:

- yalnızca markette satılan mal kategorilerine odaklanır,
- resmî TÜFE kapsamını temsil etmez,
- şehir ve mağaza örneklemesini tam nüfus ağırlıklı bir tasarımla modellemez,
- promosyon, stok durumu ve ürün ambalaj değişikliklerinden etkilenebilir,
- veri kaynağındaki ürün katalog değişikliklerine bağımlıdır,
- henüz mevsimsellik veya kalite değişimi düzeltmesi uygulamaz.

Bu nedenle seri **araştırma ve yüksek frekanslı izleme göstergesi** olarak değerlendirilmelidir.

## Veri kaynağı

MVP, [`marketfiyati.org.tr`](https://marketfiyati.org.tr/) arayüzünün kullandığı veri servisine düşük hacimli sorgular gönderir.

Repo, kaynağın toplu aynasını oluşturmaz. Yalnızca endeks için seçilen ürünlere ilişkin gerekli günlük gözlemleri saklar. Kaynak verinin kullanım ve yeniden dağıtım koşulları için [`NOTICE.md`](NOTICE.md) dosyasına bakın.

## Katkı

Kod, ürün eşleştirme mantığı, testler ve metodoloji geliştirmeleri pull request ile yapılabilir.

Otomatik üretilen `data/` ve `state/` dosyalarının elle değiştirilmesi yerine problemi üreten toplama/eşleştirme katmanının düzeltilmesi tercih edilir.

Katkı rehberi: [`CONTRIBUTING.md`](CONTRIBUTING.md)

## Lisans ve veri hakları

Bu depo özgün proje kodu ile üçüncü taraf kaynaklardan elde edilen fiyat gözlemlerini ayrı değerlendirir.

- Özgün Python kodu, otomasyon ve proje yapılandırması MIT lisansı altındadır: [`LICENSE-CODE`](LICENSE-CODE).
- Kaynak fiyat verileri üzerinde proje ayrıca bir telif veya yeniden lisanslama iddiasında bulunmaz.
- Veri kaynağı ve kullanım notları: [`LICENSE`](LICENSE) ve [`NOTICE.md`](NOTICE.md).

## Proje sahibi

**Onurcan Büyükkalkan**  
[buyukkalkan.net](https://buyukkalkan.net/)

---

Açık Sepet bağımsız ve deneysel bir projedir; herhangi bir kamu kurumunun resmî istatistik yayını değildir.
