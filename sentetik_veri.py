from __future__ import annotations

import datetime as dt
import glob
import os
from dataclasses import dataclass

import numpy as np
import pandas as pd


# =============================================================================
# 1. GERÇEK ÖLÇÜM VERİSİNİN OKUNMASI (İstenen Veriler.xlsx -> Akım Sensörü)
# =============================================================================

def gercek_akim_verisini_oku(klasor_veya_dosya: str = ".") -> np.ndarray | None:
    """Klasördeki Excel dosyasını (isim/boşluk varyasyonlarına toleranslı) bulur

    ve primer akım sütununu okur. Dosya yoksa None döner.
    """
    try:
        from openpyxl import load_workbook
    except ImportError:
        return None

    hedef_dosya = None
    if os.path.isfile(klasor_veya_dosya) and klasor_veya_dosya.endswith((".xlsx", ".xls")):
        hedef_dosya = klasor_veya_dosya
    else:
        bulunanlar = glob.glob(os.path.join(klasor_veya_dosya, "*Veriler*.xlsx")) or glob.glob("*.xlsx")
        if bulunanlar:
            hedef_dosya = bulunanlar[0]

    if not hedef_dosya:
        return None

    try:
        wb = load_workbook(hedef_dosya, read_only=True, data_only=True)
        if "Akım Sensörü" not in wb.sheetnames:
            return None
        ws = wb["Akım Sensörü"]
        rows = list(ws.iter_rows(values_only=True))[6:]
        degerler = [r[4] for r in rows if len(r) > 4 and r[4] is not None]
        return np.asarray(degerler, dtype=float) if degerler else None
    except Exception:
        return None


# =============================================================================
# 2. STANDARTLARA UYGUN FİZİK PARAMETRELERİ (IEC 60943, IEEE 738)
# =============================================================================

@dataclass
class FizikParametreleri:
    # Aşırı Yük (IEC 60943, TEDAŞ-MLZ/2003-06.B)
    I_NOMINAL_FIDER_A: float = 320.0
    ASIRI_YUK_ORAN_MIN: float = 1.20
    ASIRI_YUK_ORAN_MAX: float = 1.50
    TERMAL_TAU_MIN_DK: float = 15.0
    TERMAL_TAU_MAX_DK: float = 45.0
    K_ISI_TRANSFERI: float = 4.0e-4

    # Gevşek Bağlantı (IEEE Std 738)
    GEVSEK_DIRENC_CARPANI_MIN: float = 2.8
    GEVSEK_DIRENC_CARPANI_MAX: float = 4.5
    GEVSEK_ONSET_DK_MIN: float = 5.0
    GEVSEK_ONSET_DK_MAX: float = 25.0

    # Çevre & İzolasyon Riski (TEDAŞ-MLZ/2003-06.B)
    NEM_RISK_ESIK_RH: float = 85.0
    CIG_NOKTASI_SOGUMA_C: float = 2.5

    # Kısmi Deşarj HFCT (EA Technology)
    PD_TABAN_PC: float = 3.0
    PD_TABAN_GURULTU_PC: float = 1.2
    PD_TETIKLEME_GECIKME_SAAT: tuple = (8.0, 20.0)
    PD_TREND_SURE_SAAT: tuple = (12.0, 36.0)
    PD_MAX_GENLIK_PC: tuple = (120.0, 350.0)

    # Örnekleme Aralığı
    DT_DK: float = 15.0


P = FizikParametreleri()


# =============================================================================
# 3. TABAN ZAMAN SERİLERİNİN OLUŞTURULMASI
# =============================================================================

def taban_akim_serisi(n: int, gercek_veri: np.ndarray | None, rng: np.random.Generator) -> np.ndarray:
    saat = (np.arange(n) * P.DT_DK / 60.0) % 24.0
    gunluk_cevrim = 0.22 * np.sin((saat - 7) / 24 * 2 * np.pi) + 0.82

    if gercek_veri is not None and len(gercek_veri) >= 8:
        taban_ort = float(np.mean(gercek_veri))
        taban_std = float(np.std(gercek_veri))
    else:
        taban_ort, taban_std = P.I_NOMINAL_FIDER_A * 0.85, 0.08 * P.I_NOMINAL_FIDER_A

    merkez = min(taban_ort, P.I_NOMINAL_FIDER_A * 0.90)
    gurultu = rng.normal(0, taban_std * 0.35, n)
    return np.clip(merkez * gunluk_cevrim + gurultu, 35.0, P.I_NOMINAL_FIDER_A * 1.02)


def taban_ortam_serisi(n: int, rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray]:
    saat = (np.arange(n) * P.DT_DK / 60.0) % 24.0
    ortam_c = 24.0 + 6.5 * np.sin((saat - 14) / 24 * 2 * np.pi) + rng.normal(0, 0.35, n)
    nem_rh = np.clip(
        52.0 - 14.0 * np.sin((saat - 14) / 24 * 2 * np.pi) + rng.normal(0, 1.8, n),
        35.0, 75.0,
    )
    return ortam_c, nem_rh


# =============================================================================
# 4. FİZİKSEL ANOMALİ ENJEKSİYONLARI
# =============================================================================

def enjekte_asiri_yuk(i_r, i_s, i_t, sic_r, sic_s, sic_t, ortam_c,
                       gt, asama, baslangic, uzunluk, rng):
    oran = rng.uniform(P.ASIRI_YUK_ORAN_MIN, P.ASIRI_YUK_ORAN_MAX)
    yeni_seviye = P.I_NOMINAL_FIDER_A * oran
    tau_dk = rng.uniform(P.TERMAL_TAU_MIN_DK, P.TERMAL_TAU_MAX_DK)
    alpha = 1.0 - np.exp(-P.DT_DK / tau_dk)
    k = rng.uniform(3.4e-4, 4.6e-4)

    # 1. Aşama & 2. Aşama: Akım sıçraması ve üstel ısınma
    for j in range(uzunluk):
        idx = baslangic + j
        if idx >= len(i_r):
            break
        i_r[idx] = yeni_seviye * (1 + rng.normal(0, 0.015))
        i_s[idx] = yeni_seviye * (1 + rng.normal(0, 0.015))
        i_t[idx] = yeni_seviye * (1 + rng.normal(0, 0.015))

        hedef_t = ortam_c[idx] + k * (yeni_seviye ** 2)
        onceki_t = sic_r[idx - 1] if idx > 0 else ortam_c[idx]
        sic_r[idx] = onceki_t + alpha * (hedef_t - onceki_t)
        sic_s[idx] = sic_r[idx] + rng.normal(0, 0.4)
        sic_t[idx] = sic_r[idx] + rng.normal(0, 0.4)

        gt[idx] = "ASIRI_YUK"
        asama[idx] = 1 if j == 0 else 2

    # Soğuma Eğrisi: Termal uçurumu önleyen üstel sönümlenme
    soguma_ornek = int(75 / P.DT_DK)
    for j in range(soguma_ornek):
        s_idx = baslangic + uzunluk + j
        if s_idx >= len(i_r) or gt[s_idx] != "NORMAL":
            break
        hedef_normal = ortam_c[s_idx] + k * (i_r[s_idx] ** 2)
        sic_r[s_idx] = sic_r[s_idx - 1] + alpha * (hedef_normal - sic_r[s_idx - 1])
        sic_s[s_idx] = sic_r[s_idx] + rng.normal(0, 0.4)
        sic_t[s_idx] = sic_r[s_idx] + rng.normal(0, 0.4)

    return baslangic + uzunluk


def enjekte_gevsek_baglanti(i_r, i_s, i_t, sic_r, sic_s, sic_t, ortam_c,
                             gt, asama, baslangic, uzunluk, rng):
    hedef_faz = rng.choice(["R", "S", "T"])
    ek_direnc_carpani = rng.uniform(P.GEVSEK_DIRENC_CARPANI_MIN, P.GEVSEK_DIRENC_CARPANI_MAX)
    onset_ornek = max(1, int(rng.uniform(P.GEVSEK_ONSET_DK_MIN, P.GEVSEK_ONSET_DK_MAX) / P.DT_DK))
    diziler = {"R": (sic_r, i_r), "S": (sic_s, i_s), "T": (sic_t, i_t)}

    for j in range(uzunluk):
        idx = baslangic + j
        if idx >= len(i_r):
            break
        ilerleme = min(1.0, (j + 1) / onset_ornek)

        for faz, (sic_dizi, i_dizi) in diziler.items():
            isi_kaybi = P.K_ISI_TRANSFERI * (i_dizi[idx] ** 2)
            taban = ortam_c[idx] + isi_kaybi
            if faz == hedef_faz:
                # I^2 * R artışı simülasyonu
                sic_dizi[idx] = taban + (isi_kaybi * (ek_direnc_carpani - 1.0) + 14.0) * ilerleme + rng.normal(0, 0.5)
            else:
                sic_dizi[idx] = taban + rng.normal(0, 0.4)

        gt[idx] = "GEVSEK_BAGLANTI"
        asama[idx] = 1
    return baslangic + uzunluk


def enjekte_nem_izolasyon(nem_rh, ortam_c, gt_nem, baslangic, uzunluk, rng):
    hedef_rh = rng.uniform(P.NEM_RISK_ESIK_RH + 2, 94.0)
    for j in range(uzunluk):
        idx = baslangic + j
        if idx >= len(nem_rh):
            break
        ilerleme = j / max(uzunluk - 1, 1)
        nem_rh[idx] = nem_rh[idx] * (1 - ilerleme) + hedef_rh * ilerleme + rng.normal(0, 0.8)
        ortam_c[idx] -= P.CIG_NOKTASI_SOGUMA_C * ilerleme
        gt_nem[idx] = "IZOLASYON_RISKI"
    return baslangic + uzunluk


def enjekte_pd(pd_pc, gt_pd, tetikleme_idx, sure_ornek, rng):
    tepe_pc = rng.uniform(*P.PD_MAX_GENLIK_PC)
    for j in range(sure_ornek):
        idx = tetikleme_idx + j
        if idx >= len(pd_pc):
            break
        ilerleme = (j + 1) / sure_ornek
        pd_pc[idx] = P.PD_TABAN_PC + tepe_pc * (ilerleme ** 1.3) + rng.normal(0, tepe_pc * 0.04)
        gt_pd[idx] = "KISMI_DESARJ"
    return tetikleme_idx + sure_ornek


# =============================================================================
# 5. ANA ÜRETİCİ
# =============================================================================

def sentetik_veri_uret(
    gun_sayisi: float = 21.0,
    seed: int = 42,
    klasor_veya_dosya: str = ".",
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = int(gun_sayisi * 24 * 60 / P.DT_DK)

    gercek_veri = gercek_akim_verisini_oku(klasor_veya_dosya)
    kaynak = "Gerçek Akım Sensörü Ölçümü + Günlük Profil" if gercek_veri is not None else "Simüle Profil"

    baslangic_ts = dt.datetime(2026, 1, 1, 0, 0)
    zaman = [baslangic_ts + dt.timedelta(minutes=P.DT_DK * i) for i in range(n)]

    i_r = taban_akim_serisi(n, gercek_veri, rng)
    i_s = i_r * (1 + rng.normal(0, 0.012, n))
    i_t = i_r * (1 + rng.normal(0, 0.012, n))
    ortam_c, nem_rh = taban_ortam_serisi(n, rng)

    k0 = P.K_ISI_TRANSFERI
    sic_r = ortam_c + k0 * (i_r ** 2) + rng.normal(0, 0.35, n)
    sic_s = ortam_c + k0 * (i_s ** 2) + rng.normal(0, 0.35, n)
    sic_t = ortam_c + k0 * (i_t ** 2) + rng.normal(0, 0.35, n)

    pd_pc = np.abs(rng.normal(P.PD_TABAN_PC, P.PD_TABAN_GURULTU_PC, n))
    ark_lux = np.abs(rng.normal(20.0, 6.0, n))

    gt = np.array(["NORMAL"] * n, dtype=object)
    asama = np.zeros(n, dtype=int)

    olaylar = []
    # 1) Aşırı Yük Vakaları
    for _ in range(3):
        b = int(rng.uniform(0.08, 0.85) * n)
        u = int(rng.uniform(2.0, 4.5) * 60 / P.DT_DK)
        olaylar.append(("ASIRI_YUK", b, u))

    # 2) Gevşek Bağlantı Vakaları
    for _ in range(3):
        b = int(rng.uniform(0.08, 0.85) * n)
        u = int(rng.uniform(3.0, 6.0) * 60 / P.DT_DK)
        olaylar.append(("GEVSEK_BAGLANTI", b, u))

    olaylar.sort(key=lambda x: x[1])
    rezerve = np.zeros(n, dtype=bool)

    for tip, b, u in olaylar:
        while b < n and rezerve[b:min(b + u + 8, n)].any():
            b += u + 8
        if b >= n:
            continue
        u = min(u, n - b)
        if tip == "ASIRI_YUK":
            enjekte_asiri_yuk(i_r, i_s, i_t, sic_r, sic_s, sic_t, ortam_c, gt, asama, b, u, rng)
        else:
            enjekte_gevsek_baglanti(i_r, i_s, i_t, sic_r, sic_s, sic_t, ortam_c, gt, asama, b, u, rng)
        rezerve[b:min(b + u + 6, n)] = True

    # 3) İzolasyon Riski ve Kısmi Deşarj (PD)
    gt_nem = np.array(["NORMAL"] * n, dtype=object)
    gt_pd = np.array(["NORMAL"] * n, dtype=object)

    gece_adimlar = [i for i in range(n) if 1 <= (i * P.DT_DK / 60) % 24 <= 4]
    secilen_gunler = sorted(list(set(int(i / (24 * 60 / P.DT_DK)) for i in gece_adimlar)))
    izolasyon_gunleri = rng.choice(secilen_gunler[2:-3], size=2, replace=False)

    for gun_no in izolasyon_gunleri:
        gece_b = int(gun_no * 24 * 60 / P.DT_DK + 1.5 * 60 / P.DT_DK)
        u_nem = int(rng.uniform(2.5, 4.0) * 60 / P.DT_DK)
        if gece_b + u_nem < n:
            enjekte_nem_izolasyon(nem_rh, ortam_c, gt_nem, gece_b, u_nem, rng)
            
            gecikme = rng.uniform(*P.PD_TETIKLEME_GECIKME_SAAT)
            pd_b = gece_b + int(gecikme * 60 / P.DT_DK)
            pd_sure = int(rng.uniform(*P.PD_TREND_SURE_SAAT) * 60 / P.DT_DK)
            if pd_b < n:
                enjekte_pd(pd_pc, gt_pd, pd_b, min(pd_sure, n - pd_b), rng)

    ground_truth = gt.copy()
    problem_asamasi = asama.copy()
    for i in range(n):
        if ground_truth[i] == "NORMAL" and gt_nem[i] != "NORMAL":
            ground_truth[i] = gt_nem[i]
            problem_asamasi[i] = 1
        if gt_pd[i] != "NORMAL" and ground_truth[i] == "NORMAL":
            ground_truth[i] = gt_pd[i]
            problem_asamasi[i] = 2

    df = pd.DataFrame({
        "timestamp": zaman,
        "current_r_A": np.round(i_r, 2),
        "current_s_A": np.round(i_s, 2),
        "current_t_A": np.round(i_t, 2),
        "temp_r_C": np.round(sic_r, 2),
        "temp_s_C": np.round(sic_s, 2),
        "temp_t_C": np.round(sic_t, 2),
        "ambient_temp_C": np.round(ortam_c, 2),
        "ambient_humidity_RH": np.round(nem_rh, 2),
        "pd_charge_pC": np.round(pd_pc, 2),
        "optical_lux": np.round(ark_lux, 2),
        "ground_truth": ground_truth,
        "problem_asamasi": problem_asamasi,
    })
    df.attrs["veri_kaynagi"] = kaynak
    return df


if __name__ == "__main__":
    df = sentetik_veri_uret(gun_sayisi=21, seed=42)
    cikis_yolu = "sentetik_veri_problem_bazli.csv"
    df.to_csv(cikis_yolu, index=False)
    print(f"Başarıyla üretildi: {cikis_yolu}")
    print(f"Veri Kaynağı: {df.attrs['veri_kaynagi']}")
    print(f"Toplam Satır: {len(df)}")
    print("\n--- Sınıf Dağılımı ---")
    print(df["ground_truth"].value_counts())
