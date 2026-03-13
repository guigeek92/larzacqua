from __future__ import annotations

import os
from io import BytesIO
import logging
from pathlib import Path
import re
import shutil

from pypdf import PdfReader


MIN_TEXT_QUALITY_FOR_OCR_SKIP = 120
logger = logging.getLogger(__name__)


def _postprocess_extracted_text(text: str) -> str:
	"""Normalize common OCR/text-extraction artifacts while preserving content."""
	if not text:
		return ""

	value = text.replace("\r\n", "\n").replace("\r", "\n")
	value = value.replace("\u00a0", " ").replace("\u202f", " ")

	# Re-join words split by hard line breaks (typical OCR artifact).
	value = re.sub(r"([A-Za-zÀ-ÖØ-öø-ÿ])[-‐]\n([A-Za-zÀ-ÖØ-öø-ÿ])", r"\1\2", value)

	unit_rewrites: list[tuple[str, str]] = [
		(r"m\s*[³3]\s*/\s*j(?:our)?", "m3/j"),
		(r"m\s*[³3]\s*/\s*h", "m3/h"),
		(r"m\s*[³3]\s*/\s*s", "m3/s"),
		(r"l\s*/\s*s", "l/s"),
		(r"l\s*/\s*min", "l/min"),
	]
	for pattern, replacement in unit_rewrites:
		value = re.sub(pattern, replacement, value, flags=re.IGNORECASE)

	lines: list[str] = []
	for line in value.split("\n"):
		clean = re.sub(r"[ \t]+", " ", line).strip()
		if clean:
			lines.append(clean)
		else:
			# Keep paragraph boundaries for downstream section parsing.
			if lines and lines[-1] != "":
				lines.append("")

	cleaned = "\n".join(lines)
	cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
	return cleaned.strip()


def _resolve_tesseract_cmd() -> str:
	# Accept either an absolute path or a command name available in PATH.
	env_value = os.getenv("TESSERACT_CMD", "").strip()
	if env_value:
		if Path(env_value).exists():
			return env_value
		from_path = shutil.which(env_value)
		if from_path:
			return from_path

	from_system = shutil.which("tesseract")
	if from_system:
		return from_system

	for candidate in [
		r"C:\Program Files\Tesseract-OCR\tesseract.exe",
		r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
	]:
		if Path(candidate).exists():
			return candidate

	return ""


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
	doc = None
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
		from PIL import Image, ImageFilter, ImageOps  # type: ignore
	except Exception:
		return ""

	tesseract_path = _resolve_tesseract_cmd()
	if not tesseract_path:
		return ""
	pytesseract.pytesseract.tesseract_cmd = tesseract_path

	pages_text: list[str] = []
	doc = None
	try:
		doc = fitz.open(stream=pdf_bytes, filetype="pdf")
		for page in doc:
			best_page_text = ""
			best_page_score = 0
			for angle in [0, 90, 180, 270]:
				matrix = fitz.Matrix(4.0, 4.0).prerotate(angle)
				pix = page.get_pixmap(matrix=matrix, alpha=False)
				img = Image.open(BytesIO(pix.tobytes("png"))).convert("L")
				img = ImageOps.autocontrast(img)
				img = img.filter(ImageFilter.MedianFilter(size=3))
				img = img.point(lambda x: 255 if x > 160 else 0)

				text = ""
				text_score = 0
				for lang in ["fra+eng", "eng", None]:
					for config in ["--oem 3 --psm 6", "--oem 3 --psm 11", "--oem 3 --psm 4"]:
						try:
							if lang:
								candidate = pytesseract.image_to_string(img, lang=lang, config=config, timeout=12)
							else:
								candidate = pytesseract.image_to_string(img, config=config, timeout=12)
							candidate_score = _score_text_quality(candidate)
							if candidate_score > text_score:
								text = candidate
								text_score = candidate_score
						except Exception:
							continue

				if text_score > best_page_score:
					best_page_text = text
					best_page_score = text_score
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

	pypdf_score = _score_text_quality(pypdf_text)
	pymupdf_score = _score_text_quality(pymupdf_text)
	best_non_ocr_score = max(pypdf_score, pymupdf_score)
	run_ocr = os.getenv("PDF_PARSER_FORCE_OCR", "").strip().lower() in {"1", "true", "yes", "on"}
	if not run_ocr and best_non_ocr_score < MIN_TEXT_QUALITY_FOR_OCR_SKIP:
		run_ocr = True
		logger.info(
			"PDF OCR enabled due to low text quality (pypdf=%s, pymupdf=%s, threshold=%s)",
			pypdf_score,
			pymupdf_score,
			MIN_TEXT_QUALITY_FOR_OCR_SKIP,
		)
	elif run_ocr:
		logger.info("PDF OCR forced by configuration PDF_PARSER_FORCE_OCR")

	ocr_text = _extract_text_with_ocr(pdf_bytes) if run_ocr else ""
	ocr_score = _score_text_quality(ocr_text) if ocr_text else 0

	candidates = [pypdf_text, pymupdf_text, ocr_text]
	ranked = sorted(candidates, key=_score_text_quality, reverse=True)

	merged_parts: list[str] = []
	for candidate in ranked:
		if not candidate.strip():
			continue
		if any(candidate.strip() in existing for existing in merged_parts):
			continue
		merged_parts.append(candidate.strip())

	merged_text = "\n\n".join(merged_parts)
	final_text = _postprocess_extracted_text(merged_text)
	logger.debug(
		"PDF text extracted (chars=%s, pypdf_score=%s, pymupdf_score=%s, ocr_score=%s)",
		len(final_text),
		pypdf_score,
		pymupdf_score,
		ocr_score,
	)
	return final_text


def extract_text_from_pdf_file(pdf_path: str | Path) -> str:
	"""Extract plain text from a PDF file path."""
	path = Path(pdf_path)
	if not path.exists() or path.suffix.lower() != ".pdf":
		return ""

	return extract_text_from_pdf(path.read_bytes())
