import httpx
import requests
import re
import xml.etree.ElementTree as ET

from datetime import datetime, timedelta
from bs4 import BeautifulSoup

BASE_URL = "https://data.europarl.europa.eu/api/v2"
current_year = datetime.now().year

MONATE = {
    "Januar": 1,
    "Februar": 2,
    "März": 3,
    "April": 4,
    "Mai": 5,
    "Juni": 6,
    "Juli": 7,
    "August": 8,
    "September": 9,
    "Oktober": 10,
    "November": 11,
    "Dezember": 12
}

MONATE_DE = {
    1: "Januar",
    2: "Februar",
    3: "März",
    4: "April",
    5: "Mai",
    6: "Juni",
    7: "Juli",
    8: "August",
    9: "September",
    10: "Oktober",
    11: "November",
    12: "Dezember"
}

WOCHENTAGE = [
    "Montag",
    "Dienstag",
    "Mittwoch",
    "Donnerstag",
    "Freitag",
    "Samstag",
    "Sonntag"
]


async def get_weeks():
    ###
    url = "https://www.europarl.europa.eu/plenary/de/votes.html?tab=votes#banner_session_live"

    response = requests.get(url)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    wochen = []

    for h3 in soup.find_all("h3"):
        woche = h3.get_text(" ", strip=True)

        # Nur Überschriften berücksichtigen, die tatsächlich
        # einen Datumsbereich enthalten
        if " - " not in woche:
            continue

        # Die Woche speichern
        wochen.append({
            "id": len(wochen),
            "woche": woche
        })

    return wochen


async def get_days(week_id):
    ###
    wochen = await get_weeks()

    # Das komplette Dictionary
    woche = wochen[week_id]

    # Nur der String
    wochen_text = woche["woche"]

    # Stadt am Ende entfernen
    wochen_text = re.sub(
        r"\s+(Strassburg|Straßburg|Brüssel|Brussels)$",
        "",
        wochen_text
    )

    match = re.search(
        r"(\w+), (\d+)\. (\w+) (\d{4}) - "
        r"(\w+), (\d+)\. (\w+) (\d{4})",
        wochen_text
    )

    if not match:
        raise ValueError(
            f"Wochenformat konnte nicht erkannt werden: {wochen_text}"
        )

    (
        start_tag,
        start_day,
        start_month,
        start_year,
        end_tag,
        end_day,
        end_month,
        end_year
    ) = match.groups()

    start_date = datetime(
        int(start_year),
        MONATE[start_month],
        int(start_day)
    ).date()

    end_date = datetime(
        int(end_year),
        MONATE[end_month],
        int(end_day)
    ).date()

    result = []

    aktueller_tag = start_date

    while aktueller_tag <= end_date:

        result.append({
            "id": len(result),
            "Tag": (    
                f"{WOCHENTAGE[aktueller_tag.weekday()]}, "
                f"{aktueller_tag.day}. "
                f"{MONATE_DE[aktueller_tag.month]} "
                f"{aktueller_tag.year}"
            ),
            "datum": aktueller_tag.isoformat()
        })

        aktueller_tag += timedelta(days=1)

    return result




async def fetch_rcv_result(identifier: str, date: str):
    ###
    url = (
        f"https://data.europarl.europa.eu/"
        f"distribution/doc/PV-10-{date}-RCV_de.xml"
    )

    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.get(url)
        response.raise_for_status()

    root = ET.fromstring(response.text)

    for result in root.iter("RollCallVote.Result"):
        if result.attrib.get("Identifier") == str(identifier):
            return ET.tostring(result, encoding="unicode")

    return None





#http://localhost:8000/punkte?tag=MTG-PL-2026-06-16
#https://data.europarl.europa.eu/api/v2/meetings/PV-10-2026-06-16/vote-results
