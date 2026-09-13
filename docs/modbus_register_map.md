# Modbus Register Map

Bu doküman, pano izleme modülünün SCADA sistemine sunacağı Modbus register alanlarını tanımlar.

## Holding Registers

| Görünen adres | Kod adresi (offset) | Veri | Ölçek | Örnek ham değer | Gerçek değer | Açıklama |
|---|---:|---|---:|---:|---:|---|
| 40001 | 0 | L1 akımı | ×10 | 3180 | 318.0 A | L1 faz akımı |
| 40002 | 1 | Kabin içi sıcaklık | ×10 | 291 | 29.1 °C | Pano iç ortam sıcaklığı |
| 40003 | 2 | Yüzey sıcaklığı | ×10 | 503 | 50.3 °C | İzlenen bağlantı veya kablo yüzeyi |
| 40004 | 3 | Bağıl nem | ×10 | 509 | %50.9 | Pano içi bağıl nem |
| 40005 | 4 | Aşırı yük risk skoru | Yok | 35 | 35/100 | Açıklanabilir risk skoru |
| 40006 | 5 | Bağlantı risk skoru | Yok | 62 | 62/100 | Gevşek/yüksek dirençli bağlantı riski |
| 40007 | 6 | İzolasyon risk skoru | Yok | 20 | 20/100 | İzolasyon/PD riski |
| 40008 | 7 | Ark durumu | Yok | 0 veya 1 | 0 veya 1 | 0: Ark yok, 1: Ark algılandı |
| 40009 | 8 | Genel durum | Yok | 0–3 | 0–3 | Sistemin genel alarm seviyesi |

## Genel Durum Kodları

| Kod | Durum |
|---:|---|
| 0 | Normal |
| 1 | Uyarı |
| 2 | Yüksek risk |
| 3 | Kritik |

## Notlar

- Sıcaklık, akım ve nem ondalıklı oldukları için 10 ile çarpılarak tam sayı şeklinde aktarılır.
- Örneğin `29.1 °C`, Modbus register içerisinde `291` olarak tutulur.
- Risk skorları olasılık değildir; kurallar ve ileride kullanılabilecek modeller tarafından üretilen 0–100 arası açıklanabilir puanlardır.
- Ark algılandığında risk skorundan bağımsız olarak genel durum kritik seviyeye çıkarılır.
- Bu harita ilk prototip sürümüdür ve veri gereksinimlerine göre genişletilecektir.