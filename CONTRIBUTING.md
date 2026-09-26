# Katkı Rehberi

Açık Sepet'e katkılar memnuniyetle karşılanır. Projenin temel önceliği günlük fiyat serilerinin karşılaştırılabilir ve yeniden üretilebilir kalmasıdır.

## Geliştirme ortamı

```bash
git clone https://github.com/onurcan-b/acik-sepet.git
cd acik-sepet
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

## Katkı alanları

Özellikle şu katkılar değerlidir:

- ürün eşleştirme kalitesinin iyileştirilmesi,
- eşleşmeyen veya kırılgan ürün tanımlarının düzeltilmesi,
- fiyat ve kapsama validasyonlarının güçlendirilmesi,
- test kapsamının artırılması,
- metodoloji ve dokümantasyon geliştirmeleri,
- yeni alt endeks veya raporlama çıktıları,
- veri kaynağı kullanım koşullarının daha net belgelenmesi.

## Veri dosyaları

`data/` ve `state/` altındaki dosyalar otomasyon tarafından üretilir. Bu dosyalarda görülen bir problemi doğrudan çıktıyı elle düzenleyerek çözmek yerine, mümkünse problemi üreten kod veya yapılandırmayı düzeltin.

Örneğin bir ürün yanlış eşleşiyorsa `data/v0.4/snapshots/...` dosyasını elle değiştirmek yerine `config/product_types.tsv`, `config/api_categories.json` veya eşleştirme mantığı düzeltilmelidir.

## Pull request öncesi

```bash
pytest -q
```

çalıştırın ve metodoloji davranışını değiştiren bir katkıda `METHOD.md` ile README'nin güncel olduğundan emin olun.

## Metodoloji değişiklikleri

Sepet, kategori ağırlıkları, baz dönemi veya endeks formülünü değiştiren PR'lar açıkça belirtilmelidir. Zaman serisinin geçmişle karşılaştırılabilirliğini bozan değişikliklerde yeni bir sepet sürümü veya yeni baz dönemi tercih edilmelidir.

## Veri kaynağı

Kaynak servisin kullanım koşullarına ve makul istek hacmine saygı gösterin. Projenin amacı üçüncü taraf servisin toplu aynasını çıkarmak değildir.

## Günlük yayın ve yerel doğrulama

```bash
# Kaynağa istek göndermeden, mevcut verilerle bütün yayını üret ve test et:
python -m acik_sepet.publish --offline

# Zamanlanmış görevin kullandığı tarama ve doğrulama işlemi:
python -m acik_sepet.publish

# Yerel Windows ortamında pytest önbelleği sorunlarını önlemek için:
python -m pytest -q -p no:cacheprovider
```

Yayın, geçici bir dizinde hazırlanır: toplama, fiyat doğrulama, güncellik, endeks,
kalite raporu, altı grafik, geçmiş kilidi ve testler geçmeden ana dosyalara kurulmaz.
Kurulum yarıda kesilirse işlem günlüğü önceki dosyaları geri yükler. Hatalı taramanın
durumu ve başarılı sorgulardan alınan keşif kanıtı saklanabilir; hatalı fiyatlar,
endeks veya gölge panel state'i yayımlanmaz. Aynı çalışma dizininde eşzamanlı iki
yayın işlemine izin verilmez. `.publication-transaction/` dosyalarını bir başarısızlık
sonrasında elle silmeyin; sonraki çalıştırma otomatik geri yükleme yapar.

GitHub Actions mevcut üç günlük çalışma saatini ve `main` yayınını korur. Raporlar
her başarılı çalışmada yenilenir; son başarılı gözlem tarihi ile son tarama girişimi
ayrı gösterilir. Kurallar değişirken son yayımlanmış günün tamamını korumak için,
mevcut geçmiş doğrulamasını geçtikten sonra
`python -m acik_sepet.history --freeze-through-latest` kullanılabilir.
Bu komut bazı yeniden başlatmaz.

## Gölge panel değerlendirmesi

```bash
python -m acik_sepet.recovery status
# Yalnızca yedi tam ve doğrulanmış gölge günü incelendikten sonra:
python -m acik_sepet.recovery --activate-from YYYY-MM-DD
```

Etkinleştirme tarihi son doğrulanmış gölge gününden sonra olmalıdır. Yeni aday ve
depot kuralları önce aynı API yanıtlarıyla paralel hesaplanır; ikinci bir tam katalog
taraması yapılmaz. Ana ve gölge kapsam, ortak panel bağlantısı, devir sayıları ve fiyat
değişimleri birlikte incelenmelidir. Günün tam yayın doğrulaması tamamlanmadan gölge
gün sayacı ilerlemez. `finalize-day` bakım komutu doğrudan işletilmemelidir; bunu yayın
işlemi başarılı doğrulamadan sonra çağırır. Geçmişe etkinleştirme ve yeterli kanıt
olmadan panel değişimi reddedilir.

Geri alma gerektiğinde `config/rollout.json` içindeki mod `shadow` yapılabilir;
yayımlanmış gözlemler silinmez, baz değiştirilmez ve eski panel state'i geri
kopyalanmaz. Son kabul edilen fiyat seviyesi üzerinden çalışmaya devam edilir.

## Dosya haritası

| Dosya/dizin | İçerik |
|---|---|
| `config/product_types.tsv`, `api_categories.json` | Ürün tanımları ve kategori eşleşmeleri |
| `config/categories.json`, `series.json`, `history-lock.json` | Sabit ağırlıklar, baz ve geçmiş koruması |
| `config/discovery.json`, `rollout.json` | İncelenmiş arama alternatifleri ve gölge/aktif politika |
| `data/v0.4/snapshots/`, `revisions/` | Günlük gözlemler ve aynı günün önceki sürümleri |
| `data/v0.4/*indices.csv`, `index.csv` | Yayımlanan endeksler; mevcut CSV alanları korunur |
| `data/v0.4/quality.json`, `collection-diagnostics/` | Sürüm numaralı kalite ve sorgu teşhisleri |
| `data/v0.4/shadow/`, `attempts/` | Gölge gözlemler ve tarihli çalışma sonuçları |
| `state/v0.4-panels.json` | Yayımlanan ürün/depot bağlantı state'i |
| `state/v0.4-discovery.json`, `v0.4-shadow-panels.json` | Ayrı aday kanıtı ve gölge paneli |
| `charts/` | README'nin günlük yenilenen altı SVG grafiği |

`product_key` gerçek ürünü, `slot_id` zaman içinde devam eden karşılaştırma
kimliğini belirtir. Ürün veya depoyu değiştirmek geçmiş fiyat hareketlerini silme
yetkisi vermez. Korunan metin dosyaları `.gitattributes` ile LF olarak saklanır;
doğrulama eski Windows CRLF checkout'larını normalize eder, içerik değişikliğine
izin vermez.
