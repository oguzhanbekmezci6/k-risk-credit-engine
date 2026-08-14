# K-RISK V14 — Faiz ve Kredi Politikası Referansları

**Referans tarihi:** 11 Ağustos 2026

Bu sürümde Akbank'ın kamuya açık bireysel kredi örnekleri müşteri faiz girdisi için; TCMB verileri ise piyasa/benchmark ve stres referansı için kullanılır. Kamuya açık TCMB mevduat faizi **gerçek banka FTP'si değildir** ve bu nedenle pilot profilde tek başına otomatik kredi REDDET gerekçesi oluşturmaz.

## Akbank kamuya açık faiz örnekleri

| Ürün | Uygulamadaki varsayılan | Kaynak notu |
|---|---:|---|
| İhtiyaç | aylık %3,84 | Hayat sigortalı örnek oran; müşteriye özel oran değişebilir. |
| Konut | aylık %3,15 | Akbank konut kredisi hesaplama örneği. |
| Taşıt 12 ay | aylık %3,75 | Hayat sigortası + kasko şartlı örnek. |
| Taşıt 24 ay | aylık %3,70 | Aynı. |
| Taşıt 36 ay | aylık %3,65 | Aynı. |
| Taşıt 48 ay | aylık %3,60 | Aynı. |

Kaynaklar:
- https://www.akbank.com/basvuru/hizli-ihtiyac-kredisi/
- https://www.akbank.com/basvuru/konut-kredisi/
- https://www.akbank.com/krediler/tasit-kredileri/0-km-tasit-kredisi
- https://www.akbank.com/krediler/tasit-kredileri/ikinci-el-tasit-kredisi
- https://www.akbank.com/krediler/ihtiyac-kredileri/ihtiyac-ve-tuketici-kredisi

## Akbank taşıt kuralları

Standart bireysel taşıt kredisi için araç değerine göre kullanılan kamu tablosu:

- 0–400.000 TL: azami %70, azami 48 ay
- 400.001–800.000 TL: azami %50, azami 36 ay
- 800.001–1.200.000 TL: azami %30, azami 24 ay
- 1.200.001–2.000.000 TL: azami %20, azami 12 ay
- 2.000.000 TL üzeri: standart tabloda kredi yok

İkinci el bireysel taşıtta ayrıca araç yaşı en fazla 10 yıl; araç yaşı + kredi vadesi en fazla 144 ay olarak kontrol edilir.

## Akbank konut kuralları

- Azami vade: 120 ay
- Başvuran yaşı + kredi vadesi toplamı 70 yılı aşmamalıdır.
- Kamu ürün sayfasında belirtilen azami kredi tutarı: 20 milyon TL (yasal sınırlar dahilinde)
- Kredi/değer oranı BDDK'nın güncel konut tablosuna göre ayrıca kontrol edilir.

## BDDK mevzuat kontrolleri

- **11152 / 13.02.2025:** ihtiyaç/tüketici kredisi genel vade sınırı: 125.000 TL ve altı 36 ay; 125.000–250.000 TL 24 ay; 250.000 TL üzeri 12 ay.
- **11364 / 29.01.2026:** konut değer ve enerji sınıfına göre güncel azami kredi/değer oranları.
- **10656 / 24.08.2023:** başvuran/eş/18 yaş altı çocukta başka nitelikli konut varsa baz LTV oranı %75 azaltılır; karardaki istisnalar ayrıca teyit edilmelidir.

Kaynaklar:
- https://www.bddk.gov.tr/Mevzuat/DokumanGetir/1270
- https://www.bddk.gov.tr/Mevzuat/DokumanGetir/1327
- https://www.bddk.gov.tr/Mevzuat/EkGetir/1210?ekId=277

## TCMB piyasa referansları

31 Temmuz 2026 haftalık akım, ağırlıklı ortalama yıllık kredi faizleri bu build'de benchmark olarak tutulur:

- İhtiyaç: %56,91
- Konut: %38,82
- Taşıt: %38,83
- TL ticari: %52,48

23 Temmuz 2026 PPK kararı:

- 1 hafta repo politika faizi: %37
- Gecelik borç verme: %40
- Gecelik borçlanma: %35,5

17 Temmuz 2026 haftası TL mevduat akım faizi %46,7'dir. K-RISK bunu yalnız **tarihli kamu fonlama vekili** olarak gösterir; bankanın iç Hazine/FTP eğrisi yerine bağlayıcı fiyatlama girdisi olarak kullanmaz.

Kaynaklar:
- https://www.tcmb.gov.tr/wps/wcm/connect/TR/TCMB+TR/Main+Menu/Istatistikler/Faiz+Istatistikleri/Haftalik/Kredi+Faiz+Oranlari/
- https://evds3.tcmb.gov.tr/charts/portlet/Njk4YjI3MDFkNmMwM2YxNDg2MjQ1MDU0/tr
- https://www.tcmb.gov.tr/wps/wcm/connect/TR/TCMB+TR/Main+Menu/Duyurular/Basin/2026/DUY2026-32

## Tasarım kararı

Akbank oranları müşteri teklifinin garantisi değildir; skor, tutar, vade, sigorta ve diğer koşullara göre değişebilir. UI'daki oran alanı **aylık nominal oran** olarak gösterilir, backend mevcut sözleşmeyle uyumluluk için bunu yıllık nominal (`aylık × 12`) biçimine dönüştürür.

TCMB sektör ortalamaları müşteri fiyatı değildir. Gerçek banka FTP/Hazine eğrisi sisteme bağlanana ve ekonomik parametreler kurum tarafından onaylanana kadar RAROC ve fiyat tabanı sonuçları **UYARI/danışma amaçlıdır**; PD, EL, mevzuat, LTV, vade ve ödeme gücü kontrolleri ise bağlayıcı kalır.
