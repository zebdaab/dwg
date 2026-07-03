# Diagnostic RSEE RE2020

Script de diagnostic pour comparer des fichiers XML RE2020 (RSEE/Pleiades/DeepWatt).

## Utilisation

Depuis la racine du dépôt :

```bash
python diagnostics/rsee_diagnostic.py rsee1.xml deepwatt_rsee1_0001.xml deepwatt_rsee1_0002.xml
```

Ou avec expansion shell :

```bash
python diagnostics/rsee_diagnostic.py *.xml
```

Le script affiche :

- Source DeepWatt (`S_hab`, `H`, `r`, `compacite`) si présente
- SHAB (`Datas_Comp` et `RSET`)
- `sref_bat_existant`
- `A_hab_gr_em_e`
- Résultats RE2020 (`Bbio`, `Cep`, `Cef`, `DH` + valeurs max)
- Surfaces d'enveloppe (`A_opv`, `A_ophh`, `A_baies`, `A_T`, `L_PT`)
- Compacité réelle (`A_T / SHAB`)
- Alertes d'incohérence

Un rapport CSV est exporté par défaut dans :

`rsee_diagnostic_report.csv`

## Options

```bash
python diagnostics/rsee_diagnostic.py *.xml --csv mon_rapport.csv
```
