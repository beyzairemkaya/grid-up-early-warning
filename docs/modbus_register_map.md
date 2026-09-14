# Modbus Register Map

Bu doküman, pano izleme modülünün RTU/SCADA sistemine sunduğu normalize edilmiş Modbus register alanlarını tanımlar.

Bu harita MPR-53CS veya TVOC-2 cihazlarının üretici register haritası değildir. Kontrol ünitemizin farklı kaynaklardan topladığı ölçümleri ve hesapladığı riskleri SCADA'ya sunmak için tanımlanmıştır.

## Prototip Bağlantı Bilgileri

| Alan | Değer |
|---|---|
| Protokol | Modbus TCP |
| Sunucu adresi | 127.0.0.1 |
| Port | 5020 |
| Device ID | 1 |
| Okuma fonksiyonu | Function Code 03 – Read Holding Registers |
| Register sayısı | 15 |

## Holding Registers

| Görünen adres | Kod offseti | Veri | Tür | Ölçek | Örnek ham değer | Gerçek değer |
|---:|---:|---|---|---:|---:|---:|
| 40001 | 0 | L1 akımı | UInt16 | ×10 | 3180 | 318.0 A |
| 40002 | 1 | L2 akımı | UInt16 | ×10 | 3150 | 315.0 A |
| 40003 | 2 | L3 akımı | UInt16 | ×10 | 3220 | 322.0 A |
| 40004 | 3 | Kabin sıcaklığı | Int16 | ×10 | 291 | 29.1 °C |
| 40005 | 4 | L1 yüzey sıcaklığı | Int16 | ×10 | 503 | 50.3 °C |
| 40006 | 5 | L2 yüzey sıcaklığı | Int16 | ×10 | 497 | 49.7 °C |
| 40007 | 6 | L3 yüzey sıcaklığı | Int16 | ×10 | 510 | 51.0 °C |
| 40008 | 7 | Bağıl nem | UInt16 | ×10 | 509 | %50.9 |
| 40009 | 8 | Normalize PD göstergesi | UInt16 | ×10 | 52 | 5.2/100 |
| 40010 | 9 | PD darbe sayısı | UInt16 | ×1 | 3 | 3 |
| 40011 | 10 | Aşırı yük risk skoru | UInt16 | ×1 | 10 | 10/100 |
| 40012 | 11 | Bağlantı risk skoru | UInt16 | ×1 | 8 | 8/100 |
| 40013 | 12 | İzolasyon risk skoru | UInt16 | ×1 | 5 | 5/100 |
| 40014 | 13 | Ark durumu | UInt16 | ×1 | 0 | Ark yok |
| 40015 | 14 | Genel durum | UInt16 | ×1 | 0 | Normal |

## Genel Durum Kodları

| Kod | Durum |
|---:|---|
| 0 | Normal |
| 1 | Uyarı |
| 2 | Yüksek risk |
| 3 | Kritik |

## Ark Durumu Kodları

| Kod | Durum |
|---:|---|
| 0 | Ark algılanmadı |
| 1 | Ark algılandı |

Ark algılandığında diğer risk skorlarından bağımsız olarak genel durum kritik seviyeye çıkarılmalıdır.

## Veri Türleri

### UInt16

Negatif olmayan tam sayıları temsil eder.

Kullanıldığı alanlar:

- Akım
- Nem
- PD göstergeleri
- Risk skorları
- Durum kodları

### Int16

Negatif değer alabilecek sıcaklıkları temsil eder.

Negatif sıcaklıklar Modbus register içerisinde 16-bit two's complement biçiminde tutulur.

Örnek:

- Gerçek sıcaklık: `-10.0 °C`
- Ölçeklenmiş değer: `-100`
- Modbus ham register değeri: `65436`
- SCADA tarafından çözülen değer: `-10.0 °C`

## Ölçeklendirme

Ondalıklı değerler register içerisinde tam sayı olarak taşınabilmesi için 10 ile çarpılır.

Örnek:

- `318.0 A` → `3180`
- `29.1 °C` → `291`
- `%50.9` → `509`
- `5.2 PD index` → `52`

SCADA bu değerleri okuduktan sonra 10'a bölerek gerçek ölçüme dönüştürmelidir.

## Risk Skorlarının Anlamı

Risk skorları arıza olasılığı değildir.

Örneğin:

`connection_risk = 76`

ifadesi, gevşek bağlantı bulunma ihtimalinin kesin olarak `%76` olduğu anlamına gelmez. Bu değer, açıklanabilir kurallar ve ileride kullanılabilecek modeller sonucunda üretilmiş `0–100` arası bir risk puanıdır.

## Adresleme Notu

Dokümanlarda görünen `40001` adresi, yazılımda çoğunlukla `0` offsetiyle okunur.

Örnek:

| SCADA gösterimi | Python offseti |
|---:|---:|
| 40001 | 0 |
| 40002 | 1 |
| 40015 | 14 |

Bu nedenle client aşağıdaki şekilde okuma yapar:

```python
client.read_holding_registers(
    address=0,
    count=15,
    device_id=1,
)