from __future__ import annotations

import json
import os
import re
import unicodedata
from typing import Any

from dotenv import load_dotenv
from groq import Groq
from src.pdf_parser import extract_text_from_pdf

load_dotenv()

HYDRO_MIN_FLOW_M3_J = float(os.getenv("HYDRO_MIN_FLOW_M3_J", "50"))

ALLOWED_MODELS = [
	"llama-3.1-8b-instant",
	"llama-3.3-70b-versatile",
	"openai/gpt-oss-20b",
	"openai/gpt-oss-120b",
]


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
		"presence_brise_charge": None,
		"nombre_brise_charge": None,
		"hauteur_chute_estimee_m": None,
		"denivele_source_reservoir_m": None,
		"denivele_estime_m": None,
		"altitudes_ngf_m": [],
		"volume_reservoir_m3": None,
		"volume_reference_m3_j": None,
		"debit_m3_j": None,
		"points_pression_reduction": [],
		"emplacements_turbine_potentiels": [],
		"contraintes_techniques": [],
		"potentiel_hydraulique": None,
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

	return re.sub(r"\b(?:[A-Za-z]\s+){2,}[A-Za-z]\b", _join_letters, text)


def _normalize_for_search(text: str) -> str:
	if not text:
		return ""
	value = text.replace("\u00b3", "3")
	value = _fold_accents(value)
	value = _collapse_spaced_words(value)
	value = _clean_spaces(value).lower()
	return value


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
	flat = _clean_spaces(text)
	flat_norm = _normalize_for_search(flat)
	result: dict[str, Any] = {}
	lines = [line.strip() for line in text.split("\n") if line.strip()]
	sites_udi = _extract_udi_sites_from_text(text)
	if sites_udi:
		result["sites_udi"] = sites_udi
		known_signed = [s.get("denivele_source_reservoir_m") for s in sites_udi if isinstance(s.get("denivele_source_reservoir_m"), (int, float))]
		if known_signed:
			best_signed = max((float(v) for v in known_signed), key=lambda x: abs(x))
			result["denivele_source_reservoir_m"] = round(best_signed, 3)
			result["denivele_estime_m"] = round(abs(best_signed), 3)
			if best_signed > 0:
				result["hauteur_chute_estimee_m"] = round(best_signed, 3)
			else:
				result["hauteur_chute_estimee_m"] = None
				result["potentiel_hydraulique"] = False
			if result.get("volume_reservoir_m3") is None:
				site_volumes = [s.get("volume_reservoir_m3") for s in sites_udi if isinstance(s.get("volume_reservoir_m3"), (int, float))]
				if site_volumes:
					result["volume_reservoir_m3"] = max(float(v) for v in site_volumes)

	udi_name_match = re.search(
		r"\bUDI\s*[:\-]?\s*([A-Za-z0-9À-ÖØ-öø-ÿ'\-\s]{3,120}?)(?=\s+(?:D[ée]bit|Volume|Hauteur|Brise|Source|R[ée]servoir|Commune)\b|$)",
		flat,
		re.IGNORECASE,
	)
	if udi_name_match:
		result["nom_udi"] = _clean_spaces(udi_name_match.group(1))
	elif re.search(r"\b(aep|eau\s+potable|synoptique)\b", flat_norm, re.IGNORECASE):
		for line in lines[:25]:
			candidate = _clean_spaces(line)
			if len(candidate) < 8:
				continue
			if re.search(r"(synoptique|schema|schéma|aep|eau\s+potable|udi|reseau|réseau)", _normalize_for_search(candidate), re.IGNORECASE):
				result["nom_udi"] = candidate[:120]
				break

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

	if re.search(r"(brise[-\s]?charge|reducteur\s+de\s+pression|chambre\s+de\s+reduction|\bprv\b)", flat_norm, re.IGNORECASE):
		result["presence_brise_charge"] = True

	count_brise = len(re.findall(r"brise[-\s]?charge", flat_norm, flags=re.IGNORECASE))
	if count_brise > 0:
		result["nombre_brise_charge"] = count_brise

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
		volume_res_match = re.search(r"reservoir[^\n]{0,60}([0-9]+(?:[.,][0-9]+)?)\s*m[³3]|([0-9]+(?:[.,][0-9]+)?)\s*m[³3][^\n]{0,60}reservoir", flat_norm, re.IGNORECASE)
		if volume_res_match:
			vol_raw = volume_res_match.group(1) or volume_res_match.group(2)
			vol_val = _parse_float(vol_raw)
			if vol_val is not None:
				result["volume_reservoir_m3"] = vol_val

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

	for searchable in search_flats:
		for pattern in head_patterns:
			head_match = re.search(pattern, searchable, re.IGNORECASE)
			if head_match:
				head_value = _parse_float(head_match.group(1))
				if head_value is not None:
					result["hauteur_chute_estimee_m"] = head_value
					break
		if result.get("hauteur_chute_estimee_m") is not None:
			break

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
			result["hauteur_chute_estimee_m"] = round((amont - aval) * 10, 3)
			result["_debug_head_source"] = "pression_amont_aval_bar"

	norm_text = _normalize_for_search(text)

	local_drops: list[float] = []
	local_signed_drops: list[float] = []
	local_altitudes: list[float] = []

	local_pair_patterns = [
		r"source[\s\S]{0,120}?([0-9]{3,4})\s*m\s*ngf[\s\S]{0,140}?reservoir[\s\S]{0,140}?([0-9]{3,4})\s*m\s*ngf",
		r"reservoir[\s\S]{0,120}?([0-9]{3,4})\s*m\s*ngf[\s\S]{0,140}?source[\s\S]{0,140}?([0-9]{3,4})\s*m\s*ngf",
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
		result["denivele_estime_m"] = round(best_drop, 3)
		if local_signed_drops:
			best_signed = max(local_signed_drops, key=lambda x: abs(x))
			result["denivele_source_reservoir_m"] = round(best_signed, 3)
		if result.get("hauteur_chute_estimee_m") is None:
			if best_signed > 0:
				# Only a positive source->reservoir difference can be interpreted as available head.
				result["hauteur_chute_estimee_m"] = round(best_signed, 3)
				result["_debug_head_source"] = "ngf_source_reservoir_local_positive"
			else:
				result["hauteur_chute_estimee_m"] = None
				result["_debug_head_source"] = "ngf_source_reservoir_local_negative"
				result["potentiel_hydraulique"] = False
	elif not local_altitudes:
		ngf_values: list[float] = []
		for match in re.finditer(r"([0-9]{3,4})\s*m\s*ngf", norm_text, re.IGNORECASE):
			value = _parse_float(match.group(1))
			if value is not None:
				ngf_values.append(value)

		if ngf_values:
			unique_altitudes = sorted(set(ngf_values), reverse=True)
			result["altitudes_ngf_m"] = unique_altitudes
			if len(unique_altitudes) >= 2:
				result["denivele_estime_m"] = round(max(unique_altitudes) - min(unique_altitudes), 3)
				if result.get("hauteur_chute_estimee_m") is None:
					result["hauteur_chute_estimee_m"] = result["denivele_estime_m"]
					result["_debug_head_source"] = "ngf_delta_global"

	points = []
	for m in re.finditer(r"([^\n]{0,100}(?:brise[-\s]?charge|chambre\s+de\s+r[ée]duction|r[ée]ducteur\s+de\s+pression)[^\n]{0,100})", text, re.IGNORECASE):
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

	constraints: list[str] = []
	constraint_patterns = [
		r"([^\n]{0,140}(?:diam[èe]tre|dn\s*\d+|fonte|pehd|pvc|acier)[^\n]{0,140})",
		r"([^\n]{0,140}(?:pression\s+amont|pression\s+aval|\bbar\b)[^\n]{0,140})",
		r"([^\n]{0,140}(?:clapet|vanne|r[ée]ducteur\s+de\s+pression|r[ée]gulateur\s+de\s+pression|brise[-\s]?charge)[^\n]{0,140})",
		r"([^\n]{0,140}(?:altitude|ngf|d[ée]nivel[ée]|hauteur\s+de\s+chute)[^\n]{0,140})",
	]
	for pattern in constraint_patterns:
		for m in re.finditer(pattern, text, re.IGNORECASE):
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

	return result


def _extract_udi_sites_from_text(document_text: str) -> list[dict[str, Any]]:
	text = (document_text or "").replace("\r\n", "\n")
	norm_text = _normalize_for_search(text)

	matches = list(re.finditer(r"\budi\s*([0-9]{1,2})\s*[-:]?\s*([^\n]{2,120})", norm_text, re.IGNORECASE))
	if not matches:
		return []

	sites: list[dict[str, Any]] = []
	for i, match in enumerate(matches):
		start = match.start()
		end = matches[i + 1].start() if i + 1 < len(matches) else len(norm_text)
		segment = norm_text[start:end]

		udi_number = match.group(1)
		udi_name_part = _clean_spaces(match.group(2))
		site_name = f"UDI {udi_number} - {udi_name_part}" if udi_name_part else f"UDI {udi_number}"

		source_alt = None
		reservoir_alt = None
		source_match = re.search(r"source[^\n]{0,120}?([0-9]{3,4})\s*m\s*ngf", segment, re.IGNORECASE)
		reservoir_match = re.search(r"reservoir[^\n]{0,120}?([0-9]{3,4})\s*m\s*ngf", segment, re.IGNORECASE)
		if source_match:
			source_alt = _parse_float(source_match.group(1))
		if reservoir_match:
			reservoir_alt = _parse_float(reservoir_match.group(1))

		denivele_signed = None
		if source_alt is not None and reservoir_alt is not None:
			denivele_signed = round(source_alt - reservoir_alt, 3)

		volume_match = re.search(r"([0-9]+(?:[.,][0-9]+)?)\s*m[³3][^\n]{0,30}reservoir", segment, re.IGNORECASE)
		volume_reservoir = _parse_float(volume_match.group(1)) if volume_match else None

		sites.append(
			{
				"site": site_name,
				"source_altitude_ngf_m": source_alt,
				"reservoir_altitude_ngf_m": reservoir_alt,
				"denivele_source_reservoir_m": denivele_signed,
				"source_au_dessus_reservoir": denivele_signed > 0 if denivele_signed is not None else None,
				"volume_reservoir_m3": volume_reservoir,
			}
		)

	return sites


def _apply_hydro_flow_filter(extraction_json: dict[str, Any]) -> dict[str, Any]:
	flow_m3_j = _parse_float(extraction_json.get("debit_m3_j"))
	if flow_m3_j is None:
		return extraction_json

	if flow_m3_j < HYDRO_MIN_FLOW_M3_J:
		extraction_json["potentiel_hydraulique"] = False

	return extraction_json


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
	if not isinstance(schema.get("contraintes_techniques"), list):
		schema["contraintes_techniques"] = []
	if not isinstance(schema.get("sites_udi"), list):
		schema["sites_udi"] = []

	for key in ["hauteur_chute_estimee_m", "denivele_source_reservoir_m", "denivele_estime_m", "volume_reference_m3_j", "debit_m3_j", "volume_reservoir_m3", "nombre_brise_charge"]:
		if schema.get(key) is not None:
			schema[key] = _parse_float(schema.get(key))

	if schema.get("nombre_brise_charge") is not None:
		schema["nombre_brise_charge"] = int(schema["nombre_brise_charge"])

	if schema.get("potentiel_hydraulique") not in (True, False, None):
		schema["potentiel_hydraulique"] = None

	for numeric_key in ["hauteur_chute_estimee_m", "denivele_source_reservoir_m", "denivele_estime_m", "volume_reference_m3_j", "debit_m3_j", "volume_reservoir_m3"]:
		if _is_missing(schema.get(numeric_key)):
			schema[numeric_key] = None

	normalized_sites: list[dict[str, Any]] = []
	for raw_site in schema.get("sites_udi") or []:
		if not isinstance(raw_site, dict):
			continue
		normalized_sites.append(
			{
				"site": str(raw_site.get("site", "")).strip(),
				"source_altitude_ngf_m": _parse_float(raw_site.get("source_altitude_ngf_m")),
				"reservoir_altitude_ngf_m": _parse_float(raw_site.get("reservoir_altitude_ngf_m")),
				"denivele_source_reservoir_m": _parse_float(raw_site.get("denivele_source_reservoir_m")),
				"source_au_dessus_reservoir": raw_site.get("source_au_dessus_reservoir") if raw_site.get("source_au_dessus_reservoir") in (True, False, None) else None,
				"volume_reservoir_m3": _parse_float(raw_site.get("volume_reservoir_m3")),
			}
		)
	schema["sites_udi"] = normalized_sites

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
		parsed_json, description = _extract_json_and_description(content)

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

		if merged_json.get("potentiel_hydraulique") not in (True, False, None):
			merged_json["potentiel_hydraulique"] = None

		if merged_json.get("potentiel_hydraulique") is None and rule_based.get("potentiel_hydraulique") is True:
			merged_json["potentiel_hydraulique"] = True

		merged_json = _apply_hydro_flow_filter(merged_json)

		debug_info = {}
		if document_type == "udi":
			debug_info = _collect_udi_debug_signals(document_text)
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

	def extract_from_pdf(self, pdf_bytes: bytes) -> dict[str, Any]:
		document_text = extract_text_from_pdf(pdf_bytes)
		if not document_text:
			raise ValueError("Impossible d'extraire du texte du PDF.")
		return self.extract_from_text(document_text)
