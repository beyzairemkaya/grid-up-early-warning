# Grid Up — Akıllı Dağıtım Panosu Erken Uyarı Platformu

1600 kVA alçak gerilim dağıtım panoları için geliştirilen erken uyarı **yazılım prototipi**. Sentetik ölçümler bir risk motorunda değerlendirilir; aşırı yük, bağlantı ve izolasyon için ayrı 0–100 risk puanları üretilir. Sonuçlar normalize edilmiş Modbus TCP holding register'ları üzerinden test istemcisine sunulur ve yüksek risk/ark olayları konsolda bildirime dönüştürülür.

> **Prototip kapsamı:** Çalışan zincir sentetik CSV → risk motoru → JSON snapshot → Modbus TCP sunucusu → SCADA test istemcisi / konsol alarm servisidir. Gerçek pano kurulumu, üretici cihazlarından Modbus RTU veri toplama, kurumun SCADA'sına bağlantı ve SMS gönderimi henüz doğrulanmış değildir.

## Mimari

| Bileşen | Bu repodaki görevi |
| --- | --- |
| Risk motoru | Telemetriyi ve aynı okumadaki bulguları değerlendirir. |
| Snapshot adaptörü | Bulguları üç risk puanına, ark bayrağına ve genel duruma dönüştürür. |
| Modbus TCP sunucusu | 15 normalize holding register'ı sunar. |
| SCADA test istemcisi | Register'ları okuyup ölçüm ve riskleri terminalde gösterir. |
| Bildirim servisi | Yüksek risk ve kritik durumları değerlendirir; cooldown, recovery ve yerel JSONL kaydı uygular. |

Ark için gerçek koruma yolu yerel donanımla sağlanmalıdır. Bu yazılım kesici açtırmaz; SCADA bağlantısı ve konsol bildirimi ark korumasının yerine geçmez.

## Kurulum

Proje kökünde, PowerShell ile:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

VS Code'da açılan **her yeni terminalde** sanal ortamı yeniden etkinleştirin veya doğru Python yorumlayıcısının seçildiğinden emin olun. `No module named 'pymodbus'` hatası alınırsa etkin ortamda `python -m pip install -r requirements.txt` komutunu tekrar çalıştırın.

## Kısa demoyu çalıştırma

Komutları **proje kökünden dört ayrı terminalde** çalıştırın. İlk komut `runtime/risk_snapshot.json` dosyasını oluşturduktan sonra diğerlerini başlatın.

**Terminal 1 — sentetik senaryo ve risk motoru**

```powershell
python -m src.risk_engine.run_risk_snapshot --csv examples/risk_demo.csv --snapshot-file runtime/risk_snapshot.json --interval 15
```

**Terminal 2 — Modbus TCP sunucusu**

```powershell
python src/modbus/server.py --snapshot-file runtime/risk_snapshot.json
```

**Terminal 3 — SCADA okumasını temsil eden test istemcisi**

```powershell
python src/modbus/scada_client.py
```

**Terminal 4 — alarm ve bildirim servisi**

```powershell
python -m src.notifications.notification_service
```

Sunucu prototipte `127.0.0.1:5020` adresinde, Device ID `1` ile çalışır. Demo CSV'nin ilk üç satırı normaldir; sonrasında bağlantı riski, normale dönüş, kritik PD ve ark senaryoları gösterilir. `--interval 15` ile her satır 15 saniye kalır. Ark sonrası risk motorundaki yazılımsal kilit oynatımı durdurabilir. Demo yeniden başlatılacaksa önce çalışan süreçleri durdurup komutları aynı sırayla başlatın.

## Modbus veri sözleşmesi

Holding register'lar **FC03**, başlangıç offset'i `0`, sayı `15` ile okunur. Bunlar ENTES veya ABB cihazlarının üretici register adresleri değildir; prototipin SCADA'ya sunduğu çıktı haritasıdır.

| Görünen adres | Offset | Veri | Ölçek |
| ---: | ---: | --- | ---: |
| 40001–40003 | 0–2 | L1/L2/L3 akımları | ×10 |
| 40004–40007 | 3–6 | Pano içi ve faz yüzey sıcaklıkları (signed) | ×10 |
| 40008 | 7 | Bağıl nem | ×10 |
| 40009 | 8 | Normalize PD göstergesi | ×10 |
| 40010 | 9 | PD darbe sayısı | ×1 |
| 40011–40013 | 10–12 | Aşırı yük, bağlantı, izolasyon risk puanları | ×1 |
| 40014 | 13 | Ark durumu: 0 yok, 1 var | ×1 |
| 40015 | 14 | Genel durum: 0 normal, 1 uyarı, 2 yüksek risk, 3 kritik | ×1 |

Risk puanları kalibre edilmiş arıza olasılıkları değildir. Demo CSV'sindeki `pd_charge_pC` değeri gerçek bir HFCT ölçüm zinciriyle kalibre edilmemiştir; 40009'daki PD göstergesi prototipte normalize edilir.

## Bildirim davranışı

- Durum `0`: acil bildirim yok; `1`: SCADA üzerinde uyarı.
- Durum `2`: **High Risk**; `3`: **Critical** bildirimi.
- `arc_status = 1`: diğer puanlardan bağımsız kritik bildirim.
- Tekrarlanan alarmlarda varsayılan cooldown uygulanır; alarm normale dönünce bir recovery bildirimi üretilebilir.
- `ConsoleNotificationSender` yalnızca terminale yazar; **gerçek SMS/WhatsApp göndermez**. Alarm geçmişi yerel `runtime/alerts.jsonl` dosyasında tutulur.

## Doğrulama

```powershell
python -m unittest tests.test_risk_integration
```

Saha cihazı, port, baud, Slave ID ve Modbus RTU **giriş adresleri** önerilen tasarımın parçalarıdır; üretici kılavuzları ve fiziksel testlerle doğrulanmadan gerçek entegrasyonda kullanılmamalıdır. Saha sürümünde yeniden bağlantı, kalıcı alarm kuyruğu, yetkilendirme, kurumsal bildirim adaptörü ve çoklu pano yük testi ayrıca gerekir.
