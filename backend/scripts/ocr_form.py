"""One-shot OCR of the form pages with Sarvam Document Intelligence.

Usage: python -I backend/scripts/ocr_form.py <pdf> <out_dir> <page,page,...>
Reads SARVAM_API_KEY from .env at the repo root. Costs credits: run sparingly.
"""
import os
import sys
import pymupdf
from sarvamai import SarvamAI

pdf, out_dir, pages = sys.argv[1], sys.argv[2], [int(p) for p in sys.argv[3].split(",")]
env = dict(l.strip().split("=", 1) for l in open(".env", encoding="utf8") if "=" in l and not l.startswith("#"))
os.makedirs(out_dir, exist_ok=True)

src = pymupdf.open(pdf)
sub = pymupdf.open()
for p in pages:
    sub.insert_pdf(src, from_page=p - 1, to_page=p - 1)
subset = os.path.join(out_dir, "form_pages.pdf")
sub.save(subset)

client = SarvamAI(api_subscription_key=env["SARVAM_API_KEY"])
job = client.document_intelligence.create_job(language="hi-IN", output_format="md")
job.upload_file(subset)
job.start()
status = job.wait_until_complete()
print("state:", status.job_state, job.get_page_metrics())
print("saved:", job.download_output(os.path.join(out_dir, "ocr_output.zip")))
