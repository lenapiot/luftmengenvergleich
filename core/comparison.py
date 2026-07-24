import re
import pandas as pd

def normalize_name(value: object) -> str | None:
   """Normalisiert einen Raumnamen für den Vergleich."""
   if value is None or pd.isna(value):
       return None
   text = re.sub(
       r"\s+",
       " ",
       str(value),
   ).strip().casefold()
   return text or None

def unique_non_null_values(
   series: pd.Series,
) -> list[object]:
   """Gibt eindeutige, nichtleere Werte einer Spalte zurück."""
   values: list[object] = []
   for value in series:
       if value is None or pd.isna(value):
           continue
       if value not in values:
           values.append(value)
   return values

def consolidate_rooms(
   raw_df: pd.DataFrame,
   source_label: str,
) -> pd.DataFrame:
   """
   Erstellt pro Raumnummer eine Vergleichszeile.
   Mehrere identische Funde sind erlaubt.
   Mehrere widersprüchliche Werte werden als uneindeutig gekennzeichnet.
   """
   columns = [
       "raumnummer",
       f"raumname_{source_label}",
       f"zul_{source_label}",
       f"abl_{source_label}",
       f"seiten_{source_label}",
       f"anzahl_funde_{source_label}",
       f"uneindeutig_{source_label}",
   ]
   if raw_df.empty:
       return pd.DataFrame(columns=columns)
   rows: list[dict[str, object]] = []
   for room_id, group in raw_df.groupby(
       "raumnummer",
       sort=True,
   ):
       names = unique_non_null_values(
           group["raumname"]
       )
       zul_values = unique_non_null_values(
           group["zul"]
       )
       abl_values = unique_non_null_values(
           group["abl"]
       )
       pages = sorted(
           {
               int(page)
               for page in group["seite"]
               if page is not None
               and not pd.isna(page)
           }
       )
       ambiguous = (
           len(names) > 1
           or len(zul_values) > 1
           or len(abl_values) > 1
       )
       rows.append(
           {
               "raumnummer": room_id,
               f"raumname_{source_label}": (
                   names[0]
                   if len(names) == 1
                   else " | ".join(
                       map(str, names)
                   )
               ),
               f"zul_{source_label}": (
                   zul_values[0]
                   if len(zul_values) == 1
                   else None
               ),
               f"abl_{source_label}": (
                   abl_values[0]
                   if len(abl_values) == 1
                   else None
               ),
               f"seiten_{source_label}": ", ".join(
                   map(str, pages)
               ),
               f"anzahl_funde_{source_label}": len(group),
               f"uneindeutig_{source_label}": ambiguous,
           }
       )
   return pd.DataFrame(
       rows,
       columns=columns,
   )

def determine_status(
   row: pd.Series,
) -> str:
   """Bestimmt den Status einer Vergleichszeile."""
   if row["_merge"] == "left_only":
       return "Nur im Grundriss"
   if row["_merge"] == "right_only":
       return "Nur im Schema"
   if (
       bool(
           row.get(
               "uneindeutig_grundriss",
               False,
           )
       )
       or bool(
           row.get(
               "uneindeutig_schema",
               False,
           )
       )
   ):
       return "Mehrfach / uneindeutig"
   if (
       not row["zul_stimmt"]
       or not row["abl_stimmt"]
   ):
       return "Abweichung Luftmenge"
   if not row["raumname_stimmt"]:
       return "Abweichung Raumname"
   return "OK"

def build_comparison(
   floorplan_raw_df: pd.DataFrame,
   schema_raw_df: pd.DataFrame,
) -> pd.DataFrame:
   """Erstellt die vollständige Vergleichstabelle."""
   floorplan_df = consolidate_rooms(
       floorplan_raw_df,
       "grundriss",
   )
   schema_df = consolidate_rooms(
       schema_raw_df,
       "schema",
   )
   comparison_df = pd.merge(
       floorplan_df,
       schema_df,
       on="raumnummer",
       how="outer",
       indicator=True,
   )
   comparison_df["vorkommen"] = (
       comparison_df["_merge"]
       .astype(str)
       .replace(
           {
               "both": "Grundriss und Schema",
               "left_only": "Nur Grundriss",
               "right_only": "Nur Schema",
           }
       )
   )
   both_mask = (
       comparison_df["_merge"] == "both"
   )
   comparison_df["zul_stimmt"] = False
   comparison_df["abl_stimmt"] = False
   comparison_df["raumname_stimmt"] = False
   comparison_df.loc[
       both_mask,
       "zul_stimmt",
   ] = (
       comparison_df.loc[
           both_mask,
           "zul_grundriss",
       ]
       ==
       comparison_df.loc[
           both_mask,
           "zul_schema",
       ]
   )
   comparison_df.loc[
       both_mask,
       "abl_stimmt",
   ] = (
       comparison_df.loc[
           both_mask,
           "abl_grundriss",
       ]
       ==
       comparison_df.loc[
           both_mask,
           "abl_schema",
       ]
   )
   comparison_df.loc[
       both_mask,
       "raumname_stimmt",
   ] = [
       normalize_name(left)
       == normalize_name(right)
       for left, right in zip(
           comparison_df.loc[
               both_mask,
               "raumname_grundriss",
           ],
           comparison_df.loc[
               both_mask,
               "raumname_schema",
           ],
       )
   ]
   comparison_df["status"] = (
       comparison_df.apply(
           determine_status,
           axis=1,
       )
   )
   comparison_df = comparison_df.drop(
       columns=["_merge"]
   )
   status_order = pd.CategoricalDtype(
       categories=[
           "Abweichung Luftmenge",
           "Abweichung Raumname",
           "Mehrfach / uneindeutig",
           "Nur im Grundriss",
           "Nur im Schema",
           "OK",
       ],
       ordered=True,
   )
   comparison_df["status"] = (
       comparison_df["status"]
       .astype(status_order)
   )
   return (
       comparison_df
       .sort_values(
           ["status", "raumnummer"]
       )
       .reset_index(drop=True)
   )
