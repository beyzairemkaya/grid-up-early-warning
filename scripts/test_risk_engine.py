# -*- coding: utf-8 -*-
"""
=============================================================================
 TEST_RISK_ENGINE.PY  -  Anomali motorunu KENDI VERINLE calistir
=============================================================================
Kullanim (terminalde):

    python -m scripts.test_risk_engine veri.csv
    python -m scripts.test_risk_engine veri.csv --nominal 320
    python -m scripts.test_risk_engine veri.csv --cikti sonuc.csv
    python -m scripts.test_risk_engine --sablon   # bos sablon CSV uretir

Bu script jurinin/baska bir ekibin kendi CSV dosyasini getirip, sutun
isimleri birebir ayni olmasa bile (yaygin varyasyonlari taniyor) motoru
uzerinde calistirmasini saglar. Eksik sutun varsa NE eksik oldugunu ve
hangi ismi bekledigini acikca soyler; sessizce yanlis sonuc uretmez.
=============================================================================
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from src.risk_engine.anomali_motoru_v2 import (
    Esikler,
    SUTUN_HARITASI,
    calistir,
    dogrula_ve_excele_yaz as dogrula,
)


# =============================================================================
# 1. SUTUN ADI ESLESTIRME  -  farkli isimlendirmeleri taniyan alias sozlugu
# =============================================================================
# Anahtar: motorun bekledigi ic isim (SUTUN_HARITASI degerleri).
# Deger  : bu ic isme karsilik gelebilecek, sikca kullanilan varyasyonlar
#          (kucuk/buyuk harf, alt cizgi/bosluk farki otomatik yok sayilir).

TAKMA_ADLAR: dict[str, list[str]] = {
    "current_r_A":         ["current_r", "i_r", "ir", "akim_r", "akim_l1", "current_l1", "l1_akim", "phase_r_current"],
    "current_s_A":         ["current_s", "i_s", "is_", "akim_s", "akim_l2", "current_l2", "l2_akim", "phase_s_current"],
    "current_t_A":         ["current_t", "i_t", "it_", "akim_t", "akim_l3", "current_l3", "l3_akim", "phase_t_current"],
    "temp_r_C":            ["temp_r", "t_r", "sicaklik_r", "sicaklik_l1", "temperature_r", "faz_r_sicaklik"],
    "temp_s_C":             ["temp_s", "t_s", "sicaklik_s", "sicaklik_l2", "temperature_s", "faz_s_sicaklik"],
    "temp_t_C":             ["temp_t", "t_t", "sicaklik_t", "sicaklik_l3", "temperature_t", "faz_t_sicaklik"],
    "ambient_temp_C":       ["ambient_temp", "ortam_sicaklik", "ortam_c", "ambient_temperature", "disortam_sicaklik"],
    "ambient_humidity_RH":  ["ambient_humidity", "nem", "nem_rh", "humidity", "rh", "bagil_nem"],
    "pd_charge_pC":         ["pd", "pd_pc", "partial_discharge", "kismi_desarj", "pd_genlik", "hfct_pc"],
    "optical_lux":          ["lux", "ark_lux", "ark", "optical", "arc_lux", "ark_sinyal"],
    "voltage_r_V":          ["voltage_r", "v_r", "gerilim_r", "gerilim_l1"],
    "voltage_s_V":          ["voltage_s", "v_s", "gerilim_s", "gerilim_l2"],
    "voltage_t_V":          ["voltage_t", "v_t", "gerilim_t", "gerilim_l3"],
    "timestamp":            ["time", "zaman", "date", "tarih", "datetime"],
}

ZORUNLU_SUTUNLAR = [
    "current_r_A", "current_s_A", "current_t_A",
    "temp_r_C", "temp_s_C", "temp_t_C",
    "ambient_temp_C", "ambient_humidity_RH",
    "pd_charge_pC", "optical_lux",
]
OPSIYONEL_SUTUNLAR = ["voltage_r_V", "voltage_s_V", "voltage_t_V", "timestamp"]


def _normallestir(ad: str) -> str:
    return ad.strip().lower().replace(" ", "_").replace("-", "_")


def sutunlari_esle(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, str], list[str]]:
    """
    Gelen DataFrame'in sutunlarini motorun bekledigi ic isimlere esler.
    Doner: (yeniden adlandirilmis df, eslesme haritasi, hala eksik olanlar)
    """
    mevcut = {_normallestir(c): c for c in df.columns}
    eslesme: dict[str, str] = {}   # ic_isim -> kullanicinin sutun adi
    eksik: list[str] = []

    hedefler = ZORUNLU_SUTUNLAR + OPSIYONEL_SUTUNLAR
    for ic_isim in hedefler:
        adaylar = [_normallestir(ic_isim)] + [_normallestir(a) for a in TAKMA_ADLAR.get(ic_isim, [])]
        bulunan = None
        for aday in adaylar:
            if aday in mevcut:
                bulunan = mevcut[aday]
                break
        if bulunan is None:
            # kismi/alt-string eslesme son care (orn. "Akım R (A)" -> "akim_r")
            for norm_ad, orijinal_ad in mevcut.items():
                if any(aday in norm_ad or norm_ad in aday for aday in adaylar if len(aday) > 3):
                    bulunan = orijinal_ad
                    break
        if bulunan:
            eslesme[ic_isim] = bulunan
        elif ic_isim in ZORUNLU_SUTUNLAR:
            eksik.append(ic_isim)

    yeni_df = df.rename(columns={v: k for k, v in eslesme.items()})
    return yeni_df, eslesme, eksik


# =============================================================================
# 2. SABLON URETICI  -  judge'lar hangi formati bekledigimizi gorsun
# =============================================================================

def sablon_uret(yol: str = "veri_sablonu.csv", n: int = 5) -> None:
    ornek = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n, freq="15min"),
        "current_r_A": [310.2, 305.8, 318.4, 522.1, 309.0],
        "current_s_A": [308.5, 303.1, 316.0, 519.6, 311.2],
        "current_t_A": [312.0, 306.4, 320.1, 524.8, 307.9],
        "temp_r_C": [45.1, 44.8, 46.2, 92.5, 44.9],
        "temp_s_C": [44.9, 44.6, 46.0, 60.1, 44.7],
        "temp_t_C": [45.3, 44.9, 46.3, 61.0, 45.0],
        "ambient_temp_C": [24.0, 23.8, 24.5, 26.1, 24.1],
        "ambient_humidity_RH": [55.0, 56.2, 54.8, 57.0, 55.5],
        "pd_charge_pC": [3.2, 2.8, 3.5, 4.1, 3.0],
        "optical_lux": [22.0, 25.1, 20.8, 24.0, 21.5],
        "ground_truth": ["NORMAL", "NORMAL", "NORMAL", "GEVSEK_BAGLANTI", "NORMAL"],
    })
    ornek.to_csv(yol, index=False)
    print(f"Sablon uretildi -> {yol}")
    print("\nZorunlu sutunlar (isim degistirilebilir, script otomatik tanimaya calisir):")
    for s in ZORUNLU_SUTUNLAR:
        print(f"  - {s}")
    print("\nOpsiyonel sutunlar:")
    for s in OPSIYONEL_SUTUNLAR:
        print(f"  - {s}")
    print("\nground_truth sutunu VARSA (etiketli veri), script otomatik olarak")
    print("precision/recall/F1 hesaplar. YOKSA sadece tespit raporunu uretir.")


# =============================================================================
# 3. ANA CALISTIRMA AKISI
# =============================================================================

def calistir_ve_raporla(csv_yolu: str, nominal_akim: float | None,
                        cikti_yolu: str | None, termal_kapat: bool) -> int:
    yol = Path(csv_yolu)
    if not yol.exists():
        print(f"HATA: dosya bulunamadi -> {csv_yolu}")
        return 1

    try:
        df = pd.read_csv(yol)
    except Exception as e:
        print(f"HATA: CSV okunamadi ({e}). Dosyanin gercekten CSV formatinda "
              f"oldugundan ve virgulle ayrildığindan emin ol.")
        return 1

    print(f"Dosya okundu: {yol.name}  ({len(df)} satir, {len(df.columns)} sutun)")
    print(f"Bulunan sutunlar: {list(df.columns)}\n")

    df, eslesme, eksik = sutunlari_esle(df)

    if eksik:
        print("HATA: asagidaki ZORUNLU sutunlar veride bulunamadi (veya "
              "otomatik taninamadi):\n")
        for e in eksik:
            olasi = TAKMA_ADLAR.get(e, [])
            print(f"  - {e}   (beklenen isimler: {e}, {', '.join(olasi)})")
        print("\nCozum: sutun basliklarini yukaridaki isimlerden birine "
              "cevir, ya da --sablon ile ornek formati incele:\n"
              "  python -m scripts.test_risk_engine --sablon")
        return 1

    print("Sutun eslesmesi basarili:")
    for ic_isim, kullanici_ad in eslesme.items():
        isaret = "=" if _normallestir(ic_isim) == _normallestir(kullanici_ad) else "<-"
        print(f"  {ic_isim:22s} {isaret} {kullanici_ad}")
    print()

    # --- olculmeyen ama gerekli olabilecek opsiyonel sutunlari doldur ------
    for opsiyonel in ["voltage_r_V", "voltage_s_V", "voltage_t_V"]:
        if opsiyonel not in df.columns:
            df[opsiyonel] = 230.0  # gerilim olculmuyorsa notr deger, o kontrolu devre disi birakir

    esik = Esikler()
    if nominal_akim is not None:
        esik.I_NOMINAL_A = nominal_akim
        print(f"Nominal akim manuel girildi: {nominal_akim} A "
              f"(mutlak asiri yuk esigi: {nominal_akim * esik.ASIRI_YUK_ORANI:.0f} A)\n")
    else:
        print("Nominal akim verilmedi -> mevsimsel (dun ayni saat) karsilastirma "
              "kullanilacak. Daha kesin sonuc icin: --nominal <deger>\n")

    try:
        rapor = calistir(df, esik=esik, termal_katman=not termal_kapat)
    except Exception as e:
        print(f"HATA: motor calisirken sorun cikti -> {e}")
        print("Ipucu: sayisal sutunlarda metin/bos hucre olmadigindan emin ol "
              "(orn. 'N/A', virgullu ondalik '3,14' gibi).")
        return 1

    # --- ozet rapor --------------------------------------------------------
    print("=" * 60)
    print("SONUC OZETI")
    print("=" * 60)
    print("\nSeviye dagilimi:")
    print(rapor["tespit_seviye"].value_counts().to_string())
    print("\nEn sik 10 alarm turu:")
    print(rapor["tespit_alarmlar"].value_counts().head(10).to_string())
    print(f"\nOrtalama saglik skoru : {rapor['saglik_skoru'].mean():.1f} / 100")
    print(f"Kesici acma karari (simulasyon): {int(rapor['kesici_ac'].sum())} kez")
    print(f"En dusuk saglik skoru : {rapor['saglik_skoru'].min():.1f}  "
          f"({rapor.loc[rapor['saglik_skoru'].idxmin(), 'tespit_alarmlar']})")

    if "ground_truth" in df.columns:
        rapor["ground_truth"] = df["ground_truth"]
        print()
        dogrula(rapor)
    else:
        print("\n(ground_truth sutunu yok -> dogruluk/precision-recall "
              "hesaplanamadi, sadece tespit raporu uretildi)")

    # --- kaydet --------------------------------------------------------
    cikti = cikti_yolu or f"anomali_sonuc_{yol.stem}.csv"
    rapor.to_csv(cikti, index=False)
    print(f"\nTam rapor kaydedildi -> {cikti}")
    return 0


# =============================================================================
# 4. CLI GIRIS NOKTASI
# =============================================================================

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Anomali tespit motorunu kendi CSV verinle calistir.")
    ap.add_argument("csv", nargs="?", help="Test edilecek CSV dosyasi")
    ap.add_argument("--nominal", type=float, default=None,
                    help="Fider/pano nominal akimi (A). Verilirse asiri yuk "
                         "tespiti mutlak esikle yapilir (daha kesin).")
    ap.add_argument("--cikti", type=str, default=None,
                    help="Rapor CSV'sinin kaydedilecegi yol (varsayilan: otomatik isim)")
    ap.add_argument("--termal-kapat", action="store_true",
                    help="Opsiyonel termal kestirim/erken uyari katmanini devre disi birak "
                         "(sadece semanin ciplak esik mantigini gormek icin)")
    ap.add_argument("--sablon", action="store_true",
                    help="Ornek/bos bir veri sablonu uretir ve cikar")
    args = ap.parse_args()

    if args.sablon:
        sablon_uret()
        return 0

    if not args.csv:
        ap.print_help()
        print("\nOrnek kullanim:\n  python -m scripts.test_risk_engine grid_verisi.csv --nominal 320")
        return 1

    return calistir_ve_raporla(args.csv, args.nominal, args.cikti, args.termal_kapat)


if __name__ == "__main__":
    sys.exit(main())
