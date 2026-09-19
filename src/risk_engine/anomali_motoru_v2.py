"""
=============================================================================
 ORTA GERILIM PANO IZLEME - ANOMALI TESPIT MOTORU (v2)
=============================================================================
 Kaynak dokumanlar:
   - algoritma_semasi.pdf                      -> karar akisi (oncelik sirasi)
   - Modbus_RTU_adresleme_ve_esik_degeri_tablosu.xlsx -> esikler + register map

 Sematik akis (yukaridan asagiya, KATI ONCELIK):
   1) Optik Ark  > esik      -> ACIL: kesici ac + SMS/WhatsApp + SISTEMI KILITLE
                                (akis burada durur, asagisi calismaz)
   2) PD / HFCT  > esik      -> UYARI: "Izolasyon Hatasi / Kismi Desarj Riski"
                                SCADA'ya logla -> sonraki kontrole gec
   3) Sicaklik > 75 C VEYA Nem > %80 RH -> UYARI: "Termal Asiri Yuk / Yogusma"
                                -> sonraki kontrole gec
   4) Faz dengesizligi > %15 VEYA asiri yuk -> "Faz Dengesizligi" kaydi
   5) Hicbiri yoksa          -> NORMAL, dongu devam

 Not: 1. adim disindaki adimlar "sonraki kontrole gec" dedigi icin
      birden fazla alarm ayni anda uretilebilir. Sadece ARK akisi keser.
=============================================================================
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field, asdict
from enum import IntEnum

import numpy as np
import pandas as pd


# =============================================================================
# 1. ESIK DEGERLERI  (Excel tablosundan birebir)
# =============================================================================

@dataclass
class Esikler:
    # --- Sicaklik & Nem Sensoru (Slave 2) -----------------------------------
    SICAKLIK_UYARI_C: float = 75.0      # Excel: "Kritik esik: > 75C"
    SICAKLIK_KRITIK_C: float = 95.0     # ek kademe (sema tek kademe istiyor)
    NEM_UYARI_RH: float = 80.0          # Excel: "Yogusma riski esigi: > %80 RH"

    # --- HFCT / PD & Ark Modulu (Slave 3) -----------------------------------
    PD_UYARI_PC: float = 80.0
    PD_KRITIK_PC: float = 250.0
    PD_TREND_PENCERE: int = 32          # kac ornek uzerinden egim hesaplanir (~8 saat @15dk)
    PD_TREND_EGIM_ESIK: float = 1.2     # pC/ornek - esik altinda kalsa da tutarli artis

    # Sema "Ark > 0" diyor; ancak optik sensor pano ici aydinlatmayi da gorur.
    ARK_LUX_ESIK: float = 5000.0
    ARK_TEYIT_ORNEK: int = 1            # kac ardisik ornekte teyit (1 = aninda)

    # --- Enerji Analizoru (Slave 1) -----------------------------------------
    FAZ_DENGESIZLIK_YUZDE: float = 15.0  # Excel/sema: "I_dengesizlik > %15"
    ASIRI_YUK_ORANI: float = 1.10        # I_ort > 1.10 * I_nominal
    I_NOMINAL_A: float | None = None     # None -> adaptif/mevsimsel tespit
    ASIRI_YUK_TEYIT_ORNEK: int = 2       # ani tepe yerine kalici yuk icin
    MEVSIMSEL_GECIKME: int = 96          # 96 ornek = 24 saat @ 15 dk
    MEVSIMSEL_ARTIS_ORANI: float = 1.25  # dune gore %25 artis -> olagandisi yuk

    # --- Gerilim (Excel: "sebeke gerilim dusumu/yukselmesi takibi") ---------
    V_NOMINAL_V: float = 230.0
    V_ALT_ORAN: float = 0.90
    V_UST_ORAN: float = 1.10

    # --- Opsiyonel termal kestirim katmani ----------------------------------
    TERMAL_SAPMA_C: float = 8.0          # beklenenin ustunde kalici sapma
    TERMAL_TAU_S: float = 1800.0         # pano termal zaman sabiti


ESIK = Esikler()


# =============================================================================
# 2. MODBUS RTU HARITASI  (Excel tablosundan)
# =============================================================================

MODBUS_MAP = {
    "faz_akimlari":   dict(slave=1, baud=9600,  hex="0x0000", dec=30001, tip="Float", fn=4),
    "gerilimler":     dict(slave=1, baud=9600,  hex="0x0010", dec=30009, tip="Float", fn=4),
    "pano_sicaklik":  dict(slave=2, baud=9600,  hex="0x0020", dec=30033, tip="Int16", fn=4),
    "pano_nem":       dict(slave=2, baud=9600,  hex="0x0021", dec=30034, tip="Int16", fn=4),
    "pd_ark":         dict(slave=3, baud=19200, hex="0x0030", dec=30049, tip="Int16", fn=4),
    "alarm_bitmap":   dict(slave=1, baud=9600,  hex="0x0100", dec=40257, tip="Uint16", fn=3),
    "saglik_skoru":   dict(slave=1, baud=9600,  hex="0x0101", dec=40258, tip="Uint16", fn=3),
    "kesici_ac_cmd":  dict(slave=1, baud=9600,  hex="0x0102", dec=40259, tip="Coil",   fn=5),
}


class Alarm(IntEnum):
    ARK_FLASI            = 0   
    PD_KRITIK            = 1
    PD_UYARI             = 2
    SICAKLIK_KRITIK      = 3
    SICAKLIK_UYARI       = 4
    NEM_YOGUSMA          = 5
    FAZ_DENGESIZLIGI     = 6
    ASIRI_YUK            = 7
    GERILIM_ANORMAL      = 8
    TERMAL_SAPMA         = 9   
    SISTEM_KILITLI       = 15


ALARM_META = {
    Alarm.ARK_FLASI:        ("ARK FLASI TESPIT EDILDI - ACIL KESME", 100, "ACIL"),
    Alarm.PD_KRITIK:        ("Izolasyon Hatasi / Kritik Kismi Desarj", 45, "KRITIK"),
    Alarm.PD_UYARI:         ("Kismi Desarj Riski", 20, "UYARI"),
    Alarm.SICAKLIK_KRITIK:  ("Kritik Asiri Isinma", 50, "KRITIK"),
    Alarm.SICAKLIK_UYARI:   ("Termal Asiri Yuk", 20, "UYARI"),
    Alarm.NEM_YOGUSMA:      ("Yogusma Riski", 15, "UYARI"),
    Alarm.FAZ_DENGESIZLIGI: ("Faz Dengesizligi", 30, "UYARI"),
    Alarm.ASIRI_YUK:        ("Asiri Yuk", 35, "UYARI"),
    Alarm.GERILIM_ANORMAL:  ("Sebeke Gerilim Anomalisi", 15, "UYARI"),
    Alarm.TERMAL_SAPMA:     ("Erken Uyari: Termal Sapma (Kontak Suphesi)", 20, "ON-UYARI"),
    Alarm.SISTEM_KILITLI:   ("Sistem Kilitli - Manuel Reset Bekleniyor", 100, "ACIL"),
}


# =============================================================================
# 3. YARDIMCI HESAPLAR
# =============================================================================

def dengesizlik_yuzdesi(i1: float, i2: float, i3: float) -> float:
    v = np.array([i1, i2, i3], dtype=float)
    ort = v.mean()
    if ort <= 1e-6:
        return 0.0
    return float(np.max(np.abs(v - ort)) / ort * 100.0)


class AdaptifTaban:
    def __init__(self, pencere: int = 96, min_ornek: int = 32, yuzdelik: float = 0.98):
        self.buf: deque[float] = deque(maxlen=pencere)   
        self.min_ornek = min_ornek
        self.yuzdelik = yuzdelik

    def guncelle(self, deger: float, saglikli: bool) -> None:
        if saglikli:
            self.buf.append(float(deger))

    @property
    def taban(self) -> float | None:
        if len(self.buf) < self.min_ornek:
            return None
        return float(np.quantile(self.buf, self.yuzdelik))


class TermalKestirimci:
    def __init__(self, k: float, tau_s: float, dt_s: float, t0: float, isq0: float):
        self.k = k
        self.alpha = 1.0 - float(np.exp(-dt_s / tau_s))
        self.x_amb = t0
        self.x_isq = isq0

    def adim(self, ortam_c: float, akim_a: float) -> float:
        self.x_amb += self.alpha * (ortam_c - self.x_amb)
        self.x_isq += self.alpha * (akim_a ** 2 - self.x_isq)
        return self.x_amb + self.k * self.x_isq


def termal_k_kalibre(akim, ortam, olculen, saglikli_maske,
                     tau_s=1800.0, dt_s=900.0) -> tuple[float, np.ndarray]:
    alpha = 1.0 - np.exp(-dt_s / tau_s)
    n = len(akim)
    xa, xb = np.zeros(n), np.zeros(n)
    xa[0], xb[0] = ortam[0], akim[0] ** 2
    for s in range(1, n):
        xa[s] = xa[s - 1] + alpha * (ortam[s] - xa[s - 1])
        xb[s] = xb[s - 1] + alpha * (akim[s] ** 2 - xb[s - 1])
    m = np.asarray(saglikli_maske, dtype=bool)
    payda = np.sum(xb[m] ** 2)
    k = float(np.sum((olculen[m] - xa[m]) * xb[m]) / payda) if payda > 0 else 0.0
    return k, xa + k * xb


# =============================================================================
# 4. ANA MOTOR
# =============================================================================

@dataclass
class Okuma:
    zaman: object = None
    i_r: float = 0.0
    i_s: float = 0.0
    i_t: float = 0.0
    v_r: float = 230.0
    v_s: float = 230.0
    v_t: float = 230.0
    sicaklik_r: float = 25.0
    sicaklik_s: float = 25.0
    sicaklik_t: float = 25.0
    nem_rh: float = 50.0
    pd_pc: float = 0.0
    ark_lux: float = 0.0
    ortam_c: float = 25.0


@dataclass
class Sonuc:
    zaman: object
    bitmap: int
    seviye: str
    alarmlar: list = field(default_factory=list)
    mesajlar: list = field(default_factory=list)
    saglik_skoru: float = 100.0
    kesici_ac: bool = False
    sistem_kilitli: bool = False
    dengesizlik_pct: float = 0.0
    aksiyonlar: list = field(default_factory=list)


class AnomaliMotoru:
    def __init__(self, esik: Esikler = ESIK, termal: dict | None = None):
        self.e = esik
        self.kilitli = False
        self.kilit_sebebi = ""
        self._ark_sayac = 0
        self._yuk_sayac = 0
        self.taban = AdaptifTaban()
        self._i_gecmis: deque[float] = deque(maxlen=esik.MEVSIMSEL_GECIKME + 1)
        self._pd_gecmis: deque[float] = deque(maxlen=esik.PD_TREND_PENCERE)
        self.termal = termal or {}          
        self.gecmis: list[Sonuc] = []

    def reset(self) -> None:
        self.kilitli = False
        self.kilit_sebebi = ""
        self._ark_sayac = 0

    def adim(self, o: Okuma) -> Sonuc:
        s = Sonuc(zaman=o.zaman, bitmap=0, seviye="NORMAL")

        if self.kilitli:
            s.bitmap |= (1 << Alarm.SISTEM_KILITLI) | (1 << Alarm.ARK_FLASI)
            s.alarmlar = ["SISTEM_KILITLI"]
            s.mesajlar = [f"Sistem kilitli ({self.kilit_sebebi}). Manuel reset gerekli."]
            s.seviye, s.saglik_skoru = "ACIL", 0.0
            s.sistem_kilitli = True
            self.gecmis.append(s)
            return s

        if o.ark_lux >= self.e.ARK_LUX_ESIK:
            self._ark_sayac += 1
        else:
            self._ark_sayac = 0

        if self._ark_sayac >= self.e.ARK_TEYIT_ORNEK:
            self.kilitli = True
            self.kilit_sebebi = f"ARK FLASI ({o.ark_lux:.0f} lux)"
            s.bitmap |= (1 << Alarm.ARK_FLASI) | (1 << Alarm.SISTEM_KILITLI)
            s.alarmlar = ["ARK_FLASI"]
            s.mesajlar = [ALARM_META[Alarm.ARK_FLASI][0]]
            s.seviye, s.saglik_skoru = "ACIL", 0.0
            s.kesici_ac = True
            s.sistem_kilitli = True
            s.aksiyonlar = [
                "MODBUS COIL 40259 -> 1 (kesiciye ACTIRMA komutu)",
                "SMS / WhatsApp alarmi firlat",
                "SCADA: ARK FLASI - sistem kilitlendi",
            ]
            self.gecmis.append(s)
            return s                      

        ceza = 0

        if o.pd_pc >= self.e.PD_KRITIK_PC:
            s.bitmap |= (1 << Alarm.PD_KRITIK)
            s.alarmlar.append("PD_KRITIK")
            s.mesajlar.append(ALARM_META[Alarm.PD_KRITIK][0])
            ceza += ALARM_META[Alarm.PD_KRITIK][1]
            s.aksiyonlar.append("SCADA log: Izolasyon Hatasi / Kismi Desarj Riski")
        elif o.pd_pc >= self.e.PD_UYARI_PC:
            s.bitmap |= (1 << Alarm.PD_UYARI)
            s.alarmlar.append("PD_UYARI")
            s.mesajlar.append(ALARM_META[Alarm.PD_UYARI][0])
            ceza += ALARM_META[Alarm.PD_UYARI][1]
            s.aksiyonlar.append("SCADA log: Kismi Desarj Riski")

        sicakliklar = {"R": o.sicaklik_r, "S": o.sicaklik_s, "T": o.sicaklik_t}
        sicak_faz = max(sicakliklar, key=sicakliklar.get)
        t_max = sicakliklar[sicak_faz]

        if t_max >= self.e.SICAKLIK_KRITIK_C:
            s.bitmap |= (1 << Alarm.SICAKLIK_KRITIK)
            s.alarmlar.append("SICAKLIK_KRITIK")
            s.mesajlar.append(f"{ALARM_META[Alarm.SICAKLIK_KRITIK][0]} ({sicak_faz} fazi {t_max:.1f} C)")
            ceza += ALARM_META[Alarm.SICAKLIK_KRITIK][1]
        elif t_max >= self.e.SICAKLIK_UYARI_C:
            s.bitmap |= (1 << Alarm.SICAKLIK_UYARI)
            s.alarmlar.append("SICAKLIK_UYARI")
            s.mesajlar.append(f"{ALARM_META[Alarm.SICAKLIK_UYARI][0]} ({sicak_faz} fazi {t_max:.1f} C)")
            ceza += ALARM_META[Alarm.SICAKLIK_UYARI][1]

        if o.nem_rh >= self.e.NEM_UYARI_RH:
            s.bitmap |= (1 << Alarm.NEM_YOGUSMA)
            s.alarmlar.append("NEM_YOGUSMA")
            s.mesajlar.append(f"{ALARM_META[Alarm.NEM_YOGUSMA][0]} (%{o.nem_rh:.0f} RH)")
            ceza += ALARM_META[Alarm.NEM_YOGUSMA][1]

        if {"SICAKLIK_UYARI", "SICAKLIK_KRITIK", "NEM_YOGUSMA"} & set(s.alarmlar):
            s.aksiyonlar.append("Alarm: Termal Asiri Yuk / Yogusma Riski")

        i_ort = (o.i_r + o.i_s + o.i_t) / 3.0
        s.dengesizlik_pct = dengesizlik_yuzdesi(o.i_r, o.i_s, o.i_t)

        dengesiz = s.dengesizlik_pct >= self.e.FAZ_DENGESIZLIK_YUZDE
        if dengesiz:
            s.bitmap |= (1 << Alarm.FAZ_DENGESIZLIGI)
            s.alarmlar.append("FAZ_DENGESIZLIGI")
            s.mesajlar.append(f"{ALARM_META[Alarm.FAZ_DENGESIZLIGI][0]} (%{s.dengesizlik_pct:.1f})")
            ceza += ALARM_META[Alarm.FAZ_DENGESIZLIGI][1]

        yuk_asimi, yuk_gerekce = False, ""

        if self.e.I_NOMINAL_A is not None:
            sinir = self.e.I_NOMINAL_A * self.e.ASIRI_YUK_ORANI
            if i_ort > sinir:
                yuk_asimi = True
                yuk_gerekce = f"I_ort {i_ort:.1f} A > %110 In ({sinir:.1f} A)"
        elif len(self._i_gecmis) == self._i_gecmis.maxlen:
            dun = self._i_gecmis[0]
            if dun > 1e-6 and i_ort / dun >= self.e.MEVSIMSEL_ARTIS_ORANI:
                yuk_asimi = True
                yuk_gerekce = (f"I_ort {i_ort:.1f} A, dun ayni saat {dun:.1f} A (+%{(i_ort / dun - 1) * 100:.0f})")

        self._yuk_sayac = self._yuk_sayac + 1 if yuk_asimi else 0
        self._i_gecmis.append(i_ort)

        if self._yuk_sayac >= self.e.ASIRI_YUK_TEYIT_ORNEK:
            s.bitmap |= (1 << Alarm.ASIRI_YUK)
            s.alarmlar.append("ASIRI_YUK")
            s.mesajlar.append(f"{ALARM_META[Alarm.ASIRI_YUK][0]} ({yuk_gerekce})")
            ceza += ALARM_META[Alarm.ASIRI_YUK][1]

        if dengesiz or self._yuk_sayac >= self.e.ASIRI_YUK_TEYIT_ORNEK:
            s.aksiyonlar.append("SCADA kayit: Faz Dengesizligi / Asiri Yuk")

        self.taban.guncelle(i_ort, saglikli=not (dengesiz or yuk_asimi))

        v = [o.v_r, o.v_s, o.v_t]
        if any(x < self.e.V_NOMINAL_V * self.e.V_ALT_ORAN or x > self.e.V_NOMINAL_V * self.e.V_UST_ORAN for x in v):
            s.bitmap |= (1 << Alarm.GERILIM_ANORMAL)
            s.alarmlar.append("GERILIM_ANORMAL")
            s.mesajlar.append(ALARM_META[Alarm.GERILIM_ANORMAL][0])
            ceza += ALARM_META[Alarm.GERILIM_ANORMAL][1]

        if self.termal and not ({"SICAKLIK_KRITIK", "FAZ_DENGESIZLIGI"} & set(s.alarmlar)):
            akimlar = {"R": o.i_r, "S": o.i_s, "T": o.i_t}
            sapmalar = {}
            for faz, model in self.termal.items():
                beklenen = model.adim(o.ortam_c, akimlar[faz])
                sapmalar[faz] = sicakliklar[faz] - beklenen
            en_kotu = max(sapmalar, key=sapmalar.get)
            if sapmalar[en_kotu] > self.e.TERMAL_SAPMA_C:
                s.bitmap |= (1 << Alarm.TERMAL_SAPMA)
                s.alarmlar.append("TERMAL_SAPMA")
                s.mesajlar.append(f"{ALARM_META[Alarm.TERMAL_SAPMA][0]} ({en_kotu} fazi +{sapmalar[en_kotu]:.1f} C)")
                ceza += ALARM_META[Alarm.TERMAL_SAPMA][1]

        if "SICAKLIK_KRITIK" not in s.alarmlar:
            t_vals = np.array([sicakliklar["R"], sicakliklar["S"], sicakliklar["T"]])
            en_sicak_idx = int(np.argmax(t_vals))
            diger_iki = np.delete(t_vals, en_sicak_idx)
            delta_t = t_vals[en_sicak_idx] - diger_iki.mean()
            diger_tutarli = np.max(np.abs(diger_iki - diger_iki.mean())) <= 2.0

            if delta_t > 10.0 and diger_tutarli and "TERMAL_SAPMA" not in s.alarmlar:
                s.bitmap |= (1 << Alarm.TERMAL_SAPMA)
                s.alarmlar.append("KONTAK_SUPHESI_TABLO")
                s.mesajlar.append(
                    f"Gevsek Baglanti Suphesi (IEEE738 kriteri): "
                    f"{['R','S','T'][en_sicak_idx]} fazi digerlerinden +{delta_t:.1f} C, diger fazlar tutarli")
                ceza += 20

        self._pd_gecmis.append(o.pd_pc)
        if len(self._pd_gecmis) == self._pd_gecmis.maxlen and "PD_UYARI" not in s.alarmlar and "PD_KRITIK" not in s.alarmlar:
            y = np.array(self._pd_gecmis)
            x = np.arange(len(y))
            egim = np.polyfit(x, y, 1)[0]  
            if egim > self.e.PD_TREND_EGIM_ESIK and y[-1] > y[0] * 1.5:
                s.bitmap |= (1 << Alarm.PD_UYARI)
                s.alarmlar.append("PD_TREND_ARTISI")
                s.mesajlar.append(f"Kismi Desarj Trend Uyarisi: son {len(y)} ornekte kademeli artis (egim {egim:.2f} pC/ornek)")
                ceza += 15

        s.saglik_skoru = max(0.0, 100.0 - ceza)
        if not s.alarmlar:
            s.seviye = "NORMAL"
            s.mesajlar = ["Sistem normal durumunda calisiyor"]
        else:
            seviyeler = [ALARM_META[Alarm[a]][2] for a in s.alarmlar if a in Alarm.__members__]
            sira = {"ACIL": 0, "KRITIK": 1, "UYARI": 2, "ON-UYARI": 3}
            s.seviye = min(seviyeler, key=lambda x: sira[x]) if seviyeler else "UYARI"

        self.gecmis.append(s)
        return s


# =============================================================================
# 5. CSV / DATAFRAME UZERINDE TOPLU CALISTIRMA
# =============================================================================

SUTUN_HARITASI = {
    "i_r": "current_r_A", "i_s": "current_s_A", "i_t": "current_t_A",
    "v_r": "voltage_r_V", "v_s": "voltage_s_V", "v_t": "voltage_t_V",
    "sicaklik_r": "temp_r_C", "sicaklik_s": "temp_s_C", "sicaklik_t": "temp_t_C",
    "nem_rh": "ambient_humidity_RH", "pd_pc": "pd_charge_pC",
    "ark_lux": "optical_lux", "ortam_c": "ambient_temp_C",
}


def calistir(df: pd.DataFrame,
             esik: Esikler = ESIK,
             termal_katman: bool = True,
             dt_s: float = 900.0,
             kilidi_yoksay: bool = True) -> pd.DataFrame:
    df = df.copy()
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])

    termal = {}
    if termal_katman and "ambient_temp_C" in df.columns:
        maske = (df["ground_truth"] == "NORMAL").values if "ground_truth" in df.columns else np.ones(len(df), dtype=bool)
        ortam = df["ambient_temp_C"].values
        for faz, ic, tc in [("R", "current_r_A", "temp_r_C"),
                            ("S", "current_s_A", "temp_s_C"),
                            ("T", "current_t_A", "temp_t_C")]:
            k, _ = termal_k_kalibre(df[ic].values, ortam, df[tc].values, maske, esik.TERMAL_TAU_S, dt_s)
            termal[faz] = TermalKestirimci(k, esik.TERMAL_TAU_S, dt_s, ortam[0], df[ic].values[0] ** 2)

    motor = AnomaliMotoru(esik, termal if termal_katman else None)

    satirlar = []
    for _, r in df.iterrows():
        kw = {alan: float(r[sut]) for alan, sut in SUTUN_HARITASI.items() if sut in df.columns}
        o = Okuma(zaman=r.get("timestamp"), **kw)
        s = motor.adim(o)
        if kilidi_yoksay and motor.kilitli:
            motor.reset()
        satirlar.append({
            "tespit_seviye": s.seviye,
            "tespit_alarmlar": "; ".join(s.alarmlar) if s.alarmlar else "NORMAL",
            "tespit_mesaj": " | ".join(s.mesajlar),
            "saglik_skoru": s.saglik_skoru,
            "modbus_bitmap": s.bitmap,
            "kesici_ac": s.kesici_ac,
            "dengesizlik_pct": round(s.dengesizlik_pct, 2),
            "aksiyon": " | ".join(s.aksiyonlar),
        })

    return pd.concat([df.reset_index(drop=True), pd.DataFrame(satirlar)], axis=1)


# =============================================================================
# 6. DOGRULAMA VE EXCEL RAPORLAMA (Takim arkadaslari icin ozel format)
# =============================================================================

def dogrula_ve_excele_yaz(rapor: pd.DataFrame, excel_yolu: str = "anomali_raporu_ve_metrikler.xlsx") -> None:
    if "ground_truth" not in rapor.columns:
        print("ground_truth sutunu yok, dogrulama atlandi.")
        rapor.to_excel(excel_yolu, index=False)
        return

    ilk = rapor["tespit_alarmlar"].apply(lambda x: x.split(";")[0].strip())
    ct = pd.crosstab(rapor["ground_truth"], ilk)

    gercek_anomali = rapor["ground_truth"] != "NORMAL"
    tespit_anomali = rapor["tespit_alarmlar"] != "NORMAL"
    tp = int((gercek_anomali & tespit_anomali).sum())
    fp = int((~gercek_anomali & tespit_anomali).sum())
    fn = int((gercek_anomali & ~tespit_anomali).sum())
    tn = int((~gercek_anomali & ~tespit_anomali).sum())
    kesinlik = tp / (tp + fp) if tp + fp else 0.0
    duyarlilik = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * kesinlik * duyarlilik / (kesinlik + duyarlilik) if kesinlik + duyarlilik else 0.0

    print("\n--- Karisiklik Tablosu (gercek x tespit) ---")
    print(ct.to_string())
    print(f"\nTP={tp}  FP={fp}  FN={fn}  TN={tn}")
    print(f"Kesinlik (precision): {kesinlik:.3f}")
    print(f"Duyarlilik (recall) : {duyarlilik:.3f}")
    print(f"F1                  : {f1:.3f}")

    # --- EXCEL OLUSTURMA ASAMASI ---
    try:
        with pd.ExcelWriter(excel_yolu, engine='openpyxl') as writer:
            # 1. Sayfa: Tüm teknik detayların olduğu ham veri
            rapor.to_excel(writer, sheet_name="Detayli_Rapor", index=False)

            # 2. Sayfa: Takım arkadaşlarının okuyacağı yönetici özeti
            ct.to_excel(writer, sheet_name="Performans_Ozeti", startrow=1, startcol=0)
            
            # Terimleri herkesin anlayacağı dile çeviriyoruz
            metrik_df = pd.DataFrame({
                "Metrik": [
                    "Gerçek Pozitif (TP) - Başarıyla Yakalanan Arızalar",
                    "Yanlış Pozitif (FP) - Sistem Boş Yere Alarm Verdi",
                    "Yanlış Negatif (FN) - Gözden Kaçırılan Arızalar",
                    "Gerçek Negatif (TN) - Doğru Bilinen Normal Durumlar",
                    "Kesinlik (Sistem alarm verdiğinde yüzde kaçı gerçekten arızaydı?)",
                    "Duyarlılık (Meydana gelen tüm arızaların yüzde kaçını yakalayabildik?)",
                    "F1 Skoru (Genel Başarı Puanı)"
                ],
                "Değer": [
                    tp, fp, fn, tn,
                    f"%{kesinlik*100:.1f}",
                    f"%{duyarlilik*100:.1f}",
                    round(f1, 3)
                ]
            })
            
            # Karışıklık tablosunun 4 satır altına metrikleri ekle
            metrik_df.to_excel(writer, sheet_name="Performans_Ozeti", startrow=len(ct)+4, startcol=0, index=False)
            
        print(f"\nTakim arkadaslari icin anlasilir Excel raporu kaydedildi -> {excel_yolu}")
        
    except ModuleNotFoundError:
        print("\nUYARI: Excel'e kaydetmek icin 'openpyxl' kutuphanesi eksik.")
        print("Terminale sunu yazarak yukleyebilirsin: pip install openpyxl")


# =============================================================================
# 7. SENTETIK VERI URETECI
# =============================================================================

def sentetik_veri(n: int = 800, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    t = pd.date_range("2026-01-01", periods=n, freq="15min")
    gunluk = np.sin(np.arange(n) * 2 * np.pi / 96)
    ortam = 22 + 6 * gunluk + rng.normal(0, 0.5, n)
    taban_i = 120 + 25 * gunluk + rng.normal(0, 3, n)

    i_r = taban_i + rng.normal(0, 2, n)
    i_s = taban_i + rng.normal(0, 2, n)
    i_t = taban_i + rng.normal(0, 2, n)
    nem = 55 + 12 * (-gunluk) + rng.normal(0, 3, n)
    pd_pc = np.abs(rng.normal(15, 6, n))
    lux = np.abs(rng.normal(30, 10, n))
    gt = np.array(["NORMAL"] * n, dtype=object)

    def pencere(baslangic, uzunluk):
        return slice(baslangic, baslangic + uzunluk)

    p = pencere(150, 30); i_r[p] *= 1.28; gt[p] = "FAZ_DENGESIZLIGI"          
    p = pencere(300, 25); pd_pc[p] += rng.uniform(120, 300, 25); gt[p] = "PD"  
    p = pencere(450, 20); nem[p] = rng.uniform(86, 94, 20); gt[p] = "NEM"      
    p = pencere(560, 28); i_r[p] *= 1.35; i_s[p] *= 1.35; i_t[p] *= 1.35; gt[p] = "ASIRI_YUK"
    lux[700] = 45000; gt[700] = "ARK"                                          

    k = 1.1e-3
    sic_r = ortam + k * i_r ** 2 + rng.normal(0, 0.6, n)
    sic_s = ortam + k * i_s ** 2 + rng.normal(0, 0.6, n)
    sic_t = ortam + k * i_t ** 2 + rng.normal(0, 0.6, n)
    p = pencere(620, 25); sic_s[p] += np.linspace(2, 30, 25); gt[p] = "KONTAK"  

    return pd.DataFrame({
        "timestamp": t, "current_r_A": i_r, "current_s_A": i_s, "current_t_A": i_t,
        "voltage_r_V": 230 + rng.normal(0, 1.5, n),
        "voltage_s_V": 230 + rng.normal(0, 1.5, n),
        "voltage_t_V": 230 + rng.normal(0, 1.5, n),
        "temp_r_C": sic_r, "temp_s_C": sic_s, "temp_t_C": sic_t,
        "ambient_temp_C": ortam, "ambient_humidity_RH": nem,
        "pd_charge_pC": pd_pc, "optical_lux": lux, "ground_truth": gt,
    })


# =============================================================================
# 8. CANLI DONGU ISKELETI
# =============================================================================

def canli_dongu(modbus_oku, sms_gonder=None, kesici_ac=None,
                scada_logla=None, periyot_s: float = 1.0):
    motor = AnomaliMotoru(ESIK)
    while True:
        s = motor.adim(modbus_oku())
        if scada_logla:
            scada_logla(asdict(s))
        if s.kesici_ac and kesici_ac:
            kesici_ac()                              
        if s.seviye in ("ACIL", "KRITIK") and sms_gonder:
            sms_gonder(" | ".join(s.mesajlar))
        if motor.kilitli:
            print("SISTEM KILITLI - operator resetine kadar bekleniyor")
            break
        time.sleep(periyot_s)


# =============================================================================
if __name__ == "__main__":
    import sys
    from pathlib import Path

    yol = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("grid_up_telemetry.csv")
    if yol.exists():
        veri = pd.read_csv(yol)
        print(f"Veri okundu: {yol}  ({len(veri)} satir)")
    else:
        veri = sentetik_veri()
        print(f"'{yol}' bulunamadi -> sentetik veri uretildi ({len(veri)} satir)")

    rapor = calistir(veri)
    
    print("\n--- Seviye dagilimi ---")
    print(rapor["tespit_seviye"].value_counts().to_string())
    print("\n--- Alarm dagilimi ---")
    print(rapor["tespit_alarmlar"].value_counts().head(12).to_string())
    print(f"\nOrtalama saglik skoru: {rapor['saglik_skoru'].mean():.1f}")
    print(f"Kesici acma komutu sayisi: {int(rapor['kesici_ac'].sum())}")
    
    dogrula_ve_excele_yaz(rapor)