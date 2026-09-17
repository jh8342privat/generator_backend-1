from fastapi import FastAPI, UploadFile, Response, Request, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
import logic as lg
from pydantic import BaseModel
import uvicorn
import asyncio
import httpx
import os
from bs4 import BeautifulSoup  # Sicherstellen, dass BeautifulSoup importiert ist
import europarl_api as ep
from fastapi import UploadFile, File, Form, HTTPException


class BildRequest(BaseModel):
    identifier: str
    tag: str
    titel: str
    format: str = "square"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Exception Handler
# -----------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"Fehler bei {request.url}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"error": "Ein interner Serverfehler ist aufgetreten.", "details": str(exc)}
    )

# -----------------------------
# Async Helferfunktionen
# -----------------------------
@app.get("/wochen")
async def wochen():

    weeks = await ep.get_weeks()


    return {
        "wochen": weeks
    }

@app.get("/tage")
async def get_tage(week_id: int):
    tage = await ep.get_days(week_id)

    return tage

@app.get("/punkte")
async def get_punkte(tag: str):
    try:
        result = await lg.parse_rcv_inhaltsverzeichnis(
            f"https://data.europarl.europa.eu/distribution/doc/PV-10-{tag}-RCV_de.xml",
            tag
        )

        return result or []

    except Exception as e:
        print(f"Keine Abstimmungen für {tag} verfügbar: {e}")
        return []



@app.post("/bild")
async def bild_generieren(body: BildRequest):

    img_path = await lg.process_abstimmung(
        identifier=body.identifier,
        tag=body.tag,
        titel=body.titel,
        format=body.format
    )

    if not img_path:
        raise HTTPException(
            status_code=404,
            detail="Bild konnte nicht generiert werden"
        )

    return FileResponse(
        img_path,
        media_type="image/png"
    )

@app.post("/manuell/abstimmungen")
async def manuelle_abstimmungen(
    file: UploadFile = File(...)
):
    if not file.filename.lower().endswith(".xml"):
        raise HTTPException(
            status_code=400,
            detail="Bitte eine XML-Datei hochladen."
        )

    try:
        xml_content = await file.read()

        abstimmungen = lg.parse_rcv_inhaltsverzeichnis_xml(
            xml_content
        )

        return abstimmungen

    except Exception as e:
        print(f"Fehler beim Lesen der XML: {e}")

        raise HTTPException(
            status_code=400,
            detail=f"XML-Datei konnte nicht verarbeitet werden: {e}"
        )

@app.post("/bild-manual")
async def bild_manual(
    identifier: str = Form(...),
    titel: str = Form(""),
    format: str = Form("square"),
    file: UploadFile = File(...)
):

    try:
        xml_content = await file.read()

        img_path = await lg.process_abstimmung_from_xml(
            identifier=identifier,
            xml_content=xml_content,
            titel=titel,
            format=format
        )

        if not img_path:
            raise HTTPException(
                status_code=404,
                detail="Bild konnte nicht generiert werden"
            )

        return FileResponse(
            img_path,
            media_type="image/png"
        )

    except HTTPException:
        raise

    except Exception as e:
        print(f"Fehler bei manueller Bildgenerierung: {e}")

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )
# -----------------------------
# Server starten
# -----------------------------
if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8001)),
        log_level="info"
    )
