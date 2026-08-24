from pathlib import Path
from tkinter import Tk, filedialog
import fitz

def choose_pdf(title: str) -> Path:
   path = filedialog.askopenfilename(
       title=title,
       filetypes=[("PDF-Dateien", "*.pdf")],
   )
   if not path:
       raise SystemExit("Keine Datei ausgewählt.")
   return Path(path)

def normalize_room_text(text: str) -> str:
   """
   Normalisiert Raumnummern aus dem Schema.
   Beispiel:
       MIT2H302
       MIT 2H302
       MIT  2H302
   werden alle zu:
       MIT2H302
   """
   return (
       str(text)
       .strip()
       .replace(" ", "")
       .replace("\t", "")
       .upper()
   )

def main() -> None:
   root = Tk()
   root.withdraw()
   pdf_path = choose_pdf(
       "MIT2 Strangschema Klimawärme/Kälte auswählen"
   )
   target_room = "MIT2H302"
   normalized_target = normalize_room_text(
       target_room
   )
   print()
   print("=" * 70)
   print("SCHEMA-POSITIONSTEST")
   print("=" * 70)
   print("Datei:", pdf_path.name)
   print("Gesuchter Raum:", target_room)
   print()
   with fitz.open(pdf_path) as document:
       found_any_room = False
       for page_number, page in enumerate(
           document,
           start=1,
       ):
           data = page.get_text("dict")
           spans = []
           for block in data["blocks"]:
               if "lines" not in block:
                   continue
               for line in block["lines"]:
                   for span in line["spans"]:
                       text = span["text"].strip()
                       if not text:
                           continue
                       spans.append(
                           {
                               "text": text,
                               "normalized_text":
                                   normalize_room_text(
                                       text
                                   ),
                               "x0": span["bbox"][0],
                               "y0": span["bbox"][1],
                               "x1": span["bbox"][2],
                               "y1": span["bbox"][3],
                           }
                       )
           # Exakter Vergleich NACH Normalisierung.
           #
           # Dadurch:
           # MIT 2H302  -> Treffer
           #
           # aber:
           # MIT2H302e -> KEIN Treffer
           room_spans = [
               span
               for span in spans
               if (
                   span["normalized_text"]
                   == normalized_target
               )
           ]
           if not room_spans:
               continue
           found_any_room = True
           print()
           print(
               f"--- Seite {page_number} ---"
           )
           for room_span in room_spans:
               print()
               print("RAUM GEFUNDEN:")
               print(
                   "Originaltext:",
                   repr(
                       room_span["text"]
                   ),
               )
               print(
                   "Normalisiert:",
                   room_span[
                       "normalized_text"
                   ],
               )
               room_x = (
                   room_span["x0"]
                   + room_span["x1"]
               ) / 2
               room_y = (
                   room_span["y0"]
                   + room_span["y1"]
               ) / 2
               print(
                   "Position:",
                   f"x={room_x:.1f}",
                   f"y={room_y:.1f}",
               )
               nearby = []
               for span in spans:
                   span_x = (
                       span["x0"]
                       + span["x1"]
                   ) / 2
                   span_y = (
                       span["y0"]
                       + span["y1"]
                   ) / 2
                   dx = (
                       span_x
                       - room_x
                   )
                   dy = (
                       span_y
                       - room_y
                   )
                   if (
                       abs(dx) <= 220
                       and abs(dy) <= 180
                   ):
                       distance = (
                           abs(dx)
                           + abs(dy)
                       )
                       nearby.append(
                           (
                               distance,
                               dx,
                               dy,
                               span,
                           )
                       )
               nearby.sort(
                   key=lambda item: item[0]
               )
               print()
               print(
                   "TEXT IN DER UMGEBUNG:"
               )
               print()
               for (
                   _,
                   dx,
                   dy,
                   span,
               ) in nearby[:120]:
                   print(
                       f"dx={dx:8.1f} "
                       f"dy={dy:8.1f} | "
                       f"{span['text']}"
                   )
       if not found_any_room:
           print()
           print(
               f"Raum {target_room} "
               "wurde im Schema nicht gefunden."
           )

if __name__ == "__main__":
   main()