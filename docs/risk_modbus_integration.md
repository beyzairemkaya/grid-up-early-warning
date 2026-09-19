# Risk motoru -> Modbus TCP prototipi

`run_risk_snapshot.py` sentetik CSV satırlarını **tek bir** `AnomaliMotoru`
örneğinden geçirir. `risk_snapshot_adapter.py` motorun alarmlarını üç ayrı
0–100 göstergeye ve mevcut 15 holding register snapshot'ına dönüştürür.
Mevcut Modbus register adresleri ve SCADA client değiştirilmez.

## Kurulum ve çalıştırma (proje kökünde)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python sentetik_veri.py
python run_risk_snapshot.py --csv sentetik_veri_problem_bazli.csv --snapshot-file runtime/risk_snapshot.json --pd-pulse-count 3 --cabinet-temperature-c 29.1
```

Son üç komutu ayrı terminallerde, önce snapshot dosyası oluştuktan sonra çalıştırın:

```powershell
python src/modbus/server.py --snapshot-file runtime/risk_snapshot.json
python src/modbus/scada_client.py
python -m src.notifications.notification_service
```

`--pd-pulse-count` ve `--cabinet-temperature-c`, CSV'de bu sütunlar yoksa
**simüle edilen sabit örnekler** sağlar. CSV'ye `pd_pulse_count` ve
`cabinet_temperature_c` sütunları eklenirse her satır için gerçek senaryo
değerleri kullanılır. Eksik değerler otomatik olarak sıfırla doldurulmaz.

## Prototip puan politikası

| Skor | Motorun alarmı | Puan |
| --- | --- | ---: |
| Aşırı yük | Faz dengesizliği / aşırı yük / ikisi | 40 / 75 / 90 |
| Bağlantı | Lokal termal sapma / ek olarak sıcaklık uyarısı | 70 / 85 |
| İzolasyon | Yüksek nem / PD trendi / PD uyarısı / PD kritik | 20 / 40 / 65 / 90 |

Bir grupta birden fazla bulgu varsa en yüksek kural uygulanır. Skorlar
**kalibre edilmiş arıza olasılıkları değildir**. Motorun `saglik_skoru` ve
alarm tespiti aynen korunur. Durum kodu: motor kritik veya ark ise 3,
en yüksek skor en az 70 ise 2, diğer alarm varsa 1, yoksa 0.

CSV'deki `pd_charge_pC` mevcut 40009 normalize PD göstergesiyle aynı fiziksel
büyüklük değildir. Demo için PD index = `min(100, max(0, pC / PD_KRITIK_PC * 100))`
olarak hesaplanır; gerçek HFCT donanımı için ölçüm ve kalibrasyon gerekir.
`I_NOMINAL_A` motorda `None` olduğu için aşırı yük tespiti geçmiş örneklerle
teyit edilir; açılışta anında aşırı yük skoru beklenmemelidir.

Ark algılandıktan sonra motorda yazılımsal kilit vardır ve CSV tekrar oynatımı
durur. Bu yazılım kesici açtırmaz; sahada donanımsal koruma ayrı çalışmalıdır.

Doğrulama: `python -m unittest tests.test_risk_integration`
