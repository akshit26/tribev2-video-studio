"""Manual browser/PDF check against a completed local Studio job."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright
from pypdf import PdfReader
from studio_decision_pdf import decision_html

if __name__ == "__main__":
    job_id = sys.argv[1] if len(sys.argv) > 1 else "e7b8c788b3a8497fbd161c497eaca1fa"
    directory = ROOT / "results/studio" / job_id
    report = json.loads((directory / "report.json").read_text(encoding="utf-8"))
    reader = PdfReader(directory / "report.pdf")
    assert 3 <= len(reader.pages) <= 4
    image_count = sum(len(page.images) for page in reader.pages)
    link_count = sum(a.get_object().get("/Subtype") == "/Link"
                     for page in reader.pages for a in page.get("/Annots", []))
    assert image_count > 0 and link_count == 0
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True, args=["--disable-gpu"])
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:8765/?job={job_id}")
        page.locator("#detailedReview .review-edit").first.wait_for()
        assert page.locator("#overallScore").inner_text() == str(report["review"]["overall_score"])
        assert page.locator("#briefClips video").count() == len(report["brief"]["clips"])
        assert "sensitivity range" in page.locator("#detailedReview").inner_text()
        page.locator("#detailedReview").scroll_into_view_if_needed()
        page.screenshot(path=str(directory / "ui_desktop.png"))
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(directory / "ui_mobile.png"))
        page.set_viewport_size({"width": 840, "height": 1100})
        page.set_content(decision_html(report, directory), wait_until="load")
        assert page.locator("a[href]").count() == 0
        assert page.locator(".screenshots img").count() > 0
        assert page.evaluate("Array.from(document.images).every(i=>i.complete && i.naturalWidth>0)")
        page.locator(".sheet").first.screenshot(path=str(directory / "pdf_overview_preview.png"))
        page.locator(".sheet").nth(2).screenshot(path=str(directory / "pdf_edit_preview.png"))
        browser.close()
    assert not errors, errors
    print(json.dumps({"job": job_id, "pdf_pages": len(reader.pages), "embedded_images": image_count,
                      "pdf_links": link_count, "browser_errors": errors, "mobile_overflow": False}))
