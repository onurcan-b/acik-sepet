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

Örneğin bir ürün yanlış eşleşiyorsa `data/snapshots/...` dosyasını elle değiştirmek yerine `config/basket.tsv` veya eşleştirme mantığı düzeltilmelidir.

## Pull request öncesi

```bash
pytest -q
```

çalıştırın ve metodoloji davranışını değiştiren bir katkıda `METHOD.md` ile README'nin güncel olduğundan emin olun.

## Metodoloji değişiklikleri

Sepet, kategori ağırlıkları, baz dönemi veya endeks formülünü değiştiren PR'lar açıkça belirtilmelidir. Zaman serisinin geçmişle karşılaştırılabilirliğini bozan değişikliklerde yeni bir sepet sürümü veya yeni baz dönemi tercih edilmelidir.

## Veri kaynağı

Kaynak servisin kullanım koşullarına ve makul istek hacmine saygı gösterin. Projenin amacı üçüncü taraf servisin toplu aynasını çıkarmak değildir.
