# Risk motoru → Modbus TCP prototipi

`src/risk_engine/run_risk_snapshot.py`, sentetik CSV satırlarını tek bir `AnomaliMotoru` örneğinden geçirir. `src/risk_engine/risk_snapshot_adapter.py` ise motorun alarmlarını üç ayrı 0–100 risk skoruna ve mevcut 15 holding register alanını içeren snapshot’a dönüştürür.

Mevcut Modbus register adresleri, SCADA test istemcisi ve bildirim servisi değiştirilmez.

## Kurulum

Komutları proje kökünde çalıştırın:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Kısa demoyu çalıştırma

**Terminal 1 — risk motoru ve snapshot üretimi:**

```powershell
.\.venv\Scripts\python.exe -m src.risk_engine.run_risk_snapshot --csv examples/risk_demo.csv --snapshot-file runtime/risk_snapshot.json --interval 15
```

İlk `row=1` çıktısı göründüğünde, proje kökünde üç ayrı terminal daha açın.

**Terminal 2 — Modbus TCP sunucusu:**

```powershell
.\.venv\Scripts\python.exe src/modbus/server.py --snapshot-file runtime/risk_snapshot.json
```

**Terminal 3 — SCADA test istemcisi:**

```powershell
.\.venv\Scripts\python.exe src/modbus/scada_client.py
```

**Terminal 4 — bildirim servisi:**

```powershell
.\.venv\Scripts\python.exe -m src.notifications.notification_service
```

Demo CSV’si önce normal ölçümler, ardından bağlantı riski, normale dönüş, kritik PD ve ark senaryoları içerir. Her satır 15 saniye gösterilir. Ark senaryosundan sonra motor yazılımsal olarak kilitlenir ve CSV oynatımı durur.

Bildirimler prototipte konsola yazılır ve `runtime/alerts.jsonl` dosyasına kaydedilir; gerçek SMS gönderilmez.

## Uzun sentetik veriyi oynatma

Önce CSV’yi üretin:

```powershell
.\.venv\Scripts\python.exe sentetik_veri.py
```

Ardından risk motorunu çalıştırın:

```powershell
.\.venv\Scripts\python.exe -m src.risk_engine.run_risk_snapshot --csv sentetik_veri_problem_bazli.csv --snapshot-file runtime/risk_snapshot.json --pd-pulse-count 3 --cabinet-temperature-c 29.1
```

Uzun sentetik CSV’de `pd_pulse_count` ve `cabinet_temperature_c` sütunları bulunmadığından komuttaki `3` ve `29.1` değerleri **simüle edilmiş sabit örneklerdir**. Bu sütunlar CSV’de varsa her satırdaki değer kullanılır. Eksik değerler sessizce sıfırla doldurulmaz.

## Prototip puan politikası

| Skor | Motorun bulgusu | Puan |
| --- | --- | ---: |
| Aşırı yük | Faz dengesizliği / aşırı yük / ikisi birlikte | 40 / 75 / 90 |
| Bağlantı | Lokal termal sapma / ek olarak sıcaklık uyarısı / kritik düzeyde tek faz sıcaklığı | 70 / 85 / 95 |
| İzolasyon | Yüksek nem / PD trend artışı / PD uyarısı / kritik PD | 20 / 40 / 65 / 90 |

Aynı risk grubunda birden fazla bulgu varsa ilgili en yüksek puan kullanılır. Bu skorlar **kalibre edilmiş arıza olasılıkları değildir**; prototipin açıklanabilir risk göstergeleridir. Motorun kendi `saglik_skoru` alanı ve alarm tespit kuralları korunur.

Genel durum kodu şu şekilde üretilir:

- `0`: Normal
- `1`: Uyarı
- `2`: En yüksek risk skoru en az 70
- `3`: Motorun kritik veya ark durumu

Ark, üç risk skorundan bağımsız olarak ayrıca `arc_status=1` üretir.

## Veri eşleştirme notları

CSV’deki `pd_charge_pC` ile Modbus haritasındaki normalize `pd_index` aynı fiziksel büyüklük değildir. Demo için gösterge, PD yükünün motorun kritik PD eşiğine oranlanmasıyla 0–100 aralığında hesaplanır. Gerçek sensör verisi için ayrı ölçüm eşleştirmesi ve kalibrasyon gerekir.

Motorda `I_NOMINAL_A=None` olduğu için aşırı yük tespiti geçmiş örneklerden yararlanır; uygulama açılır açılmaz aşırı yük skoru oluşması beklenmez.

Yazılım kesici açtırma işlemi gerçekleştirmez. Saha koruması ayrı bir donanımsal yol gerektirir.

## Doğrulama

Proje kökünde çalıştırın:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_risk_integration
```

Bu doğrulama ve demo, **simüle edilmiş verilerle yazılım akışını** gösterir; gerçek pano, sensör veya kurum SCADA sistemiyle yapılmış saha testi değildir.