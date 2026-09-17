import requests
from bs4 import BeautifulSoup
from collections import defaultdict
import xml.etree.ElementTree as ET
import os
import math
from PIL import Image, ImageDraw, ImageFont
from typing import Optional, Tuple
import europarl_api as ep
import httpx
from collections import OrderedDict
BASE_URL = "https://data.europarl.europa.eu/api/v2"


MAX_WIDTH = 70
COLUMN_COUNT = 4
PADDING = 12
LINE_HEIGHT = 35
ICON_SIZE = 32
REC_SIZE = 10
FONT_PATH = "PTSansProCondRg.OTF"  # oder "arial.ttf"
FONT2 = "PTSansProXBd.OTF"
FONT_SIZE = 28
FONT_SIZE2 = 42
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # Pfad zum backend-Ordner
LOGO_PATH = os.path.join(BASE_DIR, "logos") 
COL_WIDTH = 270

COLOR_MAP = {
    "ja": "green",
    "nein": "red",
    "enthaltung": "orange",
    "nicht_abgestimmt": "grey"
}


# URL der Webseite, die du auslesen willst
url = 'https://www.europarl.europa.eu/plenary/en/votes.html?tab=votes#banner_session_live'  # ← Ersetze das mit deiner Ziel-URL


parteireihenfolge = [
            "Grune", "CDU", "CSU", "AfD", "SPD", "FDP",
            "Linke", "fw", 'BSW', "Volt", "Die Partei", "Piratenpartei",
            "ODP", "Tierschutzpartei", "Sonstige"
        ]

FRANKTIONSKÜRZEL = {
    "Fraktion der Progressiven Allianz der Sozialdemokraten im Europäischen Parlament": "S&D",
    "Fraktion Renew Europe": "Renew",
    "Fraktion der Europäischen Volkspartei (Christdemokraten)": "PPE",
    "Fraktion Patrioten für Europa": "PfE",
    "Fraktion der Europäischen Konservativen und Reformer": "ECR",
    "Fraktion Europa der Souveränen Nationen": "ESN",
    "Fraktion Die Linke im Europäischen Parlament - GUE/NGL": "The Left",
    "Fraktion der Grünen / Freie Europäische Allianz": "Verts/ALE",
    "Fraktionslos": "NI"
}

PARTEI_ABKÜRZUNGEN = {
    "Bündnis 90/Die Grünen": "Grune",
    "Sozialdemokratische Partei Deutschlands": "SPD",
    "Christlich Demokratische Union Deutschlands": "CDU",
    "Christlich-Soziale Union in Bayern e.V.": "CSU",
    "Freie Demokratische Partei": "FDP",
    "DIE LINKE.": "Linke",
    "Alternative für Deutschland": "AfD",
    'Partei Mensch Umwelt Tierschutz': 'Tierschutz',
    'Bündnis Sahra Wagenknecht – Vernunft und Gerechtigkeit': 'BSW',
    'Die PARTEI': 'Die Partei',
    'Freie Wähler': 'fw',
    'Ökologisch-Demokratische Partei': "ODP",
    'Familien-Partei Deutschlands': 'Familien Partei',
    'Partei des Fortschritts': 'PDF'
}

def parse_vote_result(xml_content):
    root = ET.fromstring(xml_content)

    description = root.findtext("RollCallVote.Description.Text")

    if not description:
        description = ""

    vote_result = defaultdict(list)

    for result_type in ["For", "Against", "Abstention"]:
        result_tag = root.find(f"./Result.{result_type}")

        if result_tag is None:
            continue

        for group in result_tag.findall("Result.PoliticalGroup.List"):
            group_id = group.attrib.get("Identifier")

            for member in group.findall("PoliticalGroup.Member.Name"):
                name = (member.text or "").strip()
                pers_id = member.attrib.get("PersId")
                mep_id = member.attrib.get("MepId")

                vote_result[result_type].append({
                    "name": name,
                    "id": pers_id,
                    "mep_id": mep_id,
                    "group": group_id
                })

    # Sonderfälle / korrigierte Abstimmungsabsichten
    intentions = root.find("Intentions")

    if intentions is not None:
        for intention_result_type in [
            "For",
            "Against",
            "Abstention"
        ]:
            intention_tag = intentions.find(
                f"Intentions.Result.{intention_result_type}"
            )

            if intention_tag is None:
                continue

            for member in intention_tag.findall("Member.Name"):
                name = (member.text or "").strip()
                pers_id = member.attrib.get("PersId")
                mep_id = member.attrib.get("MepId")

                # MEP aus allen bisherigen Kategorien entfernen
                for key in vote_result:
                    vote_result[key] = [
                        m
                        for m in vote_result[key]
                        if m["id"] != pers_id
                    ]

                # MEP in die korrigierte Kategorie einfügen
                vote_result[intention_result_type].append({
                    "name": name,
                    "id": pers_id,
                    "mep_id": mep_id
                })

    return {
        "identifier": root.attrib.get("Identifier"),
        "dlv_id": root.attrib.get("DlvId"),
        "date": root.attrib.get("Date"),
        "description": description.strip(),
        "results": dict(vote_result)
    }

def parse_meps_from_url(xml_url):
    response = requests.get(xml_url)
    response.raise_for_status()
    xml_content = response.content

    root = ET.fromstring(xml_content)
    mep_dict = {}

    for mep in root.findall(".//mep"):
        mep_id = mep.findtext("id")
        full_name = mep.findtext("fullName", "").strip()
        political_group = mep.findtext("politicalGroup", "").strip()
        national_group = mep.findtext("nationalPoliticalGroup", "").strip()

        mep_dict[mep_id] = {
            "full_name": full_name,
            "political_group": political_group,
            "national_political_group": national_group
        }

    return mep_dict

def normalize_partei(name):
    return PARTEI_ABKÜRZUNGEN.get(name, name)

def verarbeite_deutsche_abstimmung(abstimmung, deutsche_meps, parteireihenfolge, titel):

    result = {
        "titel_abstimmung": titel,
        "For": [],
        "Against": [],
        "Abstention": [],
        "not_voted": []
    }

    gewertete_ids = set()

    # Die drei Abstimmungskategorien durchgehen
    for entscheidung in ["For", "Against", "Abstention"]:
        for abgeordneter in abstimmung.get("results", {}).get(entscheidung, []):

            mep_id = abgeordneter.get("id")

            # Nur deutsche MEPs berücksichtigen
            if mep_id not in deutsche_meps:
                continue

            info = deutsche_meps[mep_id]

            national_party = normalize_partei(
                info["national_political_group"]
            )

            # Vor- und Nachnamen bestimmen
            parts = info["full_name"].split()

            nachnamen_teile = [
                teil.capitalize()
                for teil in parts
                if teil.isupper()
            ]

            vornamen_teile = [
                teil.capitalize()
                for teil in parts
                if not teil.isupper()
            ]

            if not nachnamen_teile:
                nachname = parts[-1]
                vorname = " ".join(parts[:-1])
            else:
                nachname = " ".join(nachnamen_teile)
                vorname = " ".join(vornamen_teile)

            if nachname == "Strack-zimmermann":
                nachname = "Strack-Zimmermann"

            result[entscheidung].append({
                "name": nachname,
                "vorname": vorname,
                "partei": national_party,
                "political_group": info["political_group"]
            })

            gewertete_ids.add(mep_id)

    # Deutsche MEPs bestimmen, die nicht in der Abstimmung vorkommen
    for mep_id, info in deutsche_meps.items():

        if mep_id in gewertete_ids:
            continue

        national_party = normalize_partei(
            info["national_political_group"]
        )

        parts = info["full_name"].split()

        nachnamen_teile = [
            teil.capitalize()
            for teil in parts
            if teil.isupper()
        ]

        vornamen_teile = [
            teil.capitalize()
            for teil in parts
            if not teil.isupper()
        ]

        if not nachnamen_teile:
            nachname = parts[-1]
            vorname = " ".join(parts[:-1])
        else:
            nachname = " ".join(nachnamen_teile)
            vorname = " ".join(vornamen_teile)

        if nachname == "Strack-zimmermann":
            nachname = "Strack-Zimmermann"

        result["not_voted"].append({
            "name": nachname,
            "vorname": vorname,
            "partei": national_party,
            "political_group": info["political_group"]
        })

    # Nach Partei und anschließend Nachname sortieren
    def sort_key(mep):
        partei_index = (
            parteireihenfolge.index(mep["partei"])
            if mep["partei"] in parteireihenfolge
            else len(parteireihenfolge)
        )

        return (
            partei_index,
            mep["name"].lower()
        )

    for entscheidung in ["For", "Against", "Abstention", "not_voted"]:
        result[entscheidung].sort(key=sort_key)

    return result

def draw_block(img, draw, persons, label, y_offset, icon_color, font, font2, font3, logos):
    draw.rectangle([PADDING, y_offset - 2, PADDING + 10, y_offset + ICON_SIZE ], fill=icon_color)
    draw.text((PADDING + REC_SIZE + 13, y_offset), label, fill=icon_color, font=font2)
    
    #y_offset += LINE_HEIGHT
    persons.insert(0, {'name': '', 'vorname': '', 'partei': ''}) 
    rows = math.ceil(len(persons) / COLUMN_COUNT)


    for col in range(COLUMN_COUNT):
            for row in range(rows):

                index = row + rows * col 
                if index >= len(persons):
                    continue
                person = persons[index]

                if index == 0:
                    name = ''
                else:
                    name = f"{person['name']} {person['vorname'][0]}."
                if True:
                    if person['name'] == "Von Der Schulenburg":
                        name = "v. d. Schulenburg M."
                    
                    if person['name'] == "Strack-Zimmermann":
                        name = "Strack-Zimmermann M.-A."
                    
                    if person['name'] == "Warnke":
                        name = "Warnke J.-P."
                    
                    if person['name'] == "Oetjen":
                        name = "Oetjen J.-C."
                logo = logos.get(person["partei"], None)

                x = PADDING + col * COL_WIDTH
                y = y_offset + row * LINE_HEIGHT

                    # Rechteck (Zustimmungsindikator)
                draw.rectangle([x, y -2, x + 10, y + ICON_SIZE + 2], fill=icon_color)

                    # Text
                if name == "Strack-Zimmermann M.-A.":
                    draw.text((x + REC_SIZE + 13, y+3), name, fill="black", font=font3)
                else:
                    draw.text((x + REC_SIZE + 13, y), name, fill="black", font=font)

                    # Logo
                if logo:
                    img.paste(logo, (x + REC_SIZE + 250 - logo.width, y), logo)

    return y_offset + rows * LINE_HEIGHT + LINE_HEIGHT

def load_logos():
    logos = {}
    for fname in os.listdir(LOGO_PATH):
        if fname.endswith(".png"):
            partei = fname.replace(".png", "")


            original_logo = Image.open(os.path.join(LOGO_PATH, fname)).convert("RGBA")
            # Calculate aspect ratio
            aspect_ratio = original_logo.width / original_logo.height
            new_width = int(ICON_SIZE * aspect_ratio)

            # Resize while preserving proportions
            logo = original_logo.resize((new_width, ICON_SIZE), Image.LANCZOS)

            # If it exceeds max width, scale it down again
            if logo.width > MAX_WIDTH:
                scale_ratio = MAX_WIDTH / logo.width
                new_width = MAX_WIDTH
                new_height = int(logo.height * scale_ratio)
                logo = logo.resize((new_width, new_height), Image.LANCZOS)
            
            logos[partei] = logo
    return logos

def wrap_text(text, font, max_width, draw):
    lines = []
    words = text.split()
    line = ""

    for word in words:
        test_line = line + word + " "
        bbox = font.getbbox(test_line)
        width = bbox[2] - bbox[0]

        if width <= max_width:
            line = test_line
        else:
            lines.append(line.strip())
            line = word + " "

    if line:
        lines.append(line.strip())

    return lines

def generate_image(data, output_path="sharepic.png", format="square"):
    # ---------------------------------------------------------
    # Bildformat bestimmen
    # ---------------------------------------------------------

    if format == "square":
        width = 1200
        estimated_height = 1200

    elif format == "portrait":
        width = 1200
        estimated_height = 1500

    else:
        raise ValueError(
            f"Unbekanntes Format: {format}"
        )

    # ---------------------------------------------------------
    # Schriftgrößen
    # ---------------------------------------------------------

    size_temp = 28

    try:
        font_temp = ImageFont.truetype(
            FONT_PATH,
            size_temp
        )

        font_block = ImageFont.truetype(
            FONT_PATH,
            FONT_SIZE
        )

        font_block2 = ImageFont.truetype(
            FONT2,
            round(FONT_SIZE * 0.9)
        )

        font_block3 = ImageFont.truetype(
            FONT_PATH,
            round(FONT_SIZE * 0.8)
        )

        font_title = ImageFont.truetype(
            FONT2,
            42
        )

    except Exception as e:
        print(f"Font loading error: {e}")
        print(f"BASE_DIR: {BASE_DIR}")
        print(
            f"FONT_PATH exists: "
            f"{os.path.exists(FONT_PATH)}"
        )
        raise

    # ---------------------------------------------------------
    # Logos
    # ---------------------------------------------------------

    logos = load_logos()

    # ---------------------------------------------------------
    # Bild erzeugen
    # ---------------------------------------------------------

    img = Image.new(
        "RGBA",
        (width, estimated_height),
        "white"
    )

    draw = ImageDraw.Draw(img)

    # ---------------------------------------------------------
    # Überschrift
    # ---------------------------------------------------------

    title = data.get("title", "")

    y = 40

    if title.strip():
        wrapped_lines = wrap_text(
            title,
            font_title,
            img.width - 80,
            draw
        )

        for line in wrapped_lines:
            bbox = draw.textbbox(
                (0, 0),
                line,
                font=font_title
            )

            line_width = bbox[2] - bbox[0]

            x = (
                img.width - line_width
            ) // 2

            draw.text(
                (x, y),
                line,
                fill="black",
                font=font_title
            )

            y += 50

        # zusätzlicher Abstand
        # zwischen Überschrift und erstem Block
        y += 45

    else:
        # Wenn kein Titel vorhanden ist,
        # trotzdem etwas Abstand oben lassen
        y += 20

    # ---------------------------------------------------------
    # Abstimmungsblöcke
    # ---------------------------------------------------------

    y = draw_block(
        img,
        draw,
        data["ja"],
        "DAFÜR",
        y,
        COLOR_MAP["ja"],
        font_block,
        font_block2,
        font_block3,
        logos
    )

    y = draw_block(
        img,
        draw,
        data["nein"],
        "DAGEGEN",
        y,
        COLOR_MAP["nein"],
        font_block,
        font_block2,
        font_block3,
        logos
    )

    y = draw_block(
        img,
        draw,
        data["enthaltung"],
        "ENTHALTEN",
        y,
        COLOR_MAP["enthaltung"],
        font_block,
        font_block2,
        font_block3,
        logos
    )

    y = draw_block(
        img,
        draw,
        data["nicht_abgestimmt"],
        "NICHT ABGESTIMMT",
        y,
        COLOR_MAP["nicht_abgestimmt"],
        font_block,
        font_block2,
        font_block3,
        logos
    )

    # ---------------------------------------------------------
    # Bild beschneiden
    # ---------------------------------------------------------

    img = img.crop(
        (0, 0, img.width, y + 50)
    )

    # ---------------------------------------------------------
    # GreensEFA Logo unten rechts
    # ---------------------------------------------------------

    logo_path = os.path.join(
        LOGO_PATH,
        "GreensEFA.png"
    )

    if os.path.exists(logo_path):

        bottom_logo = Image.open(
            logo_path
        ).convert("RGBA")

        logo_width = 100

        aspect_ratio = (
            bottom_logo.height
            / bottom_logo.width
        )

        logo_height = int(
            logo_width * aspect_ratio
        )

        bottom_logo = bottom_logo.resize(
            (
                logo_width,
                logo_height
            ),
            Image.LANCZOS
        )

        x_pos = (
            img.width
            - logo_width
            - 80
        )

        y_pos = (
            img.height
            - logo_height
            - 18
        )

        img.paste(
            bottom_logo,
            (x_pos, y_pos),
            bottom_logo
        )

    # ---------------------------------------------------------
    # Speichern
    # ---------------------------------------------------------

    img.save(output_path)

def übersetze_keys(abstimmungs_dict):
    key_mapping = {
        "titel_abstimmung": "title",
        "For": "ja",
        "Against": "nein",
        "Abstention": "enthaltung",
        "not_voted": "nicht_abgestimmt"
    }

    return {
        key_mapping.get(k, k): v for k, v in abstimmungs_dict.items()
    }

async def parse_rcv_inhaltsverzeichnis(url: str, date: str):
    ###
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.get(url)
        response.raise_for_status()

    root = ET.fromstring(response.text)

    # =========================================================
    # 2. Vote-Results des Tages aus der API laden
    # =========================================================

    sitting_id = f"MTG-PL-{date}"

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.get(
            f"{BASE_URL}/meetings/{sitting_id}/vote-results",
            headers={
                "Accept": "application/ld+json"
            }
        )

        response.raise_for_status()

    vote_results = response.json()["data"]

    # =========================================================
    # 3. DlvId -> API-Vote
    # =========================================================

    vote_by_dlv_id = {
        vote.get("notation_dlvId"): vote
        for vote in vote_results
        if vote.get("notation_dlvId")
    }

    # =========================================================
    # 4. RCVs aus XML gruppieren
    # =========================================================

    abstimmungen = OrderedDict()

    for result in root.iter("RollCallVote.Result"):

        dlv_id = result.attrib.get("DlvId")
        identifier = result.attrib.get("Identifier")
        result_date = result.attrib.get("Date")

        description = result.findtext(
            "RollCallVote.Description.Text",
            default=""
        ).strip()

        if not dlv_id or not description:
            continue

        # -----------------------------------------------------
        # Abstimmungsobjekt erstmalig anlegen
        # -----------------------------------------------------

        if dlv_id not in abstimmungen:

            api_vote = vote_by_dlv_id.get(dlv_id)

            titel = None
            vote_id = None
            dokument_id = None

            if api_vote:

                vote_id = api_vote.get("activity_id")

                # Zugehöriges Dokument
                references = api_vote.get(
                    "based_on_a_realization_of",
                    []
                )

                if references:
                    dokument_id = references[0].split("/")[-1]

                # Titel des übergeordneten Abstimmungsobjekts
                #
                # Wir verwenden dafür den activity_label
                # des Vote-Results, NICHT den RCV-Description-Text.
                titel = (
                    api_vote.get("activity_label", {})
                    .get("de")
                )

            # Fallback, falls API keinen Titel liefert
            if not titel:
                titel = description.split(" – ")[0].strip()

            abstimmungen[dlv_id] = {
                "titel": titel,
                "dlv_id": dlv_id,
                "vote_id": vote_id,
                "dokument_id": dokument_id,
                "unterabstimmungen": []
            }

        # -----------------------------------------------------
        # Unterabstimmung hinzufügen
        # -----------------------------------------------------

        abstimmungen[dlv_id]["unterabstimmungen"].append({
            "titel": description,
            "identifier": identifier,
            "date": result_date
        })

    # =========================================================
    # 5. Liste zurückgeben
    # =========================================================

    return list(abstimmungen.values())

async def process_abstimmung(identifier, tag, titel, format):
    ###
    # RCV anhand des Identifiers holen
    xml_content = await ep.fetch_rcv_result(
        identifier,
        tag
    )

    if not xml_content:
        raise ValueError(
            f"Keine Abstimmung mit Identifier {identifier} gefunden."
        )

    vote_results = parse_vote_result(xml_content)

    mep_link = (
        "https://www.europarl.europa.eu/"
        "meps/de/download/advanced/xml?countryCode=DE"
    )

    mep_dict = parse_meps_from_url(mep_link)

    ergebnis = verarbeite_deutsche_abstimmung(
        abstimmung=vote_results,
        deutsche_meps=mep_dict,
        parteireihenfolge=parteireihenfolge,
        titel=titel
    )

    auswertung = übersetze_keys(ergebnis)

    generate_image(
        auswertung,
        "sharepic.png",
        format=format
    )

    return "sharepic.png"

def parse_rcv_inhaltsverzeichnis_xml(xml_content: bytes):
    """
    Liest eine hochgeladene RCV-XML-Datei und gruppiert
    alle RollCallVote.Result nach DlvId.
    """

    root = ET.fromstring(xml_content)

    abstimmungen = OrderedDict()

    for result in root.iter("RollCallVote.Result"):

        dlv_id = result.attrib.get("DlvId")
        identifier = result.attrib.get("Identifier")
        result_date = result.attrib.get("Date")

        description = result.findtext(
            "RollCallVote.Description.Text",
            default=""
        ).strip()

        if not dlv_id or not description:
            continue

        # Titel des übergeordneten Abstimmungsobjekts
        titel = description.split(" – ")[0].strip()

        if dlv_id not in abstimmungen:
            abstimmungen[dlv_id] = {
                "titel": titel,
                "dlv_id": dlv_id,
                "unterabstimmungen": []
            }

        abstimmungen[dlv_id]["unterabstimmungen"].append({
            "titel": description,
            "identifier": identifier,
            "date": result_date
        })

    return list(abstimmungen.values())

async def process_abstimmung_from_xml(
    identifier,
    xml_content,
    titel,
    format="square"
):
    # Gewünschtes RCV aus der hochgeladenen XML suchen
    root = ET.fromstring(xml_content)

    xml_result = None

    for result in root.iter("RollCallVote.Result"):
        if result.attrib.get("Identifier") == str(identifier):
            xml_result = ET.tostring(
                result,
                encoding="unicode"
            )
            break

    if not xml_result:
        raise ValueError(
            f"Keine Abstimmung mit Identifier "
            f"{identifier} in der XML gefunden."
        )

    vote_results = parse_vote_result(xml_result)

    mep_link = (
        "https://www.europarl.europa.eu/"
        "meps/de/download/advanced/xml?countryCode=DE"
    )

    mep_dict = parse_meps_from_url(mep_link)

    ergebnis = verarbeite_deutsche_abstimmung(
        abstimmung=vote_results,
        deutsche_meps=mep_dict,
        parteireihenfolge=parteireihenfolge,
        titel=titel
    )

    auswertung = übersetze_keys(ergebnis)

    generate_image(
        auswertung,
        "sharepic.png",
        format=format
    )

    return "sharepic.png"
