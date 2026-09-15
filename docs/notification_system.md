# Alarm ve Bildirim Sistemi

## 1. Amaç

Bu bileşen, pano izleme modülünün Modbus üzerinden sunduğu alarm ve risk bilgilerini merkezi sistemde takip eder. Yüksek risk, kritik durum veya ark algılanması hâlinde ilgili operasyon ekibine bildirim oluşturur.

Bildirim mekanizması, koruma sisteminin yerine geçmez. Özellikle ark gibi zaman açısından kritik olaylarda yerel koruma ve kesici açtırma işlemleri SMS veya merkezi haberleşme sonucunu beklemeden gerçekleştirilmelidir.

## 2. Sistem Mimarisi

```text
Sensörler ve mevcut ölçüm cihazları
                ↓
           Risk motoru
                ↓
       Modbus register haritası
                ↓
         Gediz Elektrik SCADA
                ↓
       Merkezi alarm yöneticisi
                ↓
    SMS gateway veya GSM modem
```

Hackathon prototipinde mevcut SCADA sistemi yerine Modbus test istemcisi kullanılmaktadır. Bildirim gönderimi ise `ConsoleNotificationSender` ile terminal üzerinde simüle edilmektedir.

## 3. Kullanılan Modbus Alanları

Alarm servisi aşağıdaki normalize edilmiş register alanlarını kullanır:

| Register | Offset | Veri |
|---:|---:|---|
| 40011 | 10 | Aşırı yük risk skoru |
| 40012 | 11 | Bağlantı risk skoru |
| 40013 | 12 | İzolasyon risk skoru |
| 40014 | 13 | Ark durumu |
| 40015 | 14 | Genel durum |

Risk skorları `0–100` arasında açıklanabilir puanlardır. Kalibre edilmiş bir olasılık modeli bulunmadığı sürece bu değerler arıza olasılığı olarak yorumlanmamalıdır.

## 4. Genel Durum Kodları

| Kod | Durum | Bildirim davranışı |
|---:|---|---|
| 0 | Normal | Acil bildirim gönderilmez |
| 1 | Uyarı | SCADA üzerinde izlenir, acil bildirim gönderilmez |
| 2 | Yüksek risk | Operasyon ekibine bildirim gönderilir |
| 3 | Kritik | Operasyon ekibine kritik bildirim gönderilir |

`general_status` değeri risk motoru tarafından hesaplanır. Bildirim servisi risk motorunun yerine geçmez; üretilen durumu merkezi bildirim politikasına göre işler.

## 5. Ark Alarmı

`arc_status` register değeri:

| Değer | Anlamı |
|---:|---|
| 0 | Ark algılanmadı |
| 1 | Ark algılandı |

`arc_status = 1` olduğunda diğer risk skorlarından ve genel durumdan bağımsız olarak kritik bildirim oluşturulur.

Ark alarmında SMS yalnızca operasyon ekibini bilgilendiren ikincil kanaldır. Yerel koruma sistemi, merkezi sistem veya SMS bağlantısına bağımlı olmamalıdır.

## 6. Baskın Riskin Belirlenmesi

Genel durum yüksek risk veya kritik seviyedeyse alarm yöneticisi aşağıdaki skorları karşılaştırır:

- Aşırı yük riski
- Bağlantı riski
- İzolasyon riski

En yüksek skor, mesajda baskın risk olarak gösterilir.

Örnek:

```text
[HIGH RISK] PANEL-001:
Dominant risk is Connection (85/100).
Overload=20/100,
Connection=85/100,
Insulation=15/100.
```

Bu yöntem operasyon ekibinin yalnızca genel alarm seviyesini değil, alarmın muhtemel nedenini de görmesini sağlar.

## 7. Cooldown Mekanizması

SCADA aynı durumu sürekli olarak okuyacağı için her sorguda yeni SMS gönderilmemelidir.

Alarm yöneticisi varsayılan olarak aynı alarm için 300 saniyelik cooldown uygular:

```text
İlk kritik okuma → Bildirim gönderilir
Aynı alarm tekrar gelir → Bildirim bastırılır
Cooldown sona erer → Alarm devam ediyorsa hatırlatma gönderilebilir
```

Alarm türü veya baskın risk değişirse cooldown süresi beklenmeden yeni bildirim oluşturulur.

Cooldown değeri komut satırından değiştirilebilir:

```powershell
python -m src.notifications.notification_service --cooldown 300
```

## 8. Recovery Bildirimi

Aktif yüksek risk veya kritik alarm sonrasında sistem tekrar normal ya da uyarı seviyesine dönerse bir kez recovery bildirimi gönderilir.

Örnek:

```text
[RECOVERY] PANEL-001 returned below the high-risk notification level.
```

Sistem normal durumda kalmaya devam ederse recovery mesajı tekrar gönderilmez.

## 9. Gönderici Katmanı

Bildirim sistemi, gönderim kanalını alarm kararından ayıran ortak bir arayüz kullanır:

```python
sender.send(recipient, message)
```

Bu sayede alarm motoru değiştirilmeden farklı göndericiler kullanılabilir.

### Prototip Gönderici

`ConsoleNotificationSender`, mesajı terminal üzerinde gösterir ve başarılı gönderilmiş gibi işaretler.

Bu gönderici yalnızca hackathon demosunda alarm akışını doğrulamak için kullanılmaktadır. Gerçek SMS gönderdiği iddia edilmemelidir.

### Gerçek Saha Seçenekleri

Gerçek uygulamada `NotificationSender` arayüzüne uygun aşağıdaki adaptörlerden biri eklenebilir:

1. Şirket içi SMS gateway
2. Kurumsal SMPP sunucusu
3. Yerel GSM modem
4. Kurum tarafından onaylanmış özel WhatsApp altyapısı

Public cloud servisleri, kurumun veri güvenliği ve altyapı politikası açıkça onaylanmadan kullanılmamalıdır.

## 10. Alarm Geçmişi

Gönderilen bildirimler yerel olarak aşağıdaki dosyada tutulur:

```text
runtime/alerts.jsonl
```

Her satır bağımsız bir JSON kaydıdır:

```json
{
  "timestamp": "2026-09-15T18:00:00",
  "recipient": "FIELD_TEAM",
  "message": "[HIGH RISK] PANEL-001: Dominant risk is Connection (85/100).",
  "successful": true
}
```

Kayıtlar aşağıdaki amaçlarla kullanılabilir:

- Alarm geçmişini incelemek
- Gönderimin başarılı olup olmadığını izlemek
- Demo sırasında bildirim zincirini kanıtlamak
- Gelecekte merkezi veritabanına aktarım yapmak

`runtime/` klasörü çalışma sırasında üretildiği için Git tarafından takip edilmez.

## 11. Prototipin Çalıştırılması

### Modbus sunucusunu çalıştırma

```powershell
python src/modbus/server.py --snapshot-file examples/snapshots/normal_snapshot.json
```

### Bildirim servisini çalıştırma

```powershell
python -m src.notifications.notification_service
```

Test sırasında daha kısa cooldown kullanılabilir:

```powershell
python -m src.notifications.notification_service --cooldown 30
```

Servis varsayılan olarak:

- `127.0.0.1` adresine,
- `5020` portuna,
- `PANEL-001` modülüne,
- `FIELD_TEAM` alıcısına

göre çalışır.

Bu değerler komut satırından değiştirilebilir:

```powershell
python -m src.notifications.notification_service \
  --host 127.0.0.1 \
  --port 5020 \
  --module-id PANEL-001 \
  --recipient FIELD_TEAM \
  --cooldown 300
```

PowerShell üzerinde komut tek satırda da kullanılabilir.

## 12. Demo Senaryoları

### Normal çalışma

```json
{
  "connection_risk": 8,
  "arc_status": 0,
  "general_status": 0
}
```

Beklenen sonuç: Acil bildirim oluşturulmaz.

### Yüksek bağlantı riski

```json
{
  "connection_risk": 85,
  "arc_status": 0,
  "general_status": 2
}
```

Beklenen sonuç: Bağlantı riskini baskın neden olarak gösteren yüksek risk bildirimi oluşturulur.

### Ark alarmı

```json
{
  "arc_status": 1,
  "general_status": 3
}
```

Beklenen sonuç: Diğer risk skorlarından bağımsız kritik ark bildirimi oluşturulur.

### Normale dönüş

```json
{
  "connection_risk": 8,
  "arc_status": 0,
  "general_status": 0
}
```

Beklenen sonuç: Bir kez recovery bildirimi oluşturulur.

## 13. Mevcut Prototipin Sınırları

Mevcut sürüm:

- Gerçek SMS veya WhatsApp göndermez.
- Tek bir Modbus modülünü takip eder.
- Alarm geçmişini yerel JSONL dosyasında tutar.
- İlk bağlantı kurulamazsa servis kapanır.
- Çalışma sırasında bağlantı hatalarını gösterir ancak gelişmiş yeniden bağlanma politikası henüz içermez.
- Recipient ve gateway bilgilerini merkezi kullanıcı yönetiminden almaz.

Gerçek saha sürümünde aşağıdakiler eklenmelidir:

- Otomatik yeniden bağlantı
- Mesaj kuyruğu ve başarısız gönderim tekrarı
- Birden fazla operasyon ekibi ve vardiya yönetimi
- Alarm onaylama ve kapatma akışı
- Yetkilendirme ve erişim kontrolü
- Merkezi ve yedekli alarm kayıt sistemi
- En az 100 modül için ölçek testi
- Kurumsal SMS gateway veya GSM modem adaptörü

## 14. Güvenlik ve Yapılandırma

Telefon numaraları, gateway parolaları ve erişim anahtarları doğrudan kaynak kod içinde tutulmamalıdır.

Gerçek entegrasyonda bu bilgiler:

- ortam değişkenlerinden,
- kurum içi secrets yönetiminden,
- erişimi sınırlandırılmış yapılandırma dosyalarından

alınmalıdır.

Gizli bilgiler Git deposuna gönderilmemelidir.

## 15. Sonuç

Geliştirilen prototip aşağıdaki uçtan uca akışı göstermektedir:

```text
Modbus alarm register’ları
→ merkezi alarm değerlendirmesi
→ cooldown ve recovery yönetimi
→ değiştirilebilir bildirim göndericisi
→ yerel alarm geçmişi
```

Bu yapı, Gediz Elektrik’in mevcut SCADA sistemi ve kurum içi bildirim altyapısıyla entegre edilebilecek şekilde katmanlara ayrılmıştır.