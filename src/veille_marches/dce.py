"""dce.py — récupération et extraction du DCE/CCTP.

Limite connue (validée en étape 0) : sur nukema, le lien `/attachments?uuid=…`
renvoie le shell de la SPA (HTML), pas le binaire ; le téléchargement réel passe
par la plateforme source (megalis, marches-securises, AWS-achat…) qui exige le
plus souvent une **inscription/login**. On tente donc le téléchargement de façon
**best-effort** :

  1. via la session Playwright (cookies SPA) si disponible ;
  2. en HTTP direct sinon.

Si l'on n'obtient pas de binaire exploitable (zip/docx/pdf), on bascule sur le
champ `description` de l'API nukema (riche : ~900–1800 caractères) comme matière
d'analyse. Le service reste utile sans DCE (scrape + filtre + analyse + post).

Extraction de texte : stdlib uniquement (zipfile pour docx, pas de dépendance
lourde). Le PDF n'est pas extrait nativement (pas de dépendance) — on s'appuie
sur le texte docx ou, à défaut, la description.
"""
from __future__ import annotations

import io
import re
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass

from .scraper import BASE, Consultation

_ZIP_MAGIC = b"PK\x03\x04"
_PDF_MAGIC = b"%PDF"


@dataclass
class DceText:
    """Texte technique récupéré pour analyse."""

    text: str
    source: str  # "cctp", "dce-docx", "description", ...
    filename: str | None = None


def _looks_like_html(data: bytes) -> bool:
    head = data[:512].lstrip().lower()
    return head.startswith(b"<!doctype") or head.startswith(b"<html")


def download_attachment(att: dict, fetcher=None, timeout: int = 60) -> bytes | None:
    """Télécharge un attachment best-effort. Retourne None si non binaire utile."""
    lien = att.get("lien") or ""
    if not lien:
        return None
    url = lien if lien.startswith("http") else f"{BASE}{lien}"
    try:
        if fetcher is not None:
            data = fetcher(url)
        else:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0", "Referer": f"{BASE}/"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310
                data = r.read()
    except (urllib.error.HTTPError, urllib.error.URLError, OSError):
        return None
    if not data or _looks_like_html(data):
        return None
    return data


def extract_docx_text(data: bytes) -> str:
    """Extrait le texte d'un .docx (zipfile + word/document.xml) — stdlib."""
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = z.namelist()
        if "word/document.xml" not in names:
            return ""
        xml = z.read("word/document.xml").decode("utf-8", errors="replace")
    # paragraphes / sauts → espaces, puis dépouille les balises
    xml = re.sub(r"</w:p>", "\n", xml)
    text = re.sub(r"<[^>]+>", " ", xml)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def extract_from_zip(data: bytes) -> tuple[str, str | None]:
    """Reçoit un zip de DCE, renvoie (texte, nom_fichier) du meilleur .docx.

    Heuristique : on privilégie un fichier dont le nom contient « CCTP », sinon
    le plus gros .docx.
    """
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        docx = [n for n in z.namelist() if n.lower().endswith(".docx")]
        if not docx:
            return "", None
        cctp = [n for n in docx if "cctp" in n.lower()]
        chosen = cctp[0] if cctp else max(docx, key=lambda n: z.getinfo(n).file_size)
        inner = z.read(chosen)
    return extract_docx_text(inner), chosen


def get_dce_text(consultation: Consultation, fetcher=None, timeout: int = 60) -> DceText:
    """Best-effort : tente CCTP docx → autre docx → zip → sinon description."""
    atts = consultation.attachments or []

    # 1) priorité aux docx (CCTP d'abord), récupérables par stdlib
    def att_sort_key(a: dict) -> tuple:
        label = (a.get("label") or "").lower()
        is_cctp = "cctp" in label
        is_docx = label.endswith(".docx")
        return (not is_cctp, not is_docx, -(a.get("taille") or 0))

    for att in sorted(atts, key=att_sort_key):
        label = (att.get("label") or "")
        data = download_attachment(att, fetcher=fetcher, timeout=timeout)
        if not data:
            continue
        if data[:4] == _ZIP_MAGIC and label.lower().endswith(".docx"):
            try:
                txt = extract_docx_text(data)
                if txt:
                    src = "cctp" if "cctp" in label.lower() else "dce-docx"
                    return DceText(text=txt, source=src, filename=label)
            except zipfile.BadZipFile:
                pass
        elif data[:4] == _ZIP_MAGIC:  # un zip d'archive DCE
            try:
                txt, fname = extract_from_zip(data)
                if txt:
                    return DceText(text=txt, source="dce-zip", filename=fname)
            except zipfile.BadZipFile:
                pass
        # PDF : pas d'extraction native (pas de dépendance lourde) → on ignore

    # 2) repli : la description riche de l'API nukema
    return DceText(text=consultation.description, source="description", filename=None)
