from __future__ import annotations

import os
from io import BytesIO
from pathlib import Path
import re
import shutil

from pypdf import PdfReader


MIN_TEXT_QUALITY_FOR_OCR_SKIP = 120


def _score_text_quality(text: str) -> int:
	if not text:
		return 0
	lower = text.lower()
	score = 0
	score += len(text) // 200
	score += len(re.findall(r"\d", text))
	for keyword in [
		"udi",
		"steu",
		"debit",
		"débit",
		"m3/j",
		"m³/j",
		"m3/h",
		"m³/h",
		"l/s",
		"pression",
		"brise-charge",
		"ouvrage",
		"ngf",
		"source",
		"reservoir",
		"réservoir",
		"adduction",
	]:
		score += lower.count(keyword) * 20
	return score


def _extract_text_with_pypdf(pdf_bytes: bytes) -> str:
	reader = PdfReader(BytesIO(pdf_bytes))
	pages_text: list[str] = []
	for page in reader.pages:
		text_standard = (page.extract_text() or "").strip()
		text_layout = ""
		try:
			text_layout = (page.extract_text(extraction_mode="layout") or "").strip()
		except TypeError:
			text_layout = ""

		if text_standard and text_layout and text_standard != text_layout:
			combined_text = f"{text_standard}\n\n{text_layout}"
		else:
			combined_text = text_standard or text_layout

		pages_text.append(combined_text)

	return "\n\n".join(chunk for chunk in pages_text if chunk)


def _extract_text_with_pymupdf(pdf_bytes: bytes) -> str:
	try:
		import fitz  # type: ignore
	except Exception:
		return ""

	pages_text: list[str] = []
	try:
		doc = fitz.open(stream=pdf_bytes, filetype="pdf")
		for page in doc:
			text = (page.get_text("text", sort=True) or "").strip()
			if text:
				pages_text.append(text)
	finally:
		try:
			doc.close()
		except Exception:
			pass

	return "\n\n".join(pages_text)


def _extract_text_with_ocr(pdf_bytes: bytes) -> str:
	try:
		import fitz  # type: ignore
		import pytesseract  # type: ignore
		from PIL import Image  # type: ignore
	except Exception:
		return ""

	tesseract_path = os.getenv("TESSERACT_CMD", "").strip()
	if not tesseract_path:
		system_tesseract = shutil.which("tesseract")
		if system_tesseract:
			tesseract_path = system_tesseract
	if not tesseract_path:
		default_paths = [
			r"C:\Program Files\Tesseract-OCR\tesseract.exe",
			r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
		]
		for candidate in default_paths:
			if Path(candidate).exists():
				tesseract_path = candidate
				break
	if not tesseract_path or not Path(tesseract_path).exists():
		return ""
	if tesseract_path:
		pytesseract.pytesseract.tesseract_cmd = tesseract_path

	pages_text: list[str] = []
	try:
		doc = fitz.open(stream=pdf_bytes, filetype="pdf")
		for page in doc:
			best_page_text = ""
			for angle in [0, 90, 180, 270]:
				matrix = fitz.Matrix(4.0, 4.0).prerotate(angle)
				pix = page.get_pixmap(matrix=matrix, alpha=False)
				img = Image.open(BytesIO(pix.tobytes("png"))).convert("L")

				text = ""
				for lang in ["fra+eng", "eng", None]:
					for config in ["--oem 3 --psm 6", "--oem 3 --psm 11", "--oem 1 --psm 6"]:
						try:
							if lang:
								candidate = pytesseract.image_to_string(img, lang=lang, config=config)
							else:
								candidate = pytesseract.image_to_string(img, config=config)
							if _score_text_quality(candidate) > _score_text_quality(text):
								text = candidate
						except Exception:
							continue

				if _score_text_quality(text) > _score_text_quality(best_page_text):
					best_page_text = text
			if best_page_text.strip():
				pages_text.append(best_page_text.strip())
	finally:
		try:
			doc.close()
		except Exception:
			pass

	return "\n\n".join(pages_text)


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
	"""Extract plain text from a PDF binary payload."""
	if not pdf_bytes:
		return ""

	pypdf_text = _extract_text_with_pypdf(pdf_bytes)
	pymupdf_text = _extract_text_with_pymupdf(pdf_bytes)

	best_non_ocr_score = max(_score_text_quality(pypdf_text), _score_text_quality(pymupdf_text))
	run_ocr = os.getenv("PDF_PARSER_FORCE_OCR", "").strip().lower() in {"1", "true", "yes", "on"}
	if not run_ocr and best_non_ocr_score < MIN_TEXT_QUALITY_FOR_OCR_SKIP:
		run_ocr = True

	ocr_text = _extract_text_with_ocr(pdf_bytes) if run_ocr else ""

	candidates = [pypdf_text, pymupdf_text, ocr_text]
	ranked = sorted(candidates, key=_score_text_quality, reverse=True)

	merged_parts: list[str] = []
	for candidate in ranked:
		if not candidate.strip():
			continue
		if any(candidate.strip() in existing for existing in merged_parts):
			continue
		merged_parts.append(candidate.strip())

	return "\n\n".join(merged_parts)


def extract_text_from_pdf_file(pdf_path: str | Path) -> str:
	"""Extract plain text from a PDF file path."""
	path = Path(pdf_path)
	if not path.exists() or path.suffix.lower() != ".pdf":
		return ""

	return extract_text_from_pdf(path.read_bytes())
