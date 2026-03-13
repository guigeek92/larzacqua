from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from groq import Groq
from src.pdf_parser import _resolve_tesseract_cmd, extract_text_from_pdf
from src.infrastructure_mapper import build_infrastructure_graph, update_udi_fields_from_detections
from src.symbol_detection import detect_symbols_from_template_bank

load_dotenv()

HYDRO_MIN_FLOW_M3_J = float(os.getenv("HYDRO_MIN_FLOW_M3_J", "50"))
MAX_PLAUSIBLE_HEAD_M = float(os.getenv("HYDRO_MAX_HEAD_M", "150"))

ALLOWED_MODELS = [
	"llama-3.1-8b-instant",
	"llama-3.3-70b-versatile",
	"openai/gpt-oss-20b",
	"openai/gpt-oss-120b",
]

logger = logging.getLogger(__name__)

UDI_REDUCER_TOKEN_PATTERN = r"(?:\br\s*\.?\s*p\b|\bp\s*\.?\s*r\s*\.?\s*v\b|\bprv\b)"
UDI_REDUCER_PHRASE_PATTERN = r"reducteur\s+de\s+pression|regulateur\s+de\s+pression|chambre\s+de\s+reduction"
UDI_REDUCER_ABBREV_STRICT_PATTERN = r"(?<![a-z0-9])(?:r[\s.\-_/]*p|p[\s.\-_/]*r[\s.\-_/]*v)(?![a-z0-9])"
UDI_REDUCER_CONTEXT_PATTERN = r"pression|reduct|regulat|chambre\s+de\s+reduction|legende|symbole"
UDI_REDUCER_PATTERN = rf"{UDI_REDUCER_PHRASE_PATTERN}|{UDI_REDUCER_TOKEN_PATTERN}"
UDI_BRISE_CHARGE_PATTERN = r"brise[-\s]?charge"
UDI_BRISE_CHARGE_LEGEND_PATTERN = r"brise[-\s]?charge|\bb\s*\.?\s*c\b|\bbc\b"
# Keep explicit references for the two legend images used in this project.
# `Image1.png` is kept as a backward-compatible alias for `legende 1`.
LEGEND_REFERENCE_FILES = (
	"legende 1.JPG",
	"legende 2.JPG",
	"Image1.png",
)


def _count_reducer_mentions(document_text: str) -> int:
	"""Count reducer mentions with precision-first rules to avoid OCR random false positives."""
	text = (document_text or "").replace("\r\n", "\n")
	norm_text = _normalize_for_search(text)
	strong_count = len(re.findall(UDI_REDUCER_PHRASE_PATTERN, norm_text, flags=re.IGNORECASE))

	contextual_abbrev_count = 0
	for raw_line in text.split("\n"):
		line = _clean_spaces(raw_line)
		if not line:
			continue
		line_norm = _normalize_for_search(line)
		if not re.search(UDI_REDUCER_ABBREV_STRICT_PATTERN, line_norm, re.IGNORECASE):
			continue
		if re.search(UDI_REDUCER_CONTEXT_PATTERN, line_norm, re.IGNORECASE):
			contextual_abbrev_count += len(re.findall(UDI_REDUCER_ABBREV_STRICT_PATTERN, line_norm, flags=re.IGNORECASE))

	return strong_count + contextual_abbrev_count


def _detect_document_type(document_text: str) -> str:
	text = _clean_spaces(document_text).lower()

	steu_indicators = [
		"steu",
		"capacité eh",
		"capacite eh",
		"filière eau",
		"filiere eau",
		"charges de référence",
		"satese",
	]
	udi_indicators = [
		"udi",
		"aep",
		"eau potable",
		"synoptique",
		"schema hydraulique",
		"schéma hydraulique",
		"chambre de vannes",
		"regulateur de pression",
		"régulateur de pression",
		"prv",
		"brise-charge",
		"brise charge",
		"réducteur de pression",
		"reducteur de pression",
		"chambre de réduction",
		"chambre de reduction",
		"adduction",
		"réservoir",
		"reservoir",
	]

	steu_score = sum(1 for token in steu_indicators if token in text)
	udi_score = sum(1 for token in udi_indicators if token in text)

	if udi_score > steu_score:
		return "udi"
	return "steu"


def _json_schema_template() -> dict[str, Any]:
	return {
		"nom_station": "",
		"commune": "",
		"capacite_eh": None,
		"annee_mise_service": None,
		"coordonnees": "",
		"surface_infiltration_m2": None,
		"nombre_casiers": None,
		"nombre_drains": None,
		"debit_m3_j": None,
		"ouvrages": [],
		"potentiel_hydraulique": None,
		"surface_potentielle_solaire_m2": None,
	}


def _udi_json_schema_template() -> dict[str, Any]:
	return {
		"nom_udi": "",
		"communes": [],
		"localisation": "",
		"sites_udi": [],
		"reservoirs_udi": [],
		"description_reservoirs": [],
		"presence_brise_charge": None,
		"nombre_brise_charge": None,
		"presence_reducteurs_pression": None,
		"nombre_reducteurs_pression": None,
		"hauteur_chute_estimee_m": None,
		"denivele_source_reservoir_m": None,
		"denivele_estime_m": None,
		"altitudes_ngf_m": [],
		"volume_reservoir_m3": None,
		"volume_reservoir_confidence": "low",
		"volume_reservoir_confidence_by_site": [],
		"volume_reference_m3_j": None,
		"debit_m3_j": None,
		"points_pression_reduction": [],
		"emplacements_turbine_potentiels": [],
		"elements_interessants_micro_hydro": [],
		"contraintes_techniques": [],
		"potentiel_hydraulique": None,
	}


def _extract_udi_legend_signals(document_text: str) -> dict[str, Any]:
	text = (document_text or "").replace("\r\n", "\n")
	norm = _normalize_for_search(text)
	lines = [_clean_spaces(line) for line in text.split("\n") if _clean_spaces(line)]

	reservoir_description_lines: list[str] = []
	for line in lines:
		line_norm = _normalize_for_search(line)
		if "legende" in line_norm:
			continue
		if not re.search(r"\breservoir\b|\br[ée]servoir\b", line_norm, re.IGNORECASE):
			continue
		if len(line) < 6:
			continue
		if line not in reservoir_description_lines:
			reservoir_description_lines.append(line)
		if len(reservoir_description_lines) >= 10:
			break

	feature_patterns: list[tuple[str, str]] = [
		(UDI_REDUCER_PATTERN, "Réduction de pression (RP/PRV)"),
		(r"brise[-\s]?charge", "Brise-charge"),
		(r"adduction\s*-?\s*gravitaire", "Adduction gravitaire"),
		(r"distribution\s*-?\s*gravitaire", "Distribution gravitaire"),
		(r"distribution\s*-?\s*refoulement|pompage\s+en\s+ligne|\bpompe\b", "Refoulement / pompage"),
		(r"manometre|manom[eè]tre", "Mesure pression (manomètre)"),
		(r"compteur", "Point de comptage (compteur)"),
		(r"vanne\s+ouverte|vanne\s+fermee|vanne\s+ferm[ée]e", "Organes de vanne"),
		(r"source", "Source/captage mentionné"),
		(r"reservoir|r[ée]servoir", "Réservoir mentionné"),
	]

	micro_hydro_elements: list[str] = []
	for pattern, label in feature_patterns:
		if re.search(pattern, norm, re.IGNORECASE):
			micro_hydro_elements.append(label)

	reducer_mentions_count = _count_reducer_mentions(text)

	return {
		"description_reservoirs": reservoir_description_lines,
		"elements_interessants_micro_hydro": micro_hydro_elements,
		"reducer_mentions_count": reducer_mentions_count,
	}


def _parse_float(value: Any) -> float | None:
	if value is None:
		return None
	if isinstance(value, (int, float)):
		return float(value)
	if not isinstance(value, str):
		return None

	cleaned = value.strip().replace("\u202f", " ").replace(" ", "")
	cleaned = cleaned.replace(",", ".")
	match = re.search(r"-?\d+(?:\.\d+)?", cleaned)
	if not match:
		return None
	try:
		return float(match.group(0))
	except ValueError:
		return None


def _build_focus_context(document_text: str, max_chars: int = 26000) -> str:
	text = (document_text or "").replace("\r\n", "\n").strip()
	if not text:
		return ""

	snippets: list[str] = []
	seen: set[str] = set()

	def add_snippet(chunk: str):
		chunk_clean = chunk.strip()
		if not chunk_clean:
			return
		key = chunk_clean[:400]
		if key in seen:
			return
		seen.add(key)
		snippets.append(chunk_clean)

	add_snippet(text[:9000])

	section_patterns = [
		r"charges?\s+de\s+r[ée]f[ée]rence",
		r"descriptif\s+et\s+[ée]tat\s+de\s+la\s+station",
		r"fili[èe]re\s+eau",
		r"fili[èe]re\s+boue",
		r"mesures\s+et\s+autosurveillance",
		r"hydraulique",
		r"performances",
		r"caract[ée]ristiques\s+du\s+rejet",
		r"type\s+d['’]ouvrage",
		r"ouvrage\s+d['’]infiltration",
	]

	for pattern in section_patterns:
		for match in re.finditer(pattern, text, flags=re.IGNORECASE):
			start = max(0, match.start() - 350)
			end = min(len(text), match.end() + 1700)
			add_snippet(text[start:end])

	for match in re.finditer(r"[^\n]{0,80}(m[³3]\s*/\s*j|m[³3]\s*/\s*jour|m3/j)[^\n]{0,120}", text, flags=re.IGNORECASE):
		start = max(0, match.start() - 260)
		end = min(len(text), match.end() + 260)
		add_snippet(text[start:end])

	merged: list[str] = []
	total = 0
	for snippet in snippets:
		block = snippet + "\n\n"
		if total + len(block) > max_chars:
			remaining = max_chars - total
			if remaining > 300:
				merged.append(block[:remaining])
			break
		merged.append(block)
		total += len(block)

	return "".join(merged).strip()


def _extract_flow_m3_per_day_from_text(document_text: str) -> float | None:
	text = (document_text or "").replace("\r\n", "\n")
	if not text.strip():
		return None

	search_zones: list[str] = []
	for section_match in re.finditer(r"charges?\s+de\s+r[ée]f[ée]rence", text, re.IGNORECASE):
		start = max(0, section_match.start() - 200)
		end = min(len(text), section_match.end() + 2600)
		search_zones.append(text[start:end])

	search_zones.extend([text[:12000], text])

	patterns = [
		r"Volume\s+de\s+r[ée]f[ée]rence\s*(?:m[³3]\s*/\s*jour|m3/jour)?\s*([0-9][0-9\s.,]*)",
		r"Volume\s+journalier\s*\(?(?:m[³3]\s*/\s*j|m3/j)\)?\s*([0-9][0-9\s.,]*)",
		r"d[ée]bit[^\n\r:]*[:=\-]?\s*(\d+[\d\s,.]*)\s*(?:m[³3]\s*/\s*j|m[³3]\s*/\s*jour|m3/j)",
		r"(\d+[\d\s,.]*)\s*(?:m[³3]\s*/\s*j|m[³3]\s*/\s*jour|m3/j)\s*(?:de\s+)?d[ée]bit",
	]

	for zone in search_zones:
		for pattern in patterns:
			for match in re.finditer(pattern, zone, re.IGNORECASE):
				raw_value = (match.group(1) or "").strip()
				if raw_value.lower() in {"nd", "null", "-", "n/a"}:
					continue
				value = _parse_float(raw_value)
				if value is not None:
					return value

	return None


def _parse_int(value: Any) -> int | None:
	parsed = _parse_float(value)
	if parsed is None:
		return None
	return int(round(parsed))


def _normalize_unit(raw_unit: str) -> str:
	unit = (raw_unit or "").lower().replace(" ", "")
	unit = unit.replace("m³", "m3")
	return unit


def _convert_flow_to_m3j_m3h(value: float, unit: str) -> tuple[float, float] | None:
	norm = _normalize_unit(unit)
	if norm.startswith("m3/j"):
		return value, value / 24
	if norm.startswith("m3/h"):
		return value * 24, value
	if norm.startswith("m3/s"):
		m3_h = value * 3600
		return m3_h * 24, m3_h
	if norm.startswith("l/s"):
		m3_h = value * 3.6
		return m3_h * 24, m3_h
	if norm.startswith("l/min"):
		m3_h = value * 0.06
		return m3_h * 24, m3_h
	if norm.startswith("l/h"):
		m3_h = value / 1000
		return m3_h * 24, m3_h
	return None


def _extract_flow_from_table_lines(document_text: str) -> tuple[float | None, float | None, str | None]:
	lines = [line.strip() for line in (document_text or "").replace("\r\n", "\n").split("\n")]
	lines = [line for line in lines if line]

	header_with_unit_pattern = re.compile(
		r"(d[ée]bit|q\b|qmoy|qmax|volume\s+de\s+r[ée]f[ée]rence|volume\s+journalier)[^\n]*?(m[³3]\s*/\s*j(?:our)?|m[³3]\s*/\s*h|m[³3]\s*/\s*s|l\s*/\s*s|l\s*/\s*min|l\s*/\s*h)",
		re.IGNORECASE,
	)

	for idx, line in enumerate(lines):
		header_match = header_with_unit_pattern.search(line)
		if not header_match:
			continue

		unit = header_match.group(2)
		for look_ahead in range(idx, min(idx + 4, len(lines))):
			candidate_line = lines[look_ahead]
			if re.search(r"\b(nd|null|n/?a|-)\b", candidate_line, re.IGNORECASE):
				continue
			num_match = re.search(r"([0-9]+(?:[\s.,][0-9]+)*)", candidate_line)
			if not num_match:
				continue
			value = _parse_float(num_match.group(1))
			if value is None:
				continue
			converted = _convert_flow_to_m3j_m3h(value, unit)
			if converted:
				m3_j, m3_h = converted
				return m3_j, m3_h, f"table_header:{_clean_spaces(line)[:80]}"

	inline_pattern = re.compile(
		r"([0-9]+(?:[\s.,][0-9]+)*)\s*(m[³3]\s*/\s*j(?:our)?|m[³3]\s*/\s*h|m[³3]\s*/\s*s|l\s*/\s*s|l\s*/\s*min|l\s*/\s*h)",
		re.IGNORECASE,
	)
	for line in lines:
		for match in inline_pattern.finditer(line):
			value = _parse_float(match.group(1))
			unit = match.group(2)
			if value is None:
				continue
			converted = _convert_flow_to_m3j_m3h(value, unit)
			if converted:
				m3_j, m3_h = converted
				return m3_j, m3_h, f"inline:{_clean_spaces(line)[:80]}"

	return None, None, None


def _collect_udi_debug_signals(document_text: str) -> dict[str, Any]:
	text = (document_text or "").replace("\r\n", "\n")
	lines = [line.strip() for line in text.split("\n") if line.strip()]
	flat = _clean_spaces(text).lower()

	keywords = [
		"udi",
		"débit",
		"debit",
		"m3/j",
		"m³/j",
		"m3/h",
		"m³/h",
		"l/s",
		"l/min",
		"pression",
		"bar",
		"hauteur de chute",
		"dénivelé",
		"denivele",
		"ngf",
		"source",
		"reservoir",
		"réservoir",
		"brise-charge",
		"brise charge",
	]

	keyword_counts = {key: flat.count(key) for key in keywords}

	interesting_patterns = [
		r"d[ée]bit",
		r"m[³3]\s*/\s*j",
		r"m[³3]\s*/\s*h",
		r"l\s*/\s*s",
		r"l\s*/\s*min",
		r"bar",
		r"hauteur\s+de\s+chute",
		r"d[ée]nivel[ée]",
		r"ngf",
		r"source",
		r"r[ée]servoir",
		r"brise[-\s]?charge",
	]

	samples: list[str] = []
	for line in lines:
		line_lower = line.lower()
		if any(re.search(pattern, line_lower, re.IGNORECASE) for pattern in interesting_patterns):
			samples.append(_clean_spaces(line))
			if len(samples) >= 12:
				break

	return {
		"text_length": len(text),
		"line_count": len(lines),
		"keyword_counts": keyword_counts,
		"raw_samples": samples,
	}


def _detect_blue_rp_symbol_detections_from_pdf(pdf_bytes: bytes) -> list[dict[str, Any]]:
	"""Best-effort detection of blue RP symbols from PDF vector spans with bboxes."""
	try:
		import fitz  # type: ignore
	except Exception:
		return []

	def _rgb_from_int(color_value: Any) -> tuple[int, int, int]:
		if not isinstance(color_value, int):
			return (0, 0, 0)
		r = (color_value >> 16) & 0xFF
		g = (color_value >> 8) & 0xFF
		b = color_value & 0xFF
		return (r, g, b)

	def _is_blue(color_value: Any) -> bool:
		# Text spans usually expose color as int RGB, vector drawings as float tuples [0,1].
		if isinstance(color_value, int):
			r, g, b = _rgb_from_int(color_value)
			return b >= 100 and b > r + 20 and b > g + 20
		if isinstance(color_value, (tuple, list)) and len(color_value) >= 3:
			try:
				r = float(color_value[0])
				g = float(color_value[1])
				b = float(color_value[2])
			except (TypeError, ValueError):
				return False
			return b >= 0.35 and b > r + 0.15 and b > g + 0.15
		return False

	def _rp_token_present(text_value: str) -> bool:
		norm_text = _normalize_for_search(text_value or "")
		if not re.search(UDI_REDUCER_ABBREV_STRICT_PATTERN, norm_text, re.IGNORECASE):
			return False
		compact = _clean_spaces(norm_text)
		# Accept isolated symbol-like labels (RP/PRV, RP-1, PRV principal).
		if len(compact) <= 18:
			return True
		# Longer text requires explicit pressure/reducer semantics.
		return re.search(UDI_REDUCER_CONTEXT_PATTERN, compact, re.IGNORECASE) is not None

	detections: list[dict[str, Any]] = []
	seen_regions: set[tuple[int, int, int]] = set()
	doc = None
	try:
		doc = fitz.open(stream=pdf_bytes, filetype="pdf")
		for page_index, page in enumerate(doc):
			text_dict = page.get_text("dict") or {}
			for block in text_dict.get("blocks", []):
				if block.get("type") != 0:
					continue
				for line in block.get("lines", []):
					for span in (line.get("spans") or []):
						span_text = _clean_spaces(str(span.get("text") or ""))
						if not _rp_token_present(span_text):
							continue
						if not _is_blue(span.get("color")):
							continue
						bbox = span.get("bbox") or [0, 0, 0, 0]
						try:
							x0 = float(bbox[0])
							y0 = float(bbox[1])
							x1 = float(bbox[2])
							y1 = float(bbox[3])
						except (TypeError, ValueError, IndexError):
							x0 = y0 = x1 = y1 = 0.0
						cx = int((x0 + x1) / 2.0)
						cy = int((y0 + y1) / 2.0)
						region_key = (page_index, cx // 8, cy // 8)
						if region_key not in seen_regions:
							seen_regions.add(region_key)
							detections.append(
								{
									"symbol": "pressure_reducer",
									"confidence": 0.88,
									"bounding_box": [x0, y0, x1, y1],
									"page": int(page_index + 1),
									"site": "",
									"method": "pdf_vector_blue_rp",
								}
							)

			# Secondary pass: detect blue circles with RP/PRV text in or near the marker.
			for drawing in (page.get_drawings() or []):
				rect = drawing.get("rect")
				if rect is None:
					continue
				try:
					shape_rect = fitz.Rect(rect)
				except Exception:
					continue
				w = float(shape_rect.width)
				h = float(shape_rect.height)
				if w < 8 or h < 8 or w > 120 or h > 120:
					continue
				if abs(w - h) > max(w, h) * 0.35:
					continue
				if not (_is_blue(drawing.get("color")) or _is_blue(drawing.get("fill"))):
					continue

				pad = max(w, h) * 0.35
				clip = fitz.Rect(
					max(0.0, shape_rect.x0 - pad),
					max(0.0, shape_rect.y0 - pad),
					shape_rect.x1 + pad,
					shape_rect.y1 + pad,
				)
				clip_text = page.get_text("text", clip=clip) or ""
				if not _rp_token_present(clip_text):
					continue

				cx = int((shape_rect.x0 + shape_rect.x1) / 2.0)
				cy = int((shape_rect.y0 + shape_rect.y1) / 2.0)
				region_key = (page_index, cx // 8, cy // 8)
				if region_key not in seen_regions:
					seen_regions.add(region_key)
					detections.append(
						{
							"symbol": "pressure_reducer",
							"confidence": 0.9,
							"bounding_box": [
								float(shape_rect.x0),
								float(shape_rect.y0),
								float(shape_rect.x1),
								float(shape_rect.y1),
							],
							"page": int(page_index + 1),
							"site": "",
							"method": "pdf_vector_blue_circle_rp",
						}
					)
	except Exception:
		return []
	finally:
		try:
			if doc is not None:
				doc.close()
		except Exception:
			pass

	return detections


def _detect_blue_rp_symbols_from_pdf(pdf_bytes: bytes) -> int:
	"""Backward-compatible count wrapper around detailed blue RP detections."""
	return len(_detect_blue_rp_symbol_detections_from_pdf(pdf_bytes))


def _detect_legend_equipment_from_pdf(pdf_bytes: bytes) -> dict[str, Any]:
	"""Detect RP/PRV and brise-charge labels specifically inside legend areas."""
	try:
		import fitz  # type: ignore
	except Exception:
		return {
			"has_reducer": False,
			"has_brise_charge": False,
			"legend_reducer_count": 0,
			"legend_brise_charge_count": 0,
		}

	def _word_to_rect(word_tuple: Any) -> Any:
		try:
			return fitz.Rect(float(word_tuple[0]), float(word_tuple[1]), float(word_tuple[2]), float(word_tuple[3]))
		except Exception:
			return None

	def _looks_like_legend_anchor(token: str) -> bool:
		norm = _normalize_for_search(token)
		if not norm:
			return False
		if norm in {"legende", "legend", "symbole", "symboles", "symbologie"}:
			return True
		return re.search(r"legende|legend|symbol", norm, re.IGNORECASE) is not None

	def _legend_has_reducer(legend_text: str) -> bool:
		norm = _normalize_for_search(legend_text)
		if re.search(UDI_REDUCER_PHRASE_PATTERN, norm, re.IGNORECASE):
			return True
		if "reducteur de pression" in norm:
			return True
		if re.search(r"\bprv\b|\brp\b|\br\s*\.?\s*p\b|\bp\s*\.?\s*r\s*\.?\s*v\b", norm, re.IGNORECASE):
			return True
		return re.search(UDI_REDUCER_ABBREV_STRICT_PATTERN, norm, re.IGNORECASE) is not None

	def _legend_has_brise_charge(legend_text: str) -> bool:
		norm = _normalize_for_search(legend_text)
		if re.search(UDI_BRISE_CHARGE_LEGEND_PATTERN, norm, re.IGNORECASE):
			return True
		# In legend style 1, brise-charge can be represented as "vanne altimetrique".
		return "vanne altimetrique" in norm

	@lru_cache(maxsize=1)
	def _get_reference_legend_keywords() -> dict[str, set[str]]:
		"""Load OCR hints from explicit project legend references (legende 1/2)."""
		workspace_root = Path(__file__).resolve().parent.parent
		result: dict[str, set[str]] = {"reducer": set(), "brise": set()}

		try:
			import pytesseract  # type: ignore
			from PIL import Image, ImageOps  # type: ignore
		except Exception:
			return result

		tesseract_cmd = _resolve_tesseract_cmd()
		if tesseract_cmd:
			pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

		candidate_paths: list[Path] = []
		for file_name in LEGEND_REFERENCE_FILES:
			candidate_paths.append(workspace_root / file_name)

		# Accept practical filename variants for "legende 1" and "legende 2".
		for base_name in ["legende 1", "legende1", "legende_1", "legend 1", "legend1"]:
			for ext in [".jpg", ".JPG", ".jpeg", ".JPEG", ".png", ".PNG"]:
				candidate_paths.append(workspace_root / f"{base_name}{ext}")
		for base_name in ["legende 2", "legende2", "legende_2", "legend 2", "legend2"]:
			for ext in [".jpg", ".JPG", ".jpeg", ".JPEG", ".png", ".PNG"]:
				candidate_paths.append(workspace_root / f"{base_name}{ext}")

		seen_paths: set[str] = set()
		for legend_path in candidate_paths:
			path_key = str(legend_path).lower()
			if path_key in seen_paths:
				continue
			seen_paths.add(path_key)
			if not legend_path.exists():
				continue
			try:
				img = Image.open(legend_path).convert("L")
				img = ImageOps.autocontrast(img)
				text = pytesseract.image_to_string(img, lang="fra+eng", config="--oem 3 --psm 6", timeout=10)
			except Exception:
				continue

			norm = _normalize_for_search(text)
			if not norm:
				continue
			if "reducteur de pression" in norm or " rp " in f" {norm} " or " prv " in f" {norm} ":
				result["reducer"].update({"reducteur de pression", "rp", "prv"})
			if "vanne altimetrique" in norm or "brise charge" in norm or "brise-charge" in norm:
				result["brise"].update({"vanne altimetrique", "brise charge", "brise-charge"})

		return result

	def _ocr_legend_zone(page: Any, zone: Any) -> str:
		# OCR fallback helps on rotated/outlined legend text where PDF text extraction is incomplete.
		try:
			import pytesseract  # type: ignore
			from PIL import Image, ImageOps  # type: ignore
		except Exception:
			return ""

		try:
			tesseract_cmd = _resolve_tesseract_cmd()
			if tesseract_cmd:
				pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

			matrix = fitz.Matrix(3.0, 3.0)
			pix = page.get_pixmap(matrix=matrix, clip=zone, alpha=False)
			img = Image.open(BytesIO(pix.tobytes("png"))).convert("L")
			img = ImageOps.autocontrast(img)
			text = pytesseract.image_to_string(img, lang="fra+eng", config="--oem 3 --psm 6", timeout=10)
			return text or ""
		except Exception:
			return ""

	has_reducer = False
	has_brise_charge = False
	legend_reducer_count = 0
	legend_brise_count = 0
	legend_signal_zones: list[dict[str, Any]] = []

	doc = None
	try:
		doc = fitz.open(stream=pdf_bytes, filetype="pdf")
		for page in doc:
			page_rect = page.rect
			words = page.get_text("words") or []
			legend_zone_rects: list[Any] = []

			for word in words:
				if len(word) < 5:
					continue
				word_text = str(word[4] or "")
				if not _looks_like_legend_anchor(word_text):
					continue
				anchor_rect = _word_to_rect(word)
				if anchor_rect is None:
					continue

				zone = fitz.Rect(
					max(0.0, anchor_rect.x0 - 60.0),
					max(0.0, anchor_rect.y0 - 30.0),
					page_rect.x1,
					min(page_rect.y1, anchor_rect.y1 + 360.0),
				)
				legend_zone_rects.append(zone)

			for zone in legend_zone_rects[:6]:
				legend_text = page.get_text("text", clip=zone) or ""
				if not legend_text.strip():
					legend_text = _ocr_legend_zone(page, zone)
				elif not (_legend_has_reducer(legend_text) or _legend_has_brise_charge(legend_text)):
					# Text extraction can miss some glyphs; enrich with OCR when no signal found.
					legend_text = f"{legend_text}\n{_ocr_legend_zone(page, zone)}"
				if not legend_text.strip():
					continue

				reference_keywords = _get_reference_legend_keywords()
				norm_legend = _normalize_for_search(legend_text)
				has_reducer_in_ref = any(token in norm_legend for token in reference_keywords.get("reducer", set()))
				has_brise_in_ref = any(token in norm_legend for token in reference_keywords.get("brise", set()))

				if _legend_has_reducer(legend_text) or has_reducer_in_ref:
					has_reducer = True
					legend_reducer_count = max(legend_reducer_count, 1)
					legend_signal_zones.append(
						{
							"page": int(page.number + 1),
							"bounding_box": [float(zone.x0), float(zone.y0), float(zone.x1), float(zone.y1)],
							"symbol": "pressure_reducer",
							"confidence": 0.7,
						}
					)

				if _legend_has_brise_charge(legend_text) or has_brise_in_ref:
					has_brise_charge = True
					legend_brise_count = max(legend_brise_count, 1)
					legend_signal_zones.append(
						{
							"page": int(page.number + 1),
							"bounding_box": [float(zone.x0), float(zone.y0), float(zone.x1), float(zone.y1)],
							"symbol": "pressure_break_chamber",
							"confidence": 0.68,
						}
					)

	finally:
		try:
			if doc is not None:
				doc.close()
		except Exception:
			pass

	return {
		"has_reducer": has_reducer,
		"has_brise_charge": has_brise_charge,
		"legend_reducer_count": legend_reducer_count,
		"legend_brise_charge_count": legend_brise_count,
		"legend_zones": legend_signal_zones[:12],
	}


def _guess_udi_site_label(result_json: dict[str, Any]) -> str:
	if not isinstance(result_json, dict):
		return ""
	if isinstance(result_json.get("nom_udi"), str) and result_json.get("nom_udi"):
		return str(result_json.get("nom_udi"))
	sites = result_json.get("sites_udi")
	if isinstance(sites, list) and sites:
		first = sites[0]
		if isinstance(first, dict):
			site_name = str(first.get("site") or "").strip()
			if site_name:
				return site_name
	return ""


def _build_symbol_detections_from_pdf_signals(
	pdf_bytes: bytes,
	result_json: dict[str, Any],
	legend_equipment: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
	"""Build a standardized detection list compatible with downstream infrastructure mapping."""
	site_hint = _guess_udi_site_label(result_json)
	detections: list[dict[str, Any]] = []

	for det in _detect_blue_rp_symbol_detections_from_pdf(pdf_bytes):
		item = dict(det)
		if not item.get("site"):
			item["site"] = site_hint
		detections.append(item)

	legend = legend_equipment if isinstance(legend_equipment, dict) else _detect_legend_equipment_from_pdf(pdf_bytes)
	for zone in legend.get("legend_zones") or []:
		if not isinstance(zone, dict):
			continue
		symbol = str(zone.get("symbol") or "").strip() or "pressure_reducer"
		bbox = zone.get("bounding_box")
		page = zone.get("page")
		if not isinstance(bbox, list) or len(bbox) != 4:
			continue
		if not isinstance(page, int):
			continue
		detections.append(
			{
				"symbol": symbol,
				"confidence": float(zone.get("confidence") or 0.65),
				"bounding_box": [float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])],
				"page": page,
				"site": site_hint,
				"method": "legend_zone_ocr",
			}
		)

	return detections


def _detect_template_bank_symbols_from_pdf(pdf_bytes: bytes, result_json: dict[str, Any]) -> list[dict[str, Any]]:
	"""Detect symbols with local template bank: data/templates_symbols/<symbol>/*.png."""
	try:
		import fitz  # type: ignore
		import cv2  # type: ignore
		import numpy as np  # type: ignore
	except Exception:
		return []

	workspace_root = Path(__file__).resolve().parent.parent
	templates_dir = workspace_root / "data" / "templates_symbols"
	if not templates_dir.exists() or not templates_dir.is_dir():
		return []

	site_hint = _guess_udi_site_label(result_json)
	detections: list[dict[str, Any]] = []
	doc = None
	try:
		doc = fitz.open(stream=pdf_bytes, filetype="pdf")
		for page_index, page in enumerate(doc):
			matrix = fitz.Matrix(2.5, 2.5)
			pix = page.get_pixmap(matrix=matrix, alpha=False)
			buffer = np.frombuffer(pix.tobytes("png"), dtype=np.uint8)
			image_bgr = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
			if image_bgr is None:
				continue
			page_detections = detect_symbols_from_template_bank(
				image_bgr=image_bgr,
				templates_dir=templates_dir,
				page=int(page_index + 1),
				site=site_hint,
				threshold=0.8,
			)
			detections.extend(page_detections)
	finally:
		try:
			if doc is not None:
				doc.close()
		except Exception:
			pass

	return detections


def _clean_spaces(text: str) -> str:
	return re.sub(r"\s+", " ", (text or "")).strip()


def _fold_accents(text: str) -> str:
	if not text:
		return ""
	normalized = unicodedata.normalize("NFKD", text)
	return "".join(char for char in normalized if not unicodedata.combining(char))


def _collapse_spaced_words(text: str) -> str:
	if not text:
		return ""

	def _join_letters(match: re.Match[str]) -> str:
		return match.group(0).replace(" ", "")

	value = re.sub(r"\b(?:[A-Za-z]\s+){2,}[A-Za-z]\b", _join_letters, text)
	# OCR may split inside key hydraulic labels; fold them explicitly.
	for noisy, fixed in [
		(r"d\s*e\s*b\s*i\s*t", "debit"),
		(r"r\s*e\s*s\s*e\s*r\s*v\s*o\s*i\s*r", "reservoir"),
		(r"d\s*e\s*n\s*i\s*v\s*e\s*l\s*e", "denivele"),
		(r"u\s*d\s*i", "udi"),
	]:
		value = re.sub(noisy, fixed, value, flags=re.IGNORECASE)
	return value


def _normalize_ocr_tokens(text: str) -> str:
	if not text:
		return ""
	value = text
	value = re.sub(r"(?<=\d)\s+(?=m\s*ngf)", "", value, flags=re.IGNORECASE)
	value = re.sub(r"m\s*[³3]\s*/\s*j(?:our)?", "m3/j", value, flags=re.IGNORECASE)
	value = re.sub(r"m\s*[³3]\s*/\s*h", "m3/h", value, flags=re.IGNORECASE)
	value = re.sub(r"m\s*[³3]\s*/\s*s", "m3/s", value, flags=re.IGNORECASE)
	value = re.sub(r"l\s*/\s*s", "l/s", value, flags=re.IGNORECASE)
	value = re.sub(r"l\s*/\s*min", "l/min", value, flags=re.IGNORECASE)
	value = re.sub(r"([A-Za-z])\s*[:;]\s*([0-9])", r"\1: \2", value)
	return value


def _normalize_for_search(text: str) -> str:
	if not text:
		return ""
	value = _normalize_ocr_tokens(text)
	value = value.replace("\u00b3", "3")
	value = _fold_accents(value)
	value = _collapse_spaced_words(value)
	value = _clean_spaces(value).lower()
	return value


def _extract_numeric_from_labeled_lines(text: str, label_pattern: str, max_scan_lines: int = 2) -> float | None:
	lines = [line for line in (text or "").replace("\r\n", "\n").split("\n") if line.strip()]
	for idx, line in enumerate(lines):
		if not re.search(label_pattern, _normalize_for_search(line), re.IGNORECASE):
			continue
		for offset in range(0, max_scan_lines + 1):
			j = idx + offset
			if j >= len(lines):
				break
			candidate = _clean_spaces(lines[j])
			m = re.search(r"([0-9]+(?:[\s.,][0-9]+)*)", candidate)
			if not m:
				continue
			parsed = _parse_float(m.group(1))
			if parsed is not None:
				return parsed
	return None


def _forced_udi_number_from_filename(filename: str | None) -> str | None:
	name = str(filename or "")
	m = re.search(r"__UDI_([0-9]{1,3})_", name, re.IGNORECASE)
	return m.group(1) if m else None


def _slice_text_to_forced_udi_section(document_text: str, forced_udi_number: str | None) -> str:
	"""Restrict OCR text to one UDI block when a segmented filename encodes the target UDI."""
	text = (document_text or "").replace("\r\n", "\n")
	forced = str(forced_udi_number or "").strip()
	if not text or not forced:
		return text

	markers = list(re.finditer(r"\budi\s*([0-9]{1,3})\b", text, flags=re.IGNORECASE))
	if not markers:
		return text

	start_match = next((m for m in markers if m.group(1) == forced), None)
	if start_match is None:
		return text

	start = max(0, start_match.start() - 120)
	end = len(text)
	for marker in markers:
		if marker.start() <= start_match.start():
			continue
		if marker.group(1) != forced:
			end = marker.start()
			break

	sliced = text[start:end].strip()
	# Keep original text only when slicing collapses to an unusably tiny fragment.
	if len(sliced) < 40:
		return text
	return sliced


def _is_missing(value: Any) -> bool:
	if value is None:
		return True
	if isinstance(value, str):
		normalized = value.strip().lower()
		if not normalized:
			return True
		if normalized in {
			"null",
			"none",
			"nd",
			"n/a",
			"na",
			"non déterminé",
			"non determine",
			"information non disponible",
			"-",
		}:
			return True
	if isinstance(value, list) and len(value) == 0:
		return True
	return False


def _extract_satese_fields_from_text(document_text: str) -> dict[str, Any]:
	text = (document_text or "").replace("\r\n", "\n")
	flat = _clean_spaces(text)
	result: dict[str, Any] = {}

	commune_match = re.search(
		r"\bCommune\s+de\s+(.+?)(?=\s+STEU\b|\s+Date\s+de\s+la\s+visite\b|\s+Capacit[ée]\b|$)",
		flat,
		re.IGNORECASE,
	)
	if commune_match:
		result["commune"] = _clean_spaces(commune_match.group(1))

	station_match = re.search(
		r"\bSTEU\s+(.+?)(?=\s+Date\s+de\s+la\s+visite\b|\s+Capacit[ée]\b|\s+Code\s+Sandre\b|$)",
		flat,
		re.IGNORECASE,
	)
	if station_match:
		result["nom_station"] = "STEU " + _clean_spaces(station_match.group(1))

	cap_match = re.search(r"Capacit[ée]\s*EH\s*([0-9][0-9\s.,]*)", flat, re.IGNORECASE)
	if cap_match:
		result["capacite_eh"] = _parse_int(cap_match.group(1))

	year_match = re.search(r"Ann[ée]e\s+de\s+mise\s+en\s+service\s*([12][0-9]{3})", flat, re.IGNORECASE)
	if year_match:
		result["annee_mise_service"] = int(year_match.group(1))

	coord_match = re.search(
		r"X\s*=\s*([0-9\s]+)\s*m\s*;\s*Y\s*=\s*([0-9\s]+)\s*m",
		flat,
		re.IGNORECASE,
	)
	if coord_match:
		x = _clean_spaces(coord_match.group(1))
		y = _clean_spaces(coord_match.group(2))
		result["coordonnees"] = f"X={x} m; Y={y} m"

	infiltration_match = re.search(
		r"(?:Superficie\s+d['’]infiltration\s*\(m²\)|S\s*=)\s*([0-9][0-9\s.,]*)\s*m²",
		flat,
		re.IGNORECASE,
	)
	if infiltration_match:
		result["surface_infiltration_m2"] = _parse_float(infiltration_match.group(1))

	debit_ref_match = re.search(
		r"Volume\s+de\s+r[ée]f[ée]rence\s*m3/jour\s*([0-9][0-9\s.,]*)",
		flat,
		re.IGNORECASE,
	)
	if debit_ref_match:
		result["debit_m3_j"] = _parse_float(debit_ref_match.group(1))
	else:
		fallback_flow = _extract_flow_m3_per_day_from_text(text)
		if fallback_flow is not None:
			result["debit_m3_j"] = fallback_flow

	casiers_drains_match = re.search(
		r"([0-9]+)\s*casiers?\s*de\s*([0-9]+)\s*drains?\s*chacun",
		flat,
		re.IGNORECASE,
	)
	if casiers_drains_match:
		n_casiers = int(casiers_drains_match.group(1))
		n_drains_each = int(casiers_drains_match.group(2))
		result["nombre_casiers"] = n_casiers
		result["nombre_drains"] = n_casiers * n_drains_each
	else:
		drains_match = re.search(r"Nombre\s+de\s+drains?\s*([0-9]+)", flat, re.IGNORECASE)
		if drains_match:
			result["nombre_drains"] = int(drains_match.group(1))
		casiers_match = re.search(r"([0-9]+)\s*casiers?", flat, re.IGNORECASE)
		if casiers_match:
			result["nombre_casiers"] = int(casiers_match.group(1))

	ouvrage_matches = re.findall(r"Type\s+d['’]ouvrage\s+([^\n]{3,90})", text, flags=re.IGNORECASE)
	ouvrages: list[str] = []
	for raw in ouvrage_matches:
		candidate = _clean_spaces(raw)
		candidate = re.sub(r"\s+Etat\s+de\s+l['’]ouvrage.*$", "", candidate, flags=re.IGNORECASE).strip(" -")
		if not candidate:
			continue
		if any(token in candidate.lower() for token in ["type d'ouvrage", "dimensions", "equipements", "présence", "fréquence", "etat de l'ouvrage", "état de l'ouvrage"]):
			continue
		if len(candidate) < 3:
			continue
		if candidate not in ouvrages:
			ouvrages.append(candidate)
	if ouvrages:
		result["ouvrages"] = ouvrages

	if re.search(r"(potentiel\s+hydraulique|r[ée]cup[ée]ration\s+d['’]?[ée]nergie|micro\s*-?turbine)", flat, re.IGNORECASE):
		result["potentiel_hydraulique"] = True

	solar_surface_match = re.search(
		r"surface\s+(?:potentiellement\s+)?disponible[^\n]{0,40}panneaux\s+solaires?\s*[:=]?\s*([0-9][0-9\s.,]*)\s*m²",
		flat,
		re.IGNORECASE,
	)
	if solar_surface_match:
		result["surface_potentielle_solaire_m2"] = _parse_float(solar_surface_match.group(1))

	return result


def _extract_udi_fields_from_text(document_text: str) -> dict[str, Any]:
	text = (document_text or "").replace("\r\n", "\n")
	text_ocr = _normalize_ocr_tokens(text)
	flat = _clean_spaces(text_ocr)
	flat_norm = _normalize_for_search(flat)
	result: dict[str, Any] = {}
	legend_signals = _extract_udi_legend_signals(text_ocr)
	lines = [line.strip() for line in text_ocr.split("\n") if line.strip()]
	sites_udi = _extract_udi_sites_from_text(text_ocr)
	if sites_udi:
		result["sites_udi"] = sites_udi
		reservoirs_udi = _extract_udi_reservoirs_from_text(text_ocr, sites_udi)
		if reservoirs_udi:
			result["reservoirs_udi"] = reservoirs_udi
			# For multi-UDI pages, assign volume per site from matching reservoir entities.
			volumes_by_site: dict[str, float] = {}
			for res in reservoirs_udi:
				if not isinstance(res, dict):
					continue
				site_key = _normalize_for_search(str(res.get("site_udi") or ""))
				vol = res.get("volume_reservoir_m3")
				if not site_key or not isinstance(vol, (int, float)):
					continue
				if site_key not in volumes_by_site or float(vol) > volumes_by_site[site_key]:
					volumes_by_site[site_key] = float(vol)
			for site in sites_udi:
				if not isinstance(site, dict):
					continue
				site_key = _normalize_for_search(str(site.get("site") or ""))
				if site_key in volumes_by_site:
					site["volume_reservoir_m3"] = volumes_by_site[site_key]
		site_volumes = [s.get("volume_reservoir_m3") for s in sites_udi if isinstance(s.get("volume_reservoir_m3"), (int, float))]
		if site_volumes and result.get("volume_reservoir_m3") is None:
			result["volume_reservoir_m3"] = max(float(v) for v in site_volumes)
		known_signed = [s.get("denivele_source_reservoir_m") for s in sites_udi if isinstance(s.get("denivele_source_reservoir_m"), (int, float))]
		if known_signed:
			best_signed = max((float(v) for v in known_signed), key=lambda x: abs(x))
			result["denivele_source_reservoir_m"] = round(best_signed, 3)
			result["denivele_estime_m"] = round(abs(best_signed), 3)
			if best_signed > 0:
				result["hauteur_chute_estimee_m"] = round(best_signed, 3)
				result["potentiel_hydraulique"] = True
			else:
				# Keep signed head for diagnostics: negative means source below reservoir.
				result["hauteur_chute_estimee_m"] = round(best_signed, 3)
				result["potentiel_hydraulique"] = False

	if result.get("reservoirs_udi"):
		reservoir_signed = [
			r.get("denivele_source_reservoir_m")
			for r in result.get("reservoirs_udi", [])
			if isinstance(r, dict) and isinstance(r.get("denivele_source_reservoir_m"), (int, float))
		]
		if reservoir_signed:
			best_signed = max((float(v) for v in reservoir_signed), key=lambda x: abs(x))
			current_signed = _parse_float(result.get("denivele_source_reservoir_m"))
			# Keep the strongest signed signal; do not let weak/zero reservoir matches override better site/local values.
			should_override = current_signed is None or abs(best_signed) > abs(current_signed)
			if should_override:
				result["denivele_source_reservoir_m"] = round(best_signed, 3)
				result["denivele_estime_m"] = round(abs(best_signed), 3)
				if best_signed > 0:
					result["hauteur_chute_estimee_m"] = round(best_signed, 3)
					if result.get("potentiel_hydraulique") is None:
						result["potentiel_hydraulique"] = True
				else:
					result["hauteur_chute_estimee_m"] = round(best_signed, 3)
					result["potentiel_hydraulique"] = False

	# Estimate confidence for reservoir volume extraction (global + per-site).
	confidence_rank = {"low": 0, "medium": 1, "high": 2}
	confidence_by_site: list[dict[str, str]] = []
	reservoirs_all = result.get("reservoirs_udi") if isinstance(result.get("reservoirs_udi"), list) else []
	for site in sites_udi if isinstance(sites_udi, list) else []:
		if not isinstance(site, dict):
			continue
		site_name = str(site.get("site") or "").strip()
		site_key = _normalize_for_search(site_name)
		site_volume = site.get("volume_reservoir_m3")
		if not isinstance(site_volume, (int, float)):
			level = "low"
		else:
			has_res_match_with_volume = False
			for res in reservoirs_all:
				if not isinstance(res, dict):
					continue
				res_site_key = _normalize_for_search(str(res.get("site_udi") or ""))
				res_vol = res.get("volume_reservoir_m3")
				if res_site_key and res_site_key == site_key and isinstance(res_vol, (int, float)):
					has_res_match_with_volume = True
					break

			has_structural_signals = any(
				isinstance(site.get(field), (int, float))
				for field in ["source_altitude_ngf_m", "reservoir_altitude_ngf_m", "denivele_source_reservoir_m"]
			)

			if has_res_match_with_volume:
				level = "high"
			elif has_structural_signals:
				level = "medium"
			else:
				level = "low"

		site["volume_reservoir_confidence"] = level
		confidence_by_site.append({"site": site_name or "Site UDI", "confidence": level})

	if confidence_by_site:
		result["volume_reservoir_confidence_by_site"] = confidence_by_site

	global_volume = result.get("volume_reservoir_m3")
	if isinstance(global_volume, (int, float)) and confidence_by_site:
		best_level = "low"
		for item in confidence_by_site:
			lvl = str(item.get("confidence") or "low").lower()
			if lvl not in confidence_rank:
				continue
			if confidence_rank[lvl] > confidence_rank[best_level]:
				best_level = lvl
		result["volume_reservoir_confidence"] = best_level
	elif isinstance(global_volume, (int, float)):
		result["volume_reservoir_confidence"] = "medium"
	else:
		result["volume_reservoir_confidence"] = "low"

	udi_name_match = re.search(
		r"\bUDI\s*([0-9]{1,2})\s*[:\-]?\s*([A-Za-z0-9À-ÖØ-öø-ÿ'\-\s]{2,120}?)(?=\s+(?:D[ée]bit|Volume|Hauteur|Brise|Source|R[ée]servoir|Commune|$))",
		flat,
		re.IGNORECASE,
	)
	if udi_name_match:
		number = _clean_spaces(udi_name_match.group(1))
		name_tail = _clean_spaces(udi_name_match.group(2))
		candidate_name = f"UDI {number} - {name_tail}" if name_tail else f"UDI {number}"
		multi_udi_label = len(re.findall(r"\bUDI\s*[0-9]{1,3}\b", candidate_name, flags=re.IGNORECASE)) >= 2
		if (not multi_udi_label) and (not re.fullmatch(r"UDI\s+[0-9]{1,2}\s*[- ]*", candidate_name or "", re.IGNORECASE)):
			result["nom_udi"] = candidate_name
	elif re.search(r"\b(aep|eau\s+potable|synoptique)\b", flat_norm, re.IGNORECASE):
		for line in lines[:25]:
			candidate = _clean_spaces(line)
			if len(candidate) < 8:
				continue
			if re.search(r"(synoptique|schema|schéma|aep|eau\s+potable|udi|reseau|réseau)", _normalize_for_search(candidate), re.IGNORECASE):
				candidate = re.sub(r"\s{2,}", " ", candidate).strip("- ")
				result["nom_udi"] = candidate[:120]
				break

	if _is_missing(result.get("nom_udi")) and sites_udi:
		first_site = sites_udi[0]
		if isinstance(first_site, dict):
			site_name = _clean_spaces(str(first_site.get("site") or ""))
			if site_name:
				result["nom_udi"] = site_name

	structured_reservoir_descriptions: list[str] = []
	for res in result.get("reservoirs_udi") or []:
		if not isinstance(res, dict):
			continue
		label = _clean_spaces(str(res.get("reservoir") or "Réservoir"))
		if not label:
			label = "Réservoir"
		parts = [label]
		vol = res.get("volume_reservoir_m3")
		if isinstance(vol, (int, float)):
			parts.append(f"volume {float(vol)} m3")
		res_alt = res.get("reservoir_altitude_ngf_m")
		if isinstance(res_alt, (int, float)):
			parts.append(f"alt réservoir {float(res_alt)} m NGF")
		src_alt = res.get("source_altitude_ngf_m")
		if isinstance(src_alt, (int, float)):
			parts.append(f"alt source {float(src_alt)} m NGF")
		signed = res.get("denivele_source_reservoir_m")
		if isinstance(signed, (int, float)):
			parts.append(f"Δ source->réservoir {float(signed)} m")
		desc = " ; ".join(parts)
		if desc not in structured_reservoir_descriptions:
			structured_reservoir_descriptions.append(desc)

	legend_desc = legend_signals.get("description_reservoirs") or []
	merged_desc: list[str] = []
	for entry in structured_reservoir_descriptions + (legend_desc if isinstance(legend_desc, list) else []):
		if not isinstance(entry, str):
			continue
		clean_entry = _clean_spaces(entry)
		if len(clean_entry) < 6:
			continue
		if re.search(r"\b(bp\s*\d+|france|dessinatrice|ingenieur|format\s*:|communaute\s+de\s+communes)\b", _normalize_for_search(clean_entry), re.IGNORECASE):
			continue
		if clean_entry not in merged_desc:
			merged_desc.append(clean_entry)
	if merged_desc:
		result["description_reservoirs"] = merged_desc[:10]

	communes = []
	for m in re.finditer(r"\bCommune\s+de\s+([A-Za-zÀ-ÖØ-öø-ÿ'\-\s]{2,80})", flat, re.IGNORECASE):
		name = _clean_spaces(m.group(1))
		if name and name not in communes:
			communes.append(name)
	if communes:
		result["communes"] = communes

	localisation_patterns = [
		r"\b(?:lieu[-\s]?dit|secteur|hameau|quartier|site)\s*[:\-]?\s*([A-Za-zÀ-ÖØ-öø-ÿ0-9'\-\s]{2,90})",
		r"\b(?:communes?|territoire)\s*[:\-]?\s*([A-Za-zÀ-ÖØ-öø-ÿ0-9'\-\s,]{3,120})",
	]
	for pattern in localisation_patterns:
		m = re.search(pattern, flat, re.IGNORECASE)
		if m:
			result["localisation"] = _clean_spaces(m.group(1))
			break

	if re.search(UDI_BRISE_CHARGE_PATTERN, flat_norm, re.IGNORECASE):
		result["presence_brise_charge"] = True

	count_brise = len(re.findall(UDI_BRISE_CHARGE_PATTERN, flat_norm, flags=re.IGNORECASE))
	if count_brise > 0:
		result["nombre_brise_charge"] = count_brise

	reducer_count = _count_reducer_mentions(text_ocr)
	legend_reducer_count = legend_signals.get("reducer_mentions_count")
	if isinstance(legend_reducer_count, int) and legend_reducer_count > reducer_count:
		reducer_count = legend_reducer_count
	result["presence_reducteurs_pression"] = reducer_count > 0
	if reducer_count > 0:
		result["nombre_reducteurs_pression"] = reducer_count
		points_existing = result.get("points_pression_reduction")
		if not isinstance(points_existing, list):
			points_existing = []
		if "RP/PRV (légende)" not in points_existing:
			points_existing.append("RP/PRV (légende)")
		result["points_pression_reduction"] = points_existing

	flow_values_j: list[float] = []
	debug_sources: list[str] = []

	flow_patterns = [
		r"(?:d[ée]bit\s+(?:moyen|nominal|de\s+pointe|source|produit)|d[ée]bit|q\s*(?:moy|max|nom)?|qmoy|qmax|q)\s*[:=\-]?\s*([0-9]+(?:\s*[àa\-]\s*[0-9]+)?[0-9\s.,]*)\s*(m[³3]\s*/\s*j(?:our)?|m[³3]\s*/\s*h|m[³3]\s*/\s*s|l\s*/\s*s|l\s*/\s*min|l\s*/\s*h)",
		r"([0-9]+(?:\s*[àa\-]\s*[0-9]+)?[0-9\s.,]*)\s*(m[³3]\s*/\s*j(?:our)?|m[³3]\s*/\s*h|m[³3]\s*/\s*s|l\s*/\s*s|l\s*/\s*min|l\s*/\s*h)\s*(?:de\s+)?(?:d[ée]bit|q|qmoy|qmax)",
	]

	search_flats = [flat, flat_norm]
	for searchable in search_flats:
		for pattern in flow_patterns:
			for match in re.finditer(pattern, searchable, re.IGNORECASE):
				raw_value = (match.group(1) or "").strip()
				unit = (match.group(2) or "").lower().replace(" ", "")

				range_match = re.search(r"([0-9][0-9\s.,]*)\s*[àa\-]\s*([0-9][0-9\s.,]*)", raw_value)
				if range_match:
					v1 = _parse_float(range_match.group(1))
					v2 = _parse_float(range_match.group(2))
					value = max(v for v in [v1, v2] if v is not None) if (v1 is not None or v2 is not None) else None
				else:
					value = _parse_float(raw_value)

				if value is None:
					continue

				converted = _convert_flow_to_m3j_m3h(value, unit)
				if converted:
					m3_j, _m3_h = converted
					flow_values_j.append(m3_j)
					debug_sources.append(f"regex:{_normalize_unit(unit)}={value}")

	table_m3j, _table_m3h, table_source = _extract_flow_from_table_lines(text_ocr)
	if table_m3j is not None:
		flow_values_j.append(table_m3j)
		if table_source:
			debug_sources.append(table_source)

	flow_labeled_value = _extract_numeric_from_labeled_lines(text_ocr, r"debit|qmoy|qmax|q\b")
	if flow_labeled_value is not None:
		norm_text = _normalize_for_search(text_ocr)
		if re.search(r"\bl/s\b", norm_text):
			converted = _convert_flow_to_m3j_m3h(flow_labeled_value, "l/s")
		elif re.search(r"\bm3/h\b", norm_text):
			converted = _convert_flow_to_m3j_m3h(flow_labeled_value, "m3/h")
		elif re.search(r"\bm3/j\b", norm_text):
			converted = _convert_flow_to_m3j_m3h(flow_labeled_value, "m3/j")
		else:
			converted = None
		if converted:
			m3_j, _m3_h = converted
			flow_values_j.append(m3_j)
			debug_sources.append(f"labeled_flow:{flow_labeled_value}")

	# UDI: ne pas confondre volume de référence avec débit.
	# On extrait le volume explicitement dans un champ dédié.
	volume_patterns = [
		r"volume\s+de\s+r[ée]f[ée]rence\s*([0-9][0-9\s.,]*)\s*(m[³3]\s*/\s*j(?:our)?)",
		r"volume\s+journalier\s*([0-9][0-9\s.,]*)\s*(m[³3]\s*/\s*j(?:our)?)",
	]
	for searchable in search_flats:
		for pattern in volume_patterns:
			m = re.search(pattern, searchable, re.IGNORECASE)
			if not m:
				continue
			vol = _parse_float(m.group(1))
			if vol is not None:
				result["volume_reference_m3_j"] = vol
				debug_sources.append(f"volume_m3j:{vol}")
				break
		if result.get("volume_reference_m3_j") is not None:
			break

	if flow_values_j:
		result["debit_m3_j"] = max(flow_values_j)
	if debug_sources:
		result["_debug_flow_sources"] = debug_sources[:8]

	if result.get("volume_reservoir_m3") is None:
		reservoir_volumes: list[float] = []
		for m in re.finditer(r"reservoir[\s\S]{0,120}?([0-9]+(?:[.,][0-9]+)?)\s*m[³3]", flat_norm, re.IGNORECASE):
			v = _parse_float(m.group(1))
			if v is not None:
				reservoir_volumes.append(float(v))
		for m in re.finditer(r"([0-9]+(?:[.,][0-9]+)?)\s*m[³3][\s\S]{0,120}?reservoir", flat_norm, re.IGNORECASE):
			v = _parse_float(m.group(1))
			if v is not None:
				reservoir_volumes.append(float(v))
		line_volume = _extract_numeric_from_labeled_lines(text_ocr, r"volume\s+reservoir|reservoir", max_scan_lines=1)
		if line_volume is not None and line_volume > 5:
			reservoir_volumes.append(float(line_volume))
		if reservoir_volumes:
			result["volume_reservoir_m3"] = max(reservoir_volumes)

	head_patterns = [
		r"hauteur\s+de\s+chute\s*[:=\-]?\s*([0-9][0-9\s.,]*)\s*m",
		r"d[ée]nivel[ée]\s*[:=\-]?\s*([0-9][0-9\s.,]*)\s*m",
		r"chute\s+brute\s*[:=\-]?\s*([0-9][0-9\s.,]*)\s*m",
		r"chute\s+nette\s*[:=\-]?\s*([0-9][0-9\s.,]*)\s*m",
		r"\bchute\s*[:=\-]?\s*([0-9][0-9\s.,]*)\s*m",
		r"\bhmt\s*[:=\-]?\s*([0-9][0-9\s.,]*)\s*m",
		r"\bΔh\s*[:=\-]?\s*([0-9][0-9\s.,]*)\s*m",
		r"\bdh\s*[:=\-]?\s*([0-9][0-9\s.,]*)\s*m",
	]

	if result.get("hauteur_chute_estimee_m") is None:
		for searchable in search_flats:
			for pattern in head_patterns:
				head_match = re.search(pattern, searchable, re.IGNORECASE)
				if head_match:
					head_value = _parse_float(head_match.group(1))
					if head_value is not None and abs(float(head_value)) <= MAX_PLAUSIBLE_HEAD_M:
						result["hauteur_chute_estimee_m"] = head_value
						break
			if result.get("hauteur_chute_estimee_m") is not None:
				break

	if result.get("denivele_source_reservoir_m") is None:
		labeled_head = _extract_numeric_from_labeled_lines(text_ocr, r"denivele|hauteur\s+de\s+chute|\bhmt\b|\bdh\b", max_scan_lines=1)
		if labeled_head is not None and abs(labeled_head) <= MAX_PLAUSIBLE_HEAD_M:
			result["denivele_source_reservoir_m"] = round(float(labeled_head), 3)
			if result.get("denivele_estime_m") is None:
				result["denivele_estime_m"] = round(abs(float(labeled_head)), 3)
			if result.get("hauteur_chute_estimee_m") is None:
				result["hauteur_chute_estimee_m"] = round(float(labeled_head), 3)
				result["_debug_head_source"] = "labeled_head"

	if result.get("hauteur_chute_estimee_m") is None:
		amont = None
		aval = None
		amont_match = re.search(r"pression\s+amont\s*[:=\-]?\s*([0-9][0-9\s.,]*)\s*bar", flat, re.IGNORECASE)
		aval_match = re.search(r"pression\s+aval\s*[:=\-]?\s*([0-9][0-9\s.,]*)\s*bar", flat, re.IGNORECASE)
		if amont_match:
			amont = _parse_float(amont_match.group(1))
		if aval_match:
			aval = _parse_float(aval_match.group(1))
		if amont is not None and aval is not None and amont > aval:
			estimated = round((amont - aval) * 10, 3)
			if abs(estimated) <= MAX_PLAUSIBLE_HEAD_M:
				result["hauteur_chute_estimee_m"] = estimated
			result["_debug_head_source"] = "pression_amont_aval_bar"

	norm_text = _normalize_for_search(text_ocr)

	local_drops: list[float] = []
	local_signed_drops: list[float] = []
	local_altitudes: list[float] = []

	local_pair_patterns = [
		r"source[\s\S]{0,90}?([0-9]{3,4})\s*m\s*ngf[\s\S]{0,90}?reservoir[\s\S]{0,90}?([0-9]{3,4})\s*m\s*ngf",
		r"reservoir[\s\S]{0,90}?([0-9]{3,4})\s*m\s*ngf[\s\S]{0,90}?source[\s\S]{0,90}?([0-9]{3,4})\s*m\s*ngf",
	]

	for pattern in local_pair_patterns:
		for match in re.finditer(pattern, norm_text, re.IGNORECASE):
			v1 = _parse_float(match.group(1))
			v2 = _parse_float(match.group(2))
			if v1 is None or v2 is None:
				continue
			local_altitudes.extend([v1, v2])
			if "source" in pattern and "reservoir" in pattern and pattern.index("source") < pattern.index("reservoir"):
				signed_drop = v1 - v2
			else:
				signed_drop = v2 - v1
			local_signed_drops.append(signed_drop)
			drop = abs(signed_drop)
			if drop > 0:
				local_drops.append(drop)

	if local_altitudes:
		result["altitudes_ngf_m"] = sorted(set(local_altitudes), reverse=True)

	if local_drops:
		best_drop = max(local_drops)
		if result.get("denivele_estime_m") is None:
			result["denivele_estime_m"] = round(best_drop, 3)
		if local_signed_drops:
			best_signed = max(local_signed_drops, key=lambda x: abs(x))
			if result.get("denivele_source_reservoir_m") is None:
				result["denivele_source_reservoir_m"] = round(best_signed, 3)
		if result.get("hauteur_chute_estimee_m") is None:
			if best_signed > 0:
				# Only a positive source->reservoir difference can be interpreted as available head.
				result["hauteur_chute_estimee_m"] = round(best_signed, 3)
				result["_debug_head_source"] = "ngf_source_reservoir_local_positive"
				if result.get("potentiel_hydraulique") is None:
					result["potentiel_hydraulique"] = True
			else:
				# Keep signed negative head to make non-exploitable cases explicit.
				result["hauteur_chute_estimee_m"] = round(best_signed, 3)
				result["_debug_head_source"] = "ngf_source_reservoir_local_negative"
				result["potentiel_hydraulique"] = False
	elif not local_altitudes and not sites_udi and not result.get("reservoirs_udi"):
		ngf_values: list[float] = []
		for match in re.finditer(r"([0-9]{3,4})\s*m\s*ngf", norm_text, re.IGNORECASE):
			value = _parse_float(match.group(1))
			if value is not None:
				ngf_values.append(value)

		if ngf_values:
			unique_altitudes = sorted(set(ngf_values), reverse=True)
			result["altitudes_ngf_m"] = unique_altitudes
			if len(unique_altitudes) >= 2:
				if result.get("denivele_estime_m") is None:
					result["denivele_estime_m"] = round(max(unique_altitudes) - min(unique_altitudes), 3)
				if result.get("hauteur_chute_estimee_m") is None:
					candidate_head = result["denivele_estime_m"]
					if isinstance(candidate_head, (int, float)) and abs(float(candidate_head)) <= MAX_PLAUSIBLE_HEAD_M:
						result["hauteur_chute_estimee_m"] = candidate_head
						result["_debug_head_source"] = "ngf_delta_global"

	# Keep consistency between head sign and hydro availability.
	head = result.get("hauteur_chute_estimee_m")
	if isinstance(head, (int, float)):
		if head > 0:
			result["potentiel_hydraulique"] = True
		elif head < 0:
			result["potentiel_hydraulique"] = False

	points = []
	for m in re.finditer(r"([^\n]{0,100}(?:brise[-\s]?charge|chambre\s+de\s+r[ée]duction|r[ée]ducteur\s+de\s+pression)[^\n]{0,100})", text_ocr, re.IGNORECASE):
		line = _clean_spaces(m.group(1))
		if line and line not in points:
			points.append(line)
	if points:
		result["points_pression_reduction"] = points[:10]

	emplacements = []
	for line in points[:10]:
		emplacements.append({
			"site": line,
			"justification": "Point hydraulique mentionné dans le document",
		})
	if emplacements:
		result["emplacements_turbine_potentiels"] = emplacements

	legend_elements = legend_signals.get("elements_interessants_micro_hydro") or []
	if isinstance(legend_elements, list) and legend_elements:
		result["elements_interessants_micro_hydro"] = legend_elements[:12]

	constraints: list[str] = []
	constraint_patterns = [
		r"([^\n]{0,140}(?:diam[èe]tre|dn\s*\d+|fonte|pehd|pvc|acier)[^\n]{0,140})",
		r"([^\n]{0,140}(?:pression\s+amont|pression\s+aval|\bbar\b)[^\n]{0,140})",
		r"([^\n]{0,140}(?:clapet|vanne|r[ée]ducteur\s+de\s+pression|r[ée]gulateur\s+de\s+pression|brise[-\s]?charge)[^\n]{0,140})",
		r"([^\n]{0,140}(?:altitude|ngf|d[ée]nivel[ée]|hauteur\s+de\s+chute)[^\n]{0,140})",
	]
	for pattern in constraint_patterns:
		for m in re.finditer(pattern, text_ocr, re.IGNORECASE):
			line = _clean_spaces(m.group(1))
			if len(line) < 8:
				continue
			if line not in constraints:
				constraints.append(line)
			if len(constraints) >= 12:
				break
		if len(constraints) >= 12:
			break

	if constraints:
		result["contraintes_techniques"] = constraints

	logger.debug(
		"UDI extraction summary nom=%s debit_m3_j=%s volume_m3=%s denivele_signed=%s reducers=%s",
		result.get("nom_udi"),
		result.get("debit_m3_j"),
		result.get("volume_reservoir_m3"),
		result.get("denivele_source_reservoir_m"),
		result.get("nombre_reducteurs_pression"),
	)

	return result


def _extract_udi_sites_from_text(document_text: str) -> list[dict[str, Any]]:
	text = (document_text or "").replace("\r\n", "\n")
	text_for_names = re.sub(r"(?<=[a-zà-öø-ÿ])(?=[A-ZÀ-ÖØ-Þ])", " ", text)
	text_for_names = re.sub(r"(?<!\n)\s*(UDI\s*[0-9]{1,3}\b)", r"\n\1", text_for_names, flags=re.IGNORECASE)

	def _build_site_name(udi_number: str, raw_name: str) -> str:
		candidate = _clean_spaces(raw_name)
		candidate = re.sub(r"(?<=[a-zà-öø-ÿ])(?=[A-ZÀ-ÖØ-Þ])", " ", candidate)
		candidate = _clean_spaces(candidate)
		candidate = re.sub(
			r"\b(sch[ée]ma\s+directeur|d['’]?alimentation\s+en\s+eau\s+potable|d[ée]partement|communaut[ée]\s+de\s+communes|legend[e]?|format\s*:).*$",
			"",
			candidate,
			flags=re.IGNORECASE,
		)
		candidate = _clean_spaces(candidate).strip("- ")

		parts: list[str] = []
		commune_match = re.search(
			r"commune\s+de\s+([A-Za-zÀ-ÖØ-öø-ÿ'\-\s]{2,80}?)(?=(?:r[ée]servoir|sch[ée]ma|d['’]?alimentation|d[ée]partement|communaut[ée]|$))",
			candidate,
			re.IGNORECASE,
		)
		if commune_match:
			commune = _clean_spaces(commune_match.group(1)).strip("- ")
			if commune:
				parts.append(f"Commune de {commune}")

		reservoir_match = re.search(
			r"r[ée]servoir\s+([A-Za-zÀ-ÖØ-öø-ÿ'\-\s]{2,80}?)(?=(?:sch[ée]ma|d['’]?alimentation|d[ée]partement|communaut[ée]|$))",
			candidate,
			re.IGNORECASE,
		)
		if reservoir_match:
			reservoir_name = _clean_spaces(reservoir_match.group(1)).strip("- ")
			if reservoir_name:
				parts.append(f"Reservoir {reservoir_name}")

		if parts:
			return f"UDI {udi_number} - {' - '.join(parts)}"

		if candidate:
			return f"UDI {udi_number} - {candidate[:120]}"

		return f"UDI {udi_number}"

	def _site_entry(site_name: str, segment: str | None = None) -> dict[str, Any]:
		seg = segment or ""
		seg_norm = _normalize_for_search(seg)
		source_alt = None
		reservoir_alt = None

		def _collect_hits(text_value: str, patterns: list[str]) -> list[tuple[int, float]]:
			hits: list[tuple[int, float]] = []
			for pattern in patterns:
				for m in re.finditer(pattern, text_value, re.IGNORECASE):
					v = _parse_float(m.group(1))
					if v is not None:
						hits.append((m.start(), float(v)))
			return hits

		source_hits_primary = _collect_hits(seg_norm, [
			r"source[\s\S]{0,220}?tn\s*:?\s*([0-9]{3,4})\s*m\s*ngf",
			r"source[\s\S]{0,160}?([0-9]{3,4})\s*m\s*ngf",
		])
		source_hits_fallback = _collect_hits(seg_norm, [
			r"([0-9]{3,4})\s*m\s*ngf[\s\S]{0,100}?source",
		])
		source_hits = source_hits_primary or source_hits_fallback

		reservoir_hits_primary = _collect_hits(seg_norm, [
			r"reservoir[\s\S]{0,220}?tn\s*:?\s*([0-9]{3,4})\s*m\s*ngf",
			r"reservoir[\s\S]{0,160}?([0-9]{3,4})\s*m\s*ngf",
		])
		reservoir_hits_fallback = _collect_hits(seg_norm, [
			r"([0-9]{3,4})\s*m\s*ngf[\s\S]{0,100}?reservoir",
		])
		reservoir_hits = reservoir_hits_primary or reservoir_hits_fallback

		if source_hits and reservoir_hits:
			candidate_pairs: list[tuple[int, float, float]] = []
			for src_pos, src_val in source_hits:
				for res_pos, res_val in reservoir_hits:
					distance = abs(src_pos - res_pos)
					if distance <= 1200:
						candidate_pairs.append((distance, src_val, res_val))

			if candidate_pairs:
				_, source_alt, reservoir_alt = min(candidate_pairs, key=lambda p: p[0])

		if source_alt is None and source_hits:
			source_alt = source_hits[0][1]
		if reservoir_alt is None and reservoir_hits:
			reservoir_alt = reservoir_hits[0][1]

		denivele_signed = None
		if source_alt is not None and reservoir_alt is not None:
			denivele_signed = round(source_alt - reservoir_alt, 3)

		volume_candidates: list[float] = []
		# Segment-first volume parsing keeps values tied to the current UDI block.
		for m in re.finditer(r"\b([0-9]+(?:[.,][0-9]+)?)\s*m[³3]\b", seg_norm, re.IGNORECASE):
			v = _parse_float(m.group(1))
			if v is None:
				continue
			context = seg_norm[max(0, m.start() - 60) : min(len(seg_norm), m.end() + 60)]
			if re.search(r"reservoir|r[ée]servoir", context, re.IGNORECASE):
				volume_candidates.append(float(v))
		for m in re.finditer(r"([0-9]+(?:[.,][0-9]+)?)\s*m[³3][\s\S]{0,180}?reservoir", seg_norm, re.IGNORECASE):
			v = _parse_float(m.group(1))
			if v is not None:
				volume_candidates.append(float(v))
		for m in re.finditer(r"reservoir[\s\S]{0,180}?([0-9]+(?:[.,][0-9]+)?)\s*m[³3]", seg_norm, re.IGNORECASE):
			v = _parse_float(m.group(1))
			if v is not None:
				volume_candidates.append(float(v))

		ordered_unique_volumes: list[float] = []
		for v in volume_candidates:
			if v not in ordered_unique_volumes:
				ordered_unique_volumes.append(v)
		volume_reservoir = ordered_unique_volumes[0] if ordered_unique_volumes else None

		if volume_reservoir is None:
			site_suffix = _clean_spaces(re.sub(r"^UDI\s*[0-9]{1,3}\s*[-:]?", "", site_name, flags=re.IGNORECASE)).strip("- ,")
			if site_suffix:
				suffix_norm = _normalize_for_search(site_suffix)
				near_name_patterns = [
					rf"{re.escape(suffix_norm)}[\s\S]{{0,80}}?([0-9]+(?:[.,][0-9]+)?)\s*m[³3]",
					rf"([0-9]+(?:[.,][0-9]+)?)\s*m[³3][\s\S]{{0,80}}?{re.escape(suffix_norm)}",
				]
				for pattern in near_name_patterns:
					m = re.search(pattern, seg_norm, re.IGNORECASE)
					if not m:
						continue
					v = _parse_float(m.group(1))
					if v is not None:
						volume_reservoir = float(v)
						break

		return {
			"site": site_name,
			"source_altitude_ngf_m": source_alt,
			"reservoir_altitude_ngf_m": reservoir_alt,
			"denivele_source_reservoir_m": denivele_signed,
			"source_au_dessus_reservoir": denivele_signed > 0 if denivele_signed is not None else None,
			"volume_reservoir_m3": volume_reservoir,
		}

	def _site_entry_score(entry: dict[str, Any]) -> int:
		score = 0
		if isinstance(entry.get("source_altitude_ngf_m"), (int, float)):
			score += 2
		if isinstance(entry.get("reservoir_altitude_ngf_m"), (int, float)):
			score += 2
		if isinstance(entry.get("denivele_source_reservoir_m"), (int, float)):
			score += 3
		if isinstance(entry.get("volume_reservoir_m3"), (int, float)):
			score += 1
		return score

	header_lines = [line.strip() for line in text.split("\n") if line.strip()][:6]
	header_text = ""
	for line in header_lines:
		if re.search(r"\budi\b", line, re.IGNORECASE):
			header_text = line
			break
	if not header_text:
		header_text = " ".join(header_lines[:2])
	header_sites: list[str] = []
	header_expanded = re.sub(r"\s*(?:&|et)\s*([0-9]{1,2})\b", r" ; UDI \1 ", header_text, flags=re.IGNORECASE)
	for hm in re.finditer(r"UDI\s*([0-9]{1,2})\s*[-:]?\s*([^;]{0,120})", header_expanded, re.IGNORECASE):
		number = hm.group(1)
		name_part = _clean_spaces(hm.group(2))
		site_name = _build_site_name(number, name_part)
		if site_name not in header_sites:
			header_sites.append(site_name)

	matches = list(re.finditer(r"(?mi)^\s*udi\s*([0-9]{1,2})\s*[-:]?\s*([^\n]{0,180})", text_for_names))
	if not matches:
		return [_site_entry(name) for name in header_sites]

	site_entries_by_key: dict[str, dict[str, Any]] = {}
	site_scores_by_key: dict[str, int] = {}
	site_order: list[str] = []
	for i, match in enumerate(matches):
		start = match.start()
		end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
		segment = text[start:end]

		udi_number = match.group(1)
		udi_name_part = _clean_spaces(match.group(2))
		udi_name_part = re.sub(r"\s*(?:&|et)\s*[0-9]{1,2}\b.*$", "", udi_name_part, flags=re.IGNORECASE).strip()
		site_name = _build_site_name(udi_number, udi_name_part)
		match_num = re.search(r"\bUDI\s*([0-9]{1,3})\b", site_name, re.IGNORECASE)
		if match_num:
			site_key = f"udi-{match_num.group(1)}"
		else:
			site_key = re.sub(r"[^a-z0-9]+", " ", _normalize_for_search(site_name)).strip()
		entry = _site_entry(site_name, segment)
		entry_score = _site_entry_score(entry)

		if site_key not in site_entries_by_key:
			site_entries_by_key[site_key] = entry
			site_scores_by_key[site_key] = entry_score
			site_order.append(site_key)
			continue

		if entry_score > site_scores_by_key.get(site_key, -1):
			site_entries_by_key[site_key] = entry
			site_scores_by_key[site_key] = entry_score

	sites = [site_entries_by_key[k] for k in site_order if k in site_entries_by_key]

	if len(sites) == 1 and header_sites:
		existing_names = {str(s.get("site", "")).lower() for s in sites}
		for name in header_sites:
			if name.lower() not in existing_names:
				sites.append(_site_entry(name))
				if len(sites) >= 2:
					break

	return sites


def _extract_udi_reservoirs_from_text(document_text: str, sites_udi: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
	text = (document_text or "").replace("\r\n", "\n")
	lines = [line.strip() for line in text.split("\n") if line.strip()]
	sites = sites_udi or []

	site_by_number: dict[str, dict[str, Any]] = {}
	for site in sites:
		if not isinstance(site, dict):
			continue
		site_name = str(site.get("site", "")).strip()
		m = re.search(r"\bUDI\s*([0-9]{1,2})\b", site_name, re.IGNORECASE)
		if m:
			site_by_number[m.group(1)] = site

	def _find_source_alt(segment: str) -> float | None:
		for pattern in [
			r"source[\s\S]{0,220}?([0-9]{3,4})\s*m\s*ngf",
			r"captage[\s\S]{0,220}?([0-9]{3,4})\s*m\s*ngf",
		]:
			m = re.search(pattern, segment, re.IGNORECASE)
			if m:
				v = _parse_float(m.group(1))
				if v is not None:
					return float(v)
		return None

	def _find_reservoir_alt(segment: str) -> float | None:
		alt_hits: list[tuple[int, float]] = []
		for m in re.finditer(r"([0-9]{3,4})\s*m\s*ngf", segment, re.IGNORECASE):
			v = _parse_float(m.group(1))
			if v is not None:
				alt_hits.append((m.start(), float(v)))
		if not alt_hits:
			return None

		res_anchors = [m.start() for m in re.finditer(r"r[ée]servoir", segment, re.IGNORECASE)]
		if not res_anchors:
			return alt_hits[0][1]

		candidate_after_anchor: list[tuple[int, float]] = []
		for anchor in res_anchors:
			after = [(pos - anchor, val) for pos, val in alt_hits if pos >= anchor]
			if after:
				candidate_after_anchor.append(min(after, key=lambda item: item[0]))

		if candidate_after_anchor:
			return min(candidate_after_anchor, key=lambda item: item[0])[1]

		closest = min(
			((abs(pos - anchor), val) for anchor in res_anchors for pos, val in alt_hits),
			key=lambda item: item[0],
		)
		return closest[1]

	global_source_alt = _find_source_alt(text)
	current_udi_number = None
	current_source_alt = global_source_alt

	def _reservoir_name_from_window(base_line: str, next_lines: list[str]) -> str:
		merged = " ".join([base_line] + next_lines)
		merged = _clean_spaces(merged)
		name_match = re.search(
			r"r[ée]servoir\s*de\s*([A-Za-zÀ-ÖØ-öø-ÿ'\- ]{2,60}?)(?=\s*(?:tn|[0-9]{3,4}\s*m\s*ngf|source|udi|$))",
			merged,
			re.IGNORECASE,
		)
		if name_match:
			return _clean_spaces(name_match.group(1)).strip(" -")

		if re.search(r"r[ée]servoir\s*de\s*$|r[ée]servoir\s*de(?!\s*[A-Za-zÀ-ÖØ-öø-ÿ])", base_line, re.IGNORECASE):
			for candidate in next_lines:
				cand = _clean_spaces(candidate)
				ngf_name = re.search(r"[0-9]{3,4}\s*m\s*ngf\s*([A-Za-zÀ-ÖØ-öø-ÿ'\- ]{2,60})$", cand, re.IGNORECASE)
				if ngf_name:
					name_tail = _clean_spaces(ngf_name.group(1)).strip(" -")
					if name_tail:
						return name_tail
				cand = re.sub(r"\btn\b.*$", "", cand, flags=re.IGNORECASE).strip()
				cand = re.sub(r"[0-9]{3,4}\s*m\s*ngf.*$", "", cand, flags=re.IGNORECASE).strip()
				if re.fullmatch(r"[A-Za-zÀ-ÖØ-öø-ÿ'\- ]{2,60}", cand or ""):
					return cand.strip(" -")

		return ""

	reservoirs: list[dict[str, Any]] = []
	for idx, line in enumerate(lines):
		udi_line = re.search(r"\bUDI\s*([0-9]{1,2})\b", line, re.IGNORECASE)
		if udi_line:
			current_udi_number = udi_line.group(1)
			if current_udi_number in site_by_number:
				src = site_by_number[current_udi_number].get("source_altitude_ngf_m")
				if isinstance(src, (int, float)):
					current_source_alt = float(src)

		if re.search(r"\b(source|captage)\b", line, re.IGNORECASE):
			src_line = _find_source_alt("\n".join(lines[idx : idx + 2]))
			if src_line is not None:
				current_source_alt = src_line

		if not re.search(r"\breservoir\b|\br[ée]servoir\b", line, re.IGNORECASE):
			continue

		window = "\n".join(lines[idx : idx + 3])
		if not re.search(r"r[ée]servoir\s*de", window, re.IGNORECASE):
			# Ignore generic legend/equipment labels (e.g. "Reservoir UV").
			continue
		res_alt = _find_reservoir_alt(window)

		vol = None
		vol_match = re.search(r"([0-9]+(?:[.,][0-9]+)?)\s*m[³3]", window, re.IGNORECASE)
		if vol_match:
			vol = _parse_float(vol_match.group(1))

		site_name = None
		if current_udi_number and current_udi_number in site_by_number:
			site_name = str(site_by_number[current_udi_number].get("site", "")).strip() or None
		if site_name is None and sites:
			site_name = str(sites[0].get("site", "")).strip() or None

		source_alt = current_source_alt
		if source_alt is None and current_udi_number and current_udi_number in site_by_number:
			src = site_by_number[current_udi_number].get("source_altitude_ngf_m")
			if isinstance(src, (int, float)):
				source_alt = float(src)

		signed = None
		head = None
		if isinstance(source_alt, (int, float)) and isinstance(res_alt, (int, float)):
			signed = round(float(source_alt) - float(res_alt), 3)
			if signed > 0:
				head = signed

		next_lines = [lines[idx + 1]] if idx + 1 < len(lines) else []
		if idx + 2 < len(lines):
			next_lines.append(lines[idx + 2])
		res_name = _reservoir_name_from_window(line, next_lines)
		if res_name:
			reservoir_label = f"Reservoir de {res_name}"
		else:
			reservoir_label = _clean_spaces(re.sub(r"\s+", " ", line))[:120]
			reservoir_label = re.sub(r"\bTN\b.*$", "", reservoir_label, flags=re.IGNORECASE).strip(" -")
			if re.search(r"r[ée]servoir\s*de\s*$", reservoir_label, re.IGNORECASE) and site_name:
				site_suffix = re.sub(r"^UDI\s*[0-9]{1,2}\s*-\s*", "", site_name, flags=re.IGNORECASE).strip()
				if site_suffix:
					reservoir_label = f"Reservoir de {site_suffix}"
		reservoirs.append(
			{
				"site_udi": site_name,
				"reservoir": reservoir_label,
				"source_altitude_ngf_m": float(source_alt) if isinstance(source_alt, (int, float)) else None,
				"reservoir_altitude_ngf_m": float(res_alt) if isinstance(res_alt, (int, float)) else None,
				"denivele_source_reservoir_m": signed,
				"hauteur_chute_disponible_m": head,
				"volume_reservoir_m3": float(vol) if isinstance(vol, (int, float)) else None,
			}
		)

	if not reservoirs:
		for site in sites:
			if not isinstance(site, dict):
				continue
			src = _parse_float(site.get("source_altitude_ngf_m"))
			res = _parse_float(site.get("reservoir_altitude_ngf_m"))
			signed = round(src - res, 3) if src is not None and res is not None else None
			head = signed if isinstance(signed, (int, float)) and signed > 0 else None
			reservoirs.append(
				{
					"site_udi": str(site.get("site", "")).strip() or None,
					"reservoir": str(site.get("site", "")).strip() or "Reservoir",
					"source_altitude_ngf_m": src,
					"reservoir_altitude_ngf_m": res,
					"denivele_source_reservoir_m": signed,
					"hauteur_chute_disponible_m": head,
					"volume_reservoir_m3": _parse_float(site.get("volume_reservoir_m3")),
				}
			)

	seen: set[str] = set()
	normalized: list[dict[str, Any]] = []
	for r in reservoirs:
		label_norm = _normalize_for_search(str(r.get("reservoir") or ""))
		label_norm = re.sub(r"\breservoir\s+de\b", "", label_norm).strip()
		key = "|".join(
			[
				str(r.get("site_udi") or ""),
				label_norm,
				str(r.get("reservoir_altitude_ngf_m") or ""),
			]
		)
		if key in seen:
			continue
		seen.add(key)
		normalized.append(r)

	return normalized


def _apply_hydro_flow_filter(extraction_json: dict[str, Any]) -> dict[str, Any]:
	flow_m3_j = _parse_float(extraction_json.get("debit_m3_j"))
	if flow_m3_j is None:
		return extraction_json

	if flow_m3_j < HYDRO_MIN_FLOW_M3_J:
		extraction_json["potentiel_hydraulique"] = False

	return extraction_json


def _reconcile_udi_hydraulic_consistency(merged_json: dict[str, Any], rule_based: dict[str, Any]) -> dict[str, Any]:
	# Rule-based source/reservoir parsing is more reliable than LLM guesses for signed head.
	rule_sites = rule_based.get("sites_udi")
	if isinstance(rule_sites, list) and rule_sites:
		merged_json["sites_udi"] = rule_sites

	rule_reservoirs = rule_based.get("reservoirs_udi")
	if isinstance(rule_reservoirs, list) and rule_reservoirs:
		merged_json["reservoirs_udi"] = rule_reservoirs

	rule_signed = _parse_float(rule_based.get("denivele_source_reservoir_m"))
	rule_head = _parse_float(rule_based.get("hauteur_chute_estimee_m"))
	rule_abs = _parse_float(rule_based.get("denivele_estime_m"))

	if rule_signed is not None:
		merged_json["denivele_source_reservoir_m"] = rule_signed
		if rule_abs is None:
			rule_abs = abs(rule_signed)
	if rule_abs is not None:
		merged_json["denivele_estime_m"] = rule_abs

	if rule_head is not None:
		merged_json["hauteur_chute_estimee_m"] = rule_head
	elif rule_signed is not None:
		merged_json["hauteur_chute_estimee_m"] = rule_signed

	head = _parse_float(merged_json.get("hauteur_chute_estimee_m"))
	signed = _parse_float(merged_json.get("denivele_source_reservoir_m"))

	if head is not None and abs(head) > MAX_PLAUSIBLE_HEAD_M:
		if signed is not None and abs(signed) <= MAX_PLAUSIBLE_HEAD_M:
			head = signed
			merged_json["hauteur_chute_estimee_m"] = head
		elif rule_head is not None and abs(rule_head) <= MAX_PLAUSIBLE_HEAD_M:
			head = rule_head
			merged_json["hauteur_chute_estimee_m"] = head
		else:
			merged_json["hauteur_chute_estimee_m"] = None
			head = None

	if head is not None and signed is not None and abs(head - signed) > 5:
		if abs(signed) <= MAX_PLAUSIBLE_HEAD_M:
			merged_json["hauteur_chute_estimee_m"] = signed
			head = signed

	if isinstance(head, (int, float)):
		if head > 0:
			merged_json["potentiel_hydraulique"] = True
		elif head < 0:
			merged_json["potentiel_hydraulique"] = False

	return merged_json


def _merge_with_udi_schema(candidate: dict[str, Any]) -> dict[str, Any]:
	schema = _udi_json_schema_template()
	for key in schema.keys():
		if key in candidate:
			schema[key] = candidate[key]

	if not isinstance(schema.get("communes"), list):
		schema["communes"] = []
	if not isinstance(schema.get("altitudes_ngf_m"), list):
		schema["altitudes_ngf_m"] = []
	if not isinstance(schema.get("points_pression_reduction"), list):
		schema["points_pression_reduction"] = []
	if not isinstance(schema.get("emplacements_turbine_potentiels"), list):
		schema["emplacements_turbine_potentiels"] = []
	if not isinstance(schema.get("elements_interessants_micro_hydro"), list):
		schema["elements_interessants_micro_hydro"] = []
	if not isinstance(schema.get("contraintes_techniques"), list):
		schema["contraintes_techniques"] = []
	if not isinstance(schema.get("sites_udi"), list):
		schema["sites_udi"] = []
	if not isinstance(schema.get("reservoirs_udi"), list):
		schema["reservoirs_udi"] = []
	if not isinstance(schema.get("description_reservoirs"), list):
		schema["description_reservoirs"] = []
	if not isinstance(schema.get("volume_reservoir_confidence_by_site"), list):
		schema["volume_reservoir_confidence_by_site"] = []

	if str(schema.get("volume_reservoir_confidence") or "").lower() not in {"high", "medium", "low"}:
		schema["volume_reservoir_confidence"] = "low"

	for key in ["hauteur_chute_estimee_m", "denivele_source_reservoir_m", "denivele_estime_m", "volume_reference_m3_j", "debit_m3_j", "volume_reservoir_m3", "nombre_brise_charge", "nombre_reducteurs_pression"]:
		if schema.get(key) is not None:
			schema[key] = _parse_float(schema.get(key))

	if schema.get("nombre_brise_charge") is not None:
		schema["nombre_brise_charge"] = int(schema["nombre_brise_charge"])
	if schema.get("nombre_reducteurs_pression") is not None:
		schema["nombre_reducteurs_pression"] = int(schema["nombre_reducteurs_pression"])

	if schema.get("presence_reducteurs_pression") not in (True, False, None):
		schema["presence_reducteurs_pression"] = None

	if schema.get("potentiel_hydraulique") not in (True, False, None):
		schema["potentiel_hydraulique"] = None

	for numeric_key in ["hauteur_chute_estimee_m", "denivele_source_reservoir_m", "denivele_estime_m", "volume_reference_m3_j", "debit_m3_j", "volume_reservoir_m3"]:
		if _is_missing(schema.get(numeric_key)):
			schema[numeric_key] = None

	normalized_sites: list[dict[str, Any]] = []
	for raw_site in schema.get("sites_udi") or []:
		if not isinstance(raw_site, dict):
			continue
		site_conf = str(raw_site.get("volume_reservoir_confidence") or "").lower()
		if site_conf not in {"high", "medium", "low"}:
			site_conf = "low"
		normalized_sites.append(
			{
				"site": str(raw_site.get("site", "")).strip(),
				"source_altitude_ngf_m": _parse_float(raw_site.get("source_altitude_ngf_m")),
				"reservoir_altitude_ngf_m": _parse_float(raw_site.get("reservoir_altitude_ngf_m")),
				"denivele_source_reservoir_m": _parse_float(raw_site.get("denivele_source_reservoir_m")),
				"source_au_dessus_reservoir": raw_site.get("source_au_dessus_reservoir") if raw_site.get("source_au_dessus_reservoir") in (True, False, None) else None,
				"volume_reservoir_m3": _parse_float(raw_site.get("volume_reservoir_m3")),
				"volume_reservoir_confidence": site_conf,
			}
		)
	schema["sites_udi"] = normalized_sites

	normalized_confidence_by_site: list[dict[str, str]] = []
	for item in schema.get("volume_reservoir_confidence_by_site") or []:
		if not isinstance(item, dict):
			continue
		site_name = str(item.get("site") or "").strip()
		level = str(item.get("confidence") or "").lower()
		if level not in {"high", "medium", "low"}:
			continue
		normalized_confidence_by_site.append({"site": site_name, "confidence": level})
	schema["volume_reservoir_confidence_by_site"] = normalized_confidence_by_site

	normalized_reservoirs: list[dict[str, Any]] = []
	for raw_res in schema.get("reservoirs_udi") or []:
		if not isinstance(raw_res, dict):
			continue
		normalized_reservoirs.append(
			{
				"site_udi": str(raw_res.get("site_udi", "")).strip() or None,
				"reservoir": str(raw_res.get("reservoir", "")).strip() or None,
				"source_altitude_ngf_m": _parse_float(raw_res.get("source_altitude_ngf_m")),
				"reservoir_altitude_ngf_m": _parse_float(raw_res.get("reservoir_altitude_ngf_m")),
				"denivele_source_reservoir_m": _parse_float(raw_res.get("denivele_source_reservoir_m")),
				"hauteur_chute_disponible_m": _parse_float(raw_res.get("hauteur_chute_disponible_m")),
				"volume_reservoir_m3": _parse_float(raw_res.get("volume_reservoir_m3")),
			}
		)
	schema["reservoirs_udi"] = normalized_reservoirs

	return schema


def _extract_json_object(response_text: str) -> dict[str, Any]:
	cleaned = response_text.strip()

	fenced = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", cleaned, re.IGNORECASE)
	if fenced:
		cleaned = fenced.group(1)

	try:
		return json.loads(cleaned)
	except json.JSONDecodeError:
		start = cleaned.find("{")
		end = cleaned.rfind("}")
		if start != -1 and end != -1 and end > start:
			return json.loads(cleaned[start : end + 1])
		raise


def _extract_json_and_description(response_text: str) -> tuple[dict[str, Any], str]:
	cleaned = response_text.strip()

	decoder = json.JSONDecoder()
	json_start = cleaned.find("{")
	if json_start != -1:
		try:
			parsed_obj, end_idx = decoder.raw_decode(cleaned[json_start:])
			remainder = cleaned[json_start + end_idx :].strip()
			if remainder.lower().startswith("description"):
				remainder = remainder.split(":", 1)[1].strip() if ":" in remainder else remainder
			if isinstance(parsed_obj, dict):
				return parsed_obj, remainder
		except json.JSONDecodeError:
			pass

	return _extract_json_object(cleaned), ""


def _safe_extract_json_and_description(response_text: str) -> tuple[dict[str, Any], str, str | None]:
	"""Parse LLM output without raising, and return an optional parse warning."""
	cleaned = (response_text or "").strip()
	if not cleaned:
		return {}, "", "Réponse IA vide."

	try:
		parsed_json, description = _extract_json_and_description(cleaned)
		if not isinstance(parsed_json, dict):
			return {}, description, "JSON IA non objet (dict attendu)."
		return parsed_json, description, None
	except json.JSONDecodeError as err:
		snippet = cleaned[:300].replace("\n", " ")
		logger.warning("Réponse IA JSON invalide: %s | extrait=%s", err, snippet)
		return {}, "", f"JSON IA invalide: {err}"


def _merge_with_schema(candidate: dict[str, Any]) -> dict[str, Any]:
	schema = _json_schema_template()
	for key in schema.keys():
		if key in candidate:
			schema[key] = candidate[key]

	if schema.get("potentiel_hydraulique") not in (True, False, None):
		schema["potentiel_hydraulique"] = None

	if not isinstance(schema.get("ouvrages"), list):
		schema["ouvrages"] = []

	if "debit_m3_h" in candidate and schema.get("debit_m3_j") is None:
		maybe_m3_h = _parse_float(candidate.get("debit_m3_h"))
		if maybe_m3_h is not None:
			schema["debit_m3_j"] = round(maybe_m3_h * 24, 3)

	if schema.get("debit_m3_j") is not None:
		schema["debit_m3_j"] = _parse_float(schema.get("debit_m3_j"))

	return schema


class RAGPipeline:
	def __init__(self, groq_model: str = "llama-3.1-8b-instant", api_key: str | None = None):
		self.groq_model = groq_model
		self.groq_api_key = api_key or os.getenv("GROQ_API_KEY")
		if not self.groq_api_key:
			raise ValueError("GROQ_API_KEY introuvable. Ajoute-la dans .env.")
		self.client = Groq(api_key=self.groq_api_key)

	def set_model(self, model_name: str):
		if model_name not in ALLOWED_MODELS:
			raise ValueError(
				f"Modèle '{model_name}' non autorisé. Modèles valides : {', '.join(ALLOWED_MODELS)}"
			)
		self.groq_model = model_name

	def _build_prompt_steu(self, document_text: str) -> str:
		context = _build_focus_context(document_text, max_chars=26000)
		return f"""
Tu es un ingénieur spécialisé en analyse d'infrastructures d'assainissement.

Ta tâche est d'analyser une fiche technique de station d'épuration (type fiche SATESE) et d'en extraire les informations importantes.

Le document peut contenir :
- des tableaux
- des sections techniques
- des données manquantes (ND)
- des informations réparties dans plusieurs parties du texte.

Analyse le document et extrait uniquement les informations utiles sur la station.

Les informations à extraire sont :
- nom de la station
- commune
- capacité de la station (EH)
- année de mise en service
- coordonnées géographiques si présentes
- surface d'infiltration (m²)
- présence et type des ouvrages hydrauliques
- nombre de drains ou casiers
- volume ou débit si présent (priorité au débit en m³/j)
- surface potentiellement disponible pour panneaux solaires
- éléments pouvant indiquer un potentiel de récupération d'énergie hydraulique

Important pour le débit :
- Recherche prioritaire dans la section "charges de référence".
- Extrais le débit en m³/j (mètre cube par jour) si présent.
- Si un débit est indiqué dans une autre unité, convertis-le en m³/j si la conversion est certaine.

Si certaines informations sont absentes, indique null.

Réponds en deux parties :
1) Un JSON structuré avec les données extraites.
2) Une description détaillée de la station en français expliquant :
- le type de station
- les principaux ouvrages
- l'état des équipements
- le fonctionnement de la filière eau
- les éléments importants observés dans la fiche
- une première analyse du potentiel énergétique (solaire ou hydro)

Format de sortie :

JSON :
{json.dumps(_json_schema_template(), ensure_ascii=False, indent=2)}

Rules:
- Keep all keys exactly as provided.
- Use null if unknown.
- Do not add any extra keys.
- Réponds uniquement avec le JSON puis la description technique détaillée.
- La description doit être technique et factuelle.
- Ne fais aucune hypothèse non présente dans le document.
- Si un équipement n'est pas mentionné, indique explicitement : "information non disponible".
- N'invente jamais de potentiel énergétique.
- Si le potentiel énergétique (hydraulique/solaire) n'est pas explicitement documenté, indique qu'il est non documenté.
- N'ajoute aucune valeur, chiffre, équipement, performance ou interprétation absente du document.
- Base chaque élément de la description uniquement sur les informations visibles dans le document.

Technical document:
\"\"\"
{context}
\"\"\"
""".strip()

	def _build_prompt_udi(self, document_text: str) -> str:
		context = _build_focus_context(document_text, max_chars=26000)
		return f"""
Tu es un ingénieur hydraulicien spécialisé en réseaux d'eau potable (UDI).

Ta tâche est d'analyser un document UDI et d'en extraire les informations utiles pour un pré-filtrage d'implantation de micro-turbines hydro.

Extrais uniquement les informations explicitement présentes dans le document.

Champs à extraire (JSON strict) :
{json.dumps(_udi_json_schema_template(), ensure_ascii=False, indent=2)}

Consignes :
- Ne fais aucune hypothèse.
- Si une information n'est pas mentionnée, mets null (ou liste vide selon le type du champ).
- Les "emplacements_turbine_potentiels" doivent reprendre des points/ouvrages explicitement cités (brise-charge, réduction de pression, etc.).
- Distingue strictement volume et débit :
	- `volume_reference_m3_j` pour les volumes journaliers/références,
	- `volume_reservoir_m3` pour le volume de réservoir,
	- `debit_m3_j` uniquement pour les débits.
- Si plusieurs réservoirs sont mentionnés, renseigne `reservoirs_udi` avec un objet par réservoir.
- Renseigne explicitement la présence de réducteurs de pression (`presence_reducteurs_pression` et `nombre_reducteurs_pression`).
- `denivele_source_reservoir_m` doit être signé pour le sens source -> réservoir (positif si source plus haute, négatif sinon).
- N'invente jamais de potentiel énergétique.
- Description technique factuelle uniquement.

Réponds en deux parties :
1) JSON structuré (strictement conforme au schéma)
2) Description technique factuelle en français

Technical document:
\"\"\"
{context}
\"\"\"
""".strip()

	def extract_from_text(self, document_text: str) -> dict[str, Any]:
		if not document_text.strip():
			raise ValueError("Le texte du document est vide.")

		document_type = _detect_document_type(document_text)
		prompt = self._build_prompt_udi(document_text) if document_type == "udi" else self._build_prompt_steu(document_text)
		try:
			completion = self.client.chat.completions.create(
				model=self.groq_model,
				temperature=0,
				max_tokens=900,
				messages=[
					{
						"role": "system",
						"content": (
							"You are a strict technical extraction engine for wastewater station sheets. "
							"Never invent data. Never infer unmentioned equipment. "
							"If information is missing, explicitly state 'information non disponible' in the description and null in JSON. "
							"Do not invent energy potential."
						),
					},
					{"role": "user", "content": prompt},
				],
			)
		except Exception as err:
			error_message = str(err)
			if "model_decommissioned" in error_message or "no longer supported" in error_message:
				raise ValueError(
					f"Le modèle '{self.groq_model}' est décommissionné par Groq. Choisis un autre modèle parmi : {', '.join(ALLOWED_MODELS)}"
				) from err
			raise ValueError(f"Erreur Groq: {error_message}") from err

		content = completion.choices[0].message.content or "{}"
		parsed_json, description, parse_warning = _safe_extract_json_and_description(content)

		if document_type == "udi":
			merged_json = _merge_with_udi_schema(parsed_json)
			rule_based = _extract_udi_fields_from_text(document_text)
		else:
			merged_json = _merge_with_schema(parsed_json)
			rule_based = _extract_satese_fields_from_text(document_text)

		for field, value in rule_based.items():
			if field not in merged_json:
				continue
			if _is_missing(merged_json.get(field)) and not _is_missing(value):
				merged_json[field] = value

		if document_type == "udi":
			merged_json = _reconcile_udi_hydraulic_consistency(merged_json, rule_based)

		if merged_json.get("potentiel_hydraulique") not in (True, False, None):
			merged_json["potentiel_hydraulique"] = None

		if merged_json.get("potentiel_hydraulique") is None and rule_based.get("potentiel_hydraulique") is True:
			merged_json["potentiel_hydraulique"] = True

		merged_json = _apply_hydro_flow_filter(merged_json)

		debug_info = {"llm_parse_warning": parse_warning} if parse_warning else {}
		if document_type == "udi":
			debug_info.update(_collect_udi_debug_signals(document_text))
			if isinstance(rule_based.get("_debug_flow_sources"), list):
				debug_info["flow_sources"] = rule_based.get("_debug_flow_sources")
			if rule_based.get("_debug_head_source"):
				debug_info["head_source"] = rule_based.get("_debug_head_source")

		return {
			"document_type": document_type,
			"json": merged_json,
			"description": description.strip(),
			"debug": debug_info,
		}

	def extract_from_pdf(self, pdf_bytes: bytes, filename: str | None = None) -> dict[str, Any]:
		document_text = extract_text_from_pdf(pdf_bytes)
		if not document_text:
			raise ValueError("Impossible d'extraire du texte du PDF.")
		forced_udi_number = _forced_udi_number_from_filename(filename)
		document_text_for_extraction = _slice_text_to_forced_udi_section(document_text, forced_udi_number)
		payload = self.extract_from_text(document_text_for_extraction)
		if payload.get("document_type") == "udi":
			result_json = payload.get("json") or {}
			blue_rp_count = _detect_blue_rp_symbols_from_pdf(pdf_bytes)
			legend_equipment = _detect_legend_equipment_from_pdf(pdf_bytes)
			symbol_detections = _build_symbol_detections_from_pdf_signals(
				pdf_bytes=pdf_bytes,
				result_json=result_json,
				legend_equipment=legend_equipment,
			)
			symbol_detections.extend(_detect_template_bank_symbols_from_pdf(pdf_bytes, result_json))
			result_json["symbol_detections"] = symbol_detections
			infrastructure_graph = build_infrastructure_graph(symbol_detections)
			result_json["infrastructure_graph"] = infrastructure_graph
			update_udi_fields_from_detections(result_json, symbol_detections)
			if blue_rp_count > 0:
				result_json["presence_reducteurs_pression"] = True
				existing_count = result_json.get("nombre_reducteurs_pression")
				if isinstance(existing_count, (int, float)):
					result_json["nombre_reducteurs_pression"] = max(int(existing_count), blue_rp_count)
				else:
					result_json["nombre_reducteurs_pression"] = blue_rp_count
				points = result_json.get("points_pression_reduction")
				if not isinstance(points, list):
					points = []
				if "RP (symbole bleu)" not in points:
					points.append("RP (symbole bleu)")
				result_json["points_pression_reduction"] = points

			if legend_equipment.get("has_reducer"):
				result_json["presence_reducteurs_pression"] = True
				existing_count = result_json.get("nombre_reducteurs_pression")
				legend_count = int(legend_equipment.get("legend_reducer_count") or 1)
				if isinstance(existing_count, (int, float)):
					result_json["nombre_reducteurs_pression"] = max(int(existing_count), legend_count)
				else:
					result_json["nombre_reducteurs_pression"] = legend_count
				points = result_json.get("points_pression_reduction")
				if not isinstance(points, list):
					points = []
				if "RP/PRV (legende)" not in points:
					points.append("RP/PRV (legende)")
				result_json["points_pression_reduction"] = points

			if legend_equipment.get("has_brise_charge"):
				result_json["presence_brise_charge"] = True
				existing_brise = result_json.get("nombre_brise_charge")
				legend_brise_count = int(legend_equipment.get("legend_brise_charge_count") or 1)
				if isinstance(existing_brise, (int, float)):
					result_json["nombre_brise_charge"] = max(int(existing_brise), legend_brise_count)
				else:
					result_json["nombre_brise_charge"] = legend_brise_count

			debug_info = payload.get("debug") or {}
			if forced_udi_number:
				debug_info["forced_udi_number"] = forced_udi_number
				debug_info["forced_udi_text_trimmed"] = document_text_for_extraction != document_text
			debug_info["rp_blue_symbol_count"] = blue_rp_count
			debug_info["legend_equipment"] = legend_equipment
			debug_info["symbol_detection_count"] = len(symbol_detections)
			payload["debug"] = debug_info
			payload["json"] = result_json

		return payload
