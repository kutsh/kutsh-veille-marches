from veille_marches.dce import extract_docx_text, get_dce_text
from veille_marches.scraper import NukemaScraper


def test_extract_docx_text(cctp_docx_bytes):
    txt = extract_docx_text(cctp_docx_bytes)
    assert "aide a l'instruction" in txt
    assert "GNAU" in txt
    assert "IA d'extraction OBLIGATOIRE" in txt


def test_get_dce_text_uses_attachment(fake_poster, cctp_docx_bytes):
    s = NukemaScraper(poster=fake_poster)
    rennes = next(c for c in s.search("x") if c.id == 3007885)

    def fetcher(url):
        return cctp_docx_bytes if "cctp-uuid" in url else b"<!doctype html>not a file"

    dce = get_dce_text(rennes, fetcher=fetcher)
    assert dce.source == "cctp"
    assert "GNAU" in dce.text


def test_get_dce_text_falls_back_to_description(fake_poster):
    s = NukemaScraper(poster=fake_poster)
    rennes = next(c for c in s.search("x") if c.id == 3007885)

    def fetcher(url):
        return b"<!doctype html><html>SPA shell</html>"  # nukema renvoie le shell

    dce = get_dce_text(rennes, fetcher=fetcher)
    assert dce.source == "description"
    assert "urbanisme" in dce.text.lower()


def test_html_attachment_rejected(fake_poster):
    s = NukemaScraper(poster=fake_poster)
    rennes = next(c for c in s.search("x") if c.id == 3007885)
    from veille_marches.dce import download_attachment

    att = rennes.attachments[0]
    out = download_attachment(att, fetcher=lambda u: b"<!DOCTYPE html><html></html>")
    assert out is None
