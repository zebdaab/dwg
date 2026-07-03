#!/usr/bin/env python3
"""Diagnostic RE2020 XML (RSEE/Pleiades)."""

import argparse
import csv
import os
import re
import sys
import xml.etree.ElementTree as ET


DEEPWATT_KEYS = ("S_hab", "H", "r", "compacite")
RESULT_KEYS = (
    "O_Bbio_pts_annuel",
    "O_Bbio_Max",
    "O_Cef_annuel",
    "O_Cep_annuel",
    "O_Cep_Max",
    "O_NbDegresHeures",
    "O_NbDegresHeures_max",
)
ENVELOPE_KEYS = ("A_opv", "A_ophh", "A_baies", "A_T", "L_PT")
NUMBER_PATTERN = r"[-+]?(?:\d+(?:[\.,]\d*)?|[\.,]\d+)(?:[eE][-+]?\d+)?"


def local_name(tag):
    return tag.split("}", 1)[-1] if "}" in tag else tag


def to_float(value):
    if value is None:
        return None
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def fmt_number(value, digits=3):
    if value is None:
        return "N/A"
    return f"{value:.{digits}f}".rstrip("0").rstrip(".")


def almost_equal(a, b, tolerance=1e-2):
    if a is None or b is None:
        return False
    return abs(a - b) <= tolerance


def iter_elements(elem, ancestors=None):
    if ancestors is None:
        ancestors = []
    yield elem, ancestors
    for child in list(elem):
        for item in iter_elements(child, ancestors + [elem]):
            yield item


def find_first(root, target, required_ancestors=None):
    target_l = target.lower()
    required = {name.lower() for name in (required_ancestors or [])}

    for elem, ancestors in iter_elements(root):
        if local_name(elem.tag).lower() != target_l:
            continue
        if required:
            ancestor_names = {local_name(a.tag).lower() for a in ancestors}
            if not required.issubset(ancestor_names):
                continue
        text = (elem.text or "").strip()
        if text:
            return text
    return None


def parse_deepwatt_header(path):
    values = {}
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            head = f.read(4096)
    except OSError:
        return values

    match = re.search(r"<!--(.*?)-->", head, flags=re.DOTALL)
    if not match:
        return values

    comment = match.group(1)
    for key in DEEPWATT_KEYS:
        key_match = re.search(rf"\b{re.escape(key)}\s*=\s*({NUMBER_PATTERN})", comment)
        if key_match:
            values[key] = to_float(key_match.group(1))
    return values


def extract_metrics(path):
    data = {
        "file": os.path.basename(path),
        "path": path,
        "error": None,
    }
    data.update({f"deepwatt_{k}": None for k in DEEPWATT_KEYS})
    data.update({k: None for k in RESULT_KEYS})
    data.update({k: None for k in ENVELOPE_KEYS})

    deepwatt = parse_deepwatt_header(path)
    for key, value in deepwatt.items():
        data[f"deepwatt_{key}"] = value

    try:
        root = ET.parse(path).getroot()
    except Exception as exc:
        data["error"] = str(exc)
        return data

    data["shab_datas_comp"] = to_float(find_first(root, "O_SHAB", ["Datas_Comp", "batiment"]))
    data["shab_rset"] = to_float(find_first(root, "SHAB", ["RSET", "groupe"]))
    if data["shab_rset"] is None:
        data["shab_rset"] = to_float(find_first(root, "SHAB", ["RSET"]))

    data["sref_bat_existant"] = to_float(find_first(root, "sref_bat_existant", ["attestations"]))
    data["A_hab_gr_em_e"] = to_float(find_first(root, "A_hab_gr_em_e", ["emetteur_ecs"]))

    for key in RESULT_KEYS:
        data[key] = to_float(find_first(root, key))

    for key in ENVELOPE_KEYS:
        data[key] = to_float(find_first(root, key))

    data["shab_ref"] = data["shab_datas_comp"] if data["shab_datas_comp"] is not None else data["shab_rset"]
    data["compacite_reelle"] = (
        data["A_T"] / data["shab_ref"] if data["A_T"] is not None and data["shab_ref"] not in (None, 0) else None
    )

    data["warn_shab_mismatch"] = (
        data["shab_datas_comp"] is not None
        and data["shab_rset"] is not None
        and not almost_equal(data["shab_datas_comp"], data["shab_rset"], tolerance=0.05)
    )
    data["warn_sref_mismatch"] = (
        data["shab_ref"] is not None
        and data["sref_bat_existant"] is not None
        and not almost_equal(data["shab_ref"], data["sref_bat_existant"], tolerance=1.0)
    )
    data["warn_ahab_mismatch"] = (
        data["shab_ref"] is not None
        and data["A_hab_gr_em_e"] is not None
        and not almost_equal(data["shab_ref"], data["A_hab_gr_em_e"], tolerance=0.05)
    )

    def compliant(value_key, max_key):
        value = data[value_key]
        maximum = data[max_key]
        return None if value is None or maximum is None else value <= maximum

    data["ok_bbio"] = compliant("O_Bbio_pts_annuel", "O_Bbio_Max")
    data["ok_cep"] = compliant("O_Cep_annuel", "O_Cep_Max")
    data["ok_dh"] = compliant("O_NbDegresHeures", "O_NbDegresHeures_max")

    return data


def status_icon(value):
    if value is None:
        return "?"
    return "✅" if value else "❌"


def print_diagnostic(item):
    print(f"\nFichier: {item['file']}")
    if item.get("error"):
        print(f"  Erreur parsing XML: {item['error']}")
        return

    if any(item.get(f"deepwatt_{k}") is not None for k in DEEPWATT_KEYS):
        source = " ".join(
            f"{k}={fmt_number(item.get(f'deepwatt_{k}'), 4)}"
            for k in DEEPWATT_KEYS
            if item.get(f"deepwatt_{k}") is not None
        )
    else:
        source = "N/A"
    print(f"  Source DeepWatt : {source}")

    print(f"  SHAB Datas_Comp : {fmt_number(item.get('shab_datas_comp'), 3)} m²")
    print(f"  SHAB RSET       : {fmt_number(item.get('shab_rset'), 3)} m²")

    sref_line = f"  sref_bat_existant: {fmt_number(item.get('sref_bat_existant'), 3)}"
    if item.get("warn_sref_mismatch"):
        sref_line += "  ⚠️  INCOHÉRENCE"
    print(sref_line)

    ahab_line = f"  A_hab_gr_em_e   : {fmt_number(item.get('A_hab_gr_em_e'), 3)} m²"
    if item.get("warn_ahab_mismatch"):
        ahab_line += f"  ⚠️  INCOHÉRENCE (devrait être ~{fmt_number(item.get('shab_ref'), 3)})"
    print(ahab_line)

    print("  Cohérence SHAB  : " + ("❌ INCOHÉRENCE" if item.get("warn_shab_mismatch") else "✅ OK"))

    print("  --- Résultats RE2020 ---")
    print(
        f"  Bbio            : {fmt_number(item.get('O_Bbio_pts_annuel'), 3)} / {fmt_number(item.get('O_Bbio_Max'), 3)}  {status_icon(item.get('ok_bbio'))}"
    )
    print(
        f"  Cep             : {fmt_number(item.get('O_Cep_annuel'), 3)} / {fmt_number(item.get('O_Cep_Max'), 3)}  {status_icon(item.get('ok_cep'))}"
    )
    print(
        f"  DH (TIC)        : {fmt_number(item.get('O_NbDegresHeures'), 3)} / {fmt_number(item.get('O_NbDegresHeures_max'), 3)}  {status_icon(item.get('ok_dh'))}"
    )
    print(f"  Cef annuel      : {fmt_number(item.get('O_Cef_annuel'), 3)} kWhef/m²/an")

    print("  --- Enveloppe ---")
    print(f"  A_opv           : {fmt_number(item.get('A_opv'), 3)} m²")
    print(f"  A_ophh          : {fmt_number(item.get('A_ophh'), 3)} m²")
    print(f"  A_baies         : {fmt_number(item.get('A_baies'), 3)} m²")
    print(f"  A_T             : {fmt_number(item.get('A_T'), 3)} m²")
    print(f"  L_PT            : {fmt_number(item.get('L_PT'), 3)} m")
    print(f"  Compacité réelle: {fmt_number(item.get('compacite_reelle'), 3)}")


def print_summary_table(items):
    if not items:
        return

    headers = ["Fichier", "SHAB_Datas", "SHAB_RSET", "A_hab", "Bbio", "Cep", "DH", "A_T", "Compacité"]
    rows = []
    for item in items:
        rows.append(
            [
                item["file"],
                fmt_number(item.get("shab_datas_comp"), 2),
                fmt_number(item.get("shab_rset"), 2),
                fmt_number(item.get("A_hab_gr_em_e"), 2),
                status_icon(item.get("ok_bbio")),
                status_icon(item.get("ok_cep")),
                status_icon(item.get("ok_dh")),
                fmt_number(item.get("A_T"), 2),
                fmt_number(item.get("compacite_reelle"), 3),
            ]
        )

    widths = [len(h) for h in headers]
    for row in rows:
        for i, col in enumerate(row):
            widths[i] = max(widths[i], len(str(col)))

    def format_row(values):
        return " | ".join(str(v).ljust(widths[i]) for i, v in enumerate(values))

    print("\n=== TABLEAU DE SYNTHÈSE ===")
    print(format_row(headers))
    print("-+-".join("-" * w for w in widths))
    for row in rows:
        print(format_row(row))


def write_csv_report(items, output_path):
    fields = [
        "file",
        "path",
        "deepwatt_S_hab",
        "deepwatt_H",
        "deepwatt_r",
        "deepwatt_compacite",
        "shab_datas_comp",
        "shab_rset",
        "sref_bat_existant",
        "A_hab_gr_em_e",
        "O_Bbio_pts_annuel",
        "O_Bbio_Max",
        "O_Cef_annuel",
        "O_Cep_annuel",
        "O_Cep_Max",
        "O_NbDegresHeures",
        "O_NbDegresHeures_max",
        "A_opv",
        "A_ophh",
        "A_baies",
        "A_T",
        "L_PT",
        "compacite_reelle",
        "warn_shab_mismatch",
        "warn_sref_mismatch",
        "warn_ahab_mismatch",
        "ok_bbio",
        "ok_cep",
        "ok_dh",
        "error",
    ]
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for item in items:
            writer.writerow({key: item.get(key) for key in fields})


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Diagnostic XML RE2020 (RSEE/Pleiades)")
    parser.add_argument("files", nargs="+", help="Fichier(s) XML à analyser")
    parser.add_argument(
        "--csv",
        default="rsee_diagnostic_report.csv",
        help="Chemin du fichier CSV de sortie (défaut: rsee_diagnostic_report.csv)",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])

    files = [path for path in args.files if os.path.exists(path)]
    missing = [path for path in args.files if not os.path.exists(path)]

    if missing:
        for path in missing:
            print(f"Erreur: fichier introuvable: {path}", file=sys.stderr)

    if not files:
        print("Aucun fichier valide à analyser.", file=sys.stderr)
        return 1

    print("=== DIAGNOSTIC RSEE RE2020 ===")

    diagnostics = [extract_metrics(path) for path in files]
    for item in diagnostics:
        print_diagnostic(item)

    print_summary_table(diagnostics)

    write_csv_report(diagnostics, args.csv)
    print(f"\nRapport CSV exporté: {args.csv}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
