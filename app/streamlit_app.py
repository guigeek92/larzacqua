from __future__ import annotations

from datetime import datetime
import hashlib
from io import BytesIO
import json
import re
from pathlib import Path
import sys
import time
import unicodedata
import uuid

import requests
import streamlit as st

try:
	from reportlab.lib import colors
	from reportlab.lib.pagesizes import A4
	from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
	from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
	REPORTLAB_AVAILABLE = True
except ImportError:
	REPORTLAB_AVAILABLE = False

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
	sys.path.insert(0, str(ROOT_DIR))

from src.ai_extraction import ALLOWED_MODELS

API_URL_DEFAULT = "http://127.0.0.1:8010/extract"
API_TIMEOUT_SECONDS = 180
API_MAX_RETRIES = 3
API_BACKOFF_SECONDS = 1.0


def inject_brand_theme() -> None:
	st.markdown(
		"""
		<style>
		:root {
			--larzac-blue: #1f6fb2;
			--larzac-blue-soft: #d8ebfb;
			--larzac-green: #2da66f;
			--larzac-green-soft: #ddf5e9;
			--larzac-ink: #0f3b57;
		}

		.stApp {
			background:
				radial-gradient(circle at 0% 0%, var(--larzac-blue-soft), transparent 42%),
				radial-gradient(circle at 100% 0%, var(--larzac-green-soft), transparent 45%),
				#f7fbff;
		}

		.larzac-hero {
			padding: 0.9rem 1rem;
			border-radius: 12px;
			background: linear-gradient(120deg, rgba(31,111,178,0.95), rgba(45,166,111,0.9));
			color: white;
			border: 1px solid rgba(255,255,255,0.25);
			box-shadow: 0 8px 24px rgba(16, 61, 92, 0.18);
			margin-bottom: 0.6rem;
		}

		.larzac-card {
			padding: 0.8rem 1rem;
			border-radius: 10px;
			border-left: 4px solid var(--larzac-blue);
			background: white;
			box-shadow: 0 3px 14px rgba(15, 59, 87, 0.1);
			margin-bottom: 0.5rem;
		}

		.larzac-card strong {
			color: var(--larzac-ink);
		}

		.stButton > button[kind="primary"] {
			background: linear-gradient(120deg, var(--larzac-blue), var(--larzac-green));
			border: none;
		}
		</style>
		""",
		unsafe_allow_html=True,
	)


def format_description_text(raw_text: str) -> str:
	text = (raw_text or "").replace("\r\n", "\n").strip()
	if not text:
		return ""

	text = re.sub(r"\n{3,}", "\n\n", text)
	text = re.sub(r"(?<=[\.!\?])\s+(?=[A-ZÀ-ÖØ-Ý])", "\n\n", text)

	for marker in [
		"Type de station",
		"Principaux ouvrages",
		"État des équipements",
		"Fonctionnement de la filière eau",
		"Éléments importants observés",
		"Première analyse du potentiel énergétique",
	]:
		text = re.sub(rf"(?i)(^|\n)\s*{re.escape(marker)}\s*:", f"\n\n### {marker}\n", text)

	if "\n" not in text:
		text = re.sub(r"\s*[;•]\s*", "\n- ", text)
		if text.startswith("- "):
			return text

	return text.strip()


def normalize_sort_key(value: str) -> str:
	base = (value or "").strip().lower()
	normalized = unicodedata.normalize("NFKD", base)
	return "".join(char for char in normalized if not unicodedata.combining(char))


def is_missing_value(value) -> bool:
	if value is None:
		return True
	if isinstance(value, str):
		normalized = value.strip().lower()
		return normalized in {"", "nd", "n/d", "null", "none", "-", "non renseignee", "non renseignée"}
	if isinstance(value, list):
		return len(value) == 0
	return False


def compute_data_completeness(result_json: dict, document_type: str) -> tuple[int, str]:
	"""
	STEP 5 - UX decision aid:
	Estimate data completeness to quickly detect fragile/partial extractions.
	"""
	if document_type == "udi":
		tracked_fields = [
			"nom_udi",
			"localisation",
			"debit_m3_j",
			"volume_reservoir_m3",
			"hauteur_chute_estimee_m",
			"denivele_source_reservoir_m",
			"potentiel_hydraulique",
		]
	else:
		tracked_fields = [
			"nom_station",
			"commune",
			"capacite_eh",
			"debit_m3_j",
			"surface_potentielle_solaire_m2",
			"potentiel_hydraulique",
		]

	available = sum(0 if is_missing_value(result_json.get(field)) else 1 for field in tracked_fields)
	percent = int(round((available / max(1, len(tracked_fields))) * 100))

	if percent >= 80:
		return percent, "Élevée"
	if percent >= 50:
		return percent, "Moyenne"
	return percent, "Faible"


def _clean_group_tokens(raw_value: str) -> list[str]:
	value = normalize_sort_key(raw_value)
	value = re.sub(r"[^a-z0-9]+", " ", value)
	tokens = [tok for tok in value.split() if tok]
	stop_words = {
		"udi",
		"site",
		"reseau",
		"réseau",
		"aep",
		"eau",
		"potable",
		"synoptique",
		"schema",
		"schematique",
		"technique",
		"document",
		"fiche",
		"pdf",
	}
	return [tok for tok in tokens if tok not in stop_words]


def infer_udi_site_group_key(entry: dict) -> str:
	result_json = entry.get("result_json", {})
	candidates = [
		result_json.get("nom_udi", ""),
		result_json.get("localisation", ""),
		" ".join(result_json.get("communes") or []),
		re.sub(r"\.[Pp][Dd][Ff]$", "", entry.get("filename", "")),
	]
	merged_tokens: list[str] = []
	for candidate in candidates:
		for token in _clean_group_tokens(str(candidate)):
			if token not in merged_tokens:
				merged_tokens.append(token)
		if len(merged_tokens) >= 4:
			break

	if merged_tokens:
		return " ".join(merged_tokens[:4])

	return normalize_sort_key(entry.get("site_name", "site-udi")) or "site-udi"


def _aggregate_udi_group(entries: list[dict]) -> dict:
	numeric_fields = [
		"debit_m3_j",
		"hauteur_chute_estimee_m",
		"denivele_source_reservoir_m",
		"denivele_estime_m",
		"volume_reservoir_m3",
		"volume_reference_m3_j",
		"nombre_brise_charge",
	]
	list_fields = [
		"communes",
		"altitudes_ngf_m",
		"sites_udi",
		"points_pression_reduction",
		"emplacements_turbine_potentiels",
		"contraintes_techniques",
	]
	text_fields = ["nom_udi", "localisation"]

	aggregated: dict = {"potentiel_hydraulique": None}
	for field in numeric_fields:
		values = []
		for entry in entries:
			value = entry.get("result_json", {}).get(field)
			if isinstance(value, (int, float)):
				values.append(float(value))
		if values:
			aggregated[field] = max(values)

	for field in list_fields:
		merged: list = []
		for entry in entries:
			value = entry.get("result_json", {}).get(field)
			if not isinstance(value, list):
				continue
			for item in value:
				if item not in merged:
					merged.append(item)
		if merged:
			aggregated[field] = merged

	for field in text_fields:
		for entry in entries:
			value = entry.get("result_json", {}).get(field)
			if isinstance(value, str) and value.strip():
				aggregated[field] = value.strip()
				break

	potentials = [entry.get("result_json", {}).get("potentiel_hydraulique") for entry in entries]
	if any(value is True for value in potentials):
		aggregated["potentiel_hydraulique"] = True
	elif all(value is False for value in potentials if value is not None) and any(value is False for value in potentials):
		aggregated["potentiel_hydraulique"] = False

	return aggregated


def link_udi_entries_by_site(results: list[dict]) -> list[dict]:
	if not results:
		return results

	grouped: dict[str, list[dict]] = {}
	for entry in results:
		if entry.get("document_type", "").lower() != "udi":
			continue
		key = infer_udi_site_group_key(entry)
		grouped.setdefault(key, []).append(entry)

	linked_results: list[dict] = []
	for entry in results:
		if entry.get("document_type", "").lower() != "udi":
			linked_results.append(entry)
			continue

		group_key = infer_udi_site_group_key(entry)
		group_entries = grouped.get(group_key, [entry])
		aggregated = _aggregate_udi_group(group_entries)

		new_entry = dict(entry)
		new_result_json = dict(entry.get("result_json", {}))
		filled_fields: list[str] = []
		for field, value in aggregated.items():
			if field not in new_result_json or is_missing_value(new_result_json.get(field)):
				if not is_missing_value(value):
					new_result_json[field] = value
					filled_fields.append(field)

		new_entry["result_json"] = new_result_json

		debug_data = dict(entry.get("debug", {}) or {})
		debug_data["udi_linking"] = {
			"group_key": group_key,
			"group_size": len(group_entries),
			"related_files": [item.get("filename", "") for item in group_entries if item.get("filename")],
			"filled_fields": filled_fields,
		}
		new_entry["debug"] = debug_data
		new_entry["site_group_key"] = group_key
		linked_results.append(new_entry)

	return linked_results


def get_site_name(result_json: dict, document_type: str, fallback_filename: str) -> str:
	if document_type == "udi":
		return (result_json.get("nom_udi") or fallback_filename or "Site UDI").strip()
	return (result_json.get("nom_station") or fallback_filename or "Site STEU").strip()


def build_hydro_summary(result_json: dict, document_type: str) -> list[str]:
	lines: list[str] = []
	potentiel = result_json.get("potentiel_hydraulique")
	if potentiel is True:
		lines.append("Statut : potentiel hydraulique identifié")
	elif potentiel is False:
		lines.append("Statut : potentiel hydraulique non retenu")
	else:
		lines.append("Statut : potentiel hydraulique non documenté")

	debit_m3_j = result_json.get("debit_m3_j")
	if debit_m3_j is not None:
		lines.append(f"Débit estimé : {debit_m3_j} m³/j")

	if document_type == "udi":
		hauteur = result_json.get("hauteur_chute_estimee_m")
		if hauteur is not None:
			lines.append(f"Hauteur de chute estimée : {hauteur} m")
		denivele_sr = result_json.get("denivele_source_reservoir_m")
		if denivele_sr is not None:
			lines.append(f"Dénivelé source -> réservoir : {denivele_sr} m")
		vol_res = result_json.get("volume_reservoir_m3")
		if vol_res is not None:
			lines.append(f"Volume réservoir : {vol_res} m³")
		sites = result_json.get("sites_udi") or []
		if sites:
			lines.append(f"Sites UDI analysés : {len(sites)}")
		points = result_json.get("points_pression_reduction") or []
		if points:
			lines.append(f"Points de réduction de pression détectés : {len(points)}")

	return lines


def build_pv_summary(result_json: dict) -> list[str]:
	lines: list[str] = []
	surface_pv = result_json.get("surface_potentielle_solaire_m2")
	if surface_pv is None:
		lines.append("Statut : potentiel PV non documenté")
	else:
		lines.append("Statut : potentiel PV identifié")
		lines.append(f"Surface potentielle : {surface_pv} m²")
	return lines


def init_session_state() -> None:
	if "analysis_history" not in st.session_state:
		st.session_state.analysis_history = []
	if "selected_history_run_id" not in st.session_state:
		st.session_state.selected_history_run_id = None
	if "analysis_cache" not in st.session_state:
		st.session_state.analysis_cache = {}


def build_cache_key(file_bytes: bytes, model_name: str) -> str:
	content_hash = hashlib.sha256(file_bytes).hexdigest()
	return f"{model_name}:{content_hash}"


def request_extract_with_retry(
	session: requests.Session,
	api_url: str,
	filename: str,
	file_bytes: bytes,
	model_name: str,
	max_attempts: int = API_MAX_RETRIES,
	timeout_seconds: int = API_TIMEOUT_SECONDS,
) -> tuple[dict | None, str | None]:
	"""
	STEP 4 - UI robustness:
	Centralized API call with retry/backoff to reduce transient failures.
	"""
	files = {"file": (filename, file_bytes, "application/pdf")}
	data = {"model": model_name}

	for attempt in range(1, max_attempts + 1):
		try:
			response = session.post(api_url, files=files, data=data, timeout=timeout_seconds)

			if response.ok:
				try:
					return response.json(), None
				except ValueError:
					return None, "Réponse API invalide (JSON non lisible)."

			# Retry only on temporary server-side conditions.
			should_retry = response.status_code in {429, 500, 502, 503, 504}
			detail = ""
			try:
				error_payload = response.json()
				detail = error_payload.get("detail", "")
			except ValueError:
				detail = response.text

			if not should_retry or attempt == max_attempts:
				return None, f"Erreur API {response.status_code}: {detail}".strip()

		except requests.RequestException as exc:
			if attempt == max_attempts:
				return None, f"Erreur API: {exc}"

		# Simple exponential backoff: 1s, 2s, 4s ...
		time.sleep(API_BACKOFF_SECONDS * (2 ** (attempt - 1)))

	return None, "Erreur API inconnue."


def render_header() -> None:
	st.set_page_config(page_title="Energy AI Tool", page_icon="⚙️", layout="wide")
	inject_brand_theme()
	st.title("Energy AI Tool - Analyse de fiches techniques STEP")
	st.caption("Extraction structurée des informations d'infrastructure depuis un PDF.")
	st.info(
		"Energy AI Tool automatise l'analyse de documents techniques (STEU/UDI), "
		"identifie les potentiels hydro et photovoltaïque, et compare plusieurs sites pour aider à prioriser les études ENR."
	)


def compute_hydro_score(result_json: dict) -> int:
	score = 0
	if result_json.get("potentiel_hydraulique") is True:
		score += 2
	flow = result_json.get("debit_m3_j")
	if isinstance(flow, (int, float)) and flow >= 50:
		score += 1
	head = result_json.get("hauteur_chute_estimee_m")
	if isinstance(head, (int, float)) and head >= 10:
		score += 1
	return score


def compute_pv_score(result_json: dict) -> int:
	surface = result_json.get("surface_potentielle_solaire_m2")
	if not isinstance(surface, (int, float)):
		return 0
	# PV scoring focused on usable surface (main criterion for STEU ranking).
	if surface >= 1000:
		return 5
	if surface >= 500:
		return 4
	if surface >= 200:
		return 3
	if surface >= 80:
		return 2
	return 1


def compute_steu_priority_score(result_json: dict) -> int:
	# STEU ranking is strictly PV-oriented.
	return compute_pv_score(result_json)


def pv_surface_band(surface_m2: float | int | None) -> str:
	if not isinstance(surface_m2, (int, float)):
		return "Non documente"
	if surface_m2 >= 1000:
		return "Tres elevee"
	if surface_m2 >= 500:
		return "Elevee"
	if surface_m2 >= 200:
		return "Moyenne"
	if surface_m2 >= 80:
		return "Faible"
	return "Tres faible"


def compute_udi_priority_score(result_json: dict) -> int:
	# UDI table is hydro-oriented.
	return compute_hydro_score(result_json)


def _flow_score_from_m3j(flow_m3_j: float | int | None) -> int:
	if not isinstance(flow_m3_j, (int, float)):
		return 0
	if flow_m3_j >= 250:
		return 3
	if flow_m3_j >= 100:
		return 2
	if flow_m3_j >= 50:
		return 1
	return 0


def _head_score_from_m(head_m: float | int | None) -> int:
	if not isinstance(head_m, (int, float)):
		return 0
	if head_m >= 25:
		return 3
	if head_m >= 15:
		return 2
	if head_m >= 8:
		return 1
	return 0


def build_ranked_steu_rows(
	results: list[dict],
	min_surface_m2: float = 0,
	min_completeness_pct: int = 0,
	weight_pv: float = 1.0,
	weight_completeness: float = 0.0,
) -> list[dict]:
	rows: list[dict] = []
	for entry in results:
		if entry.get("document_type", "").lower() != "steu":
			continue
		result_json = entry.get("result_json", {})
		pv_surface = result_json.get("surface_potentielle_solaire_m2")
		completeness_pct, _ = compute_data_completeness(result_json, "steu")
		if completeness_pct < min_completeness_pct:
			continue
		if isinstance(pv_surface, (int, float)) and pv_surface < min_surface_m2:
			continue

		pv_priority = compute_steu_priority_score(result_json)
		weighted_priority = round(
			(weight_pv * pv_priority) + (weight_completeness * (completeness_pct / 20)),
			2,
		)
		rows.append(
			{
				"Station": entry.get("site_name", "Site"),
				"Commune": result_json.get("commune"),
				"Surface PV (m2)": pv_surface,
				"Complétude (%)": completeness_pct,
				"Classe surface": pv_surface_band(pv_surface),
				"Potentiel PV": "Oui" if isinstance(pv_surface, (int, float)) else "N/D",
				"Score PV": compute_pv_score(result_json),
				"Priorité PV": weighted_priority,
			}
		)
	return sorted(rows, key=lambda row: row["Priorité PV"], reverse=True)


def build_ranked_udi_rows(
	results: list[dict],
	min_flow_m3j: float = 0,
	min_head_m: float = 0,
	min_completeness_pct: int = 0,
	weight_hydro: float = 1.0,
	weight_flow: float = 1.0,
	weight_head: float = 1.0,
	weight_points: float = 0.5,
	weight_completeness: float = 0.0,
) -> list[dict]:
	rows: list[dict] = []
	for entry in results:
		if entry.get("document_type", "").lower() != "udi":
			continue
		result_json = entry.get("result_json", {})
		hydro_status = result_json.get("potentiel_hydraulique")
		points = result_json.get("points_pression_reduction") or []
		flow_m3_j = result_json.get("debit_m3_j")
		head_m = result_json.get("hauteur_chute_estimee_m")
		completeness_pct, _ = compute_data_completeness(result_json, "udi")

		if completeness_pct < min_completeness_pct:
			continue
		if isinstance(flow_m3_j, (int, float)) and flow_m3_j < min_flow_m3j:
			continue
		if isinstance(head_m, (int, float)) and head_m < min_head_m:
			continue

		weighted_priority = round(
			(weight_hydro * compute_hydro_score(result_json))
			+ (weight_flow * _flow_score_from_m3j(flow_m3_j))
			+ (weight_head * _head_score_from_m(head_m))
			+ (weight_points * min(len(points), 3))
			+ (weight_completeness * (completeness_pct / 25)),
			2,
		)
		rows.append(
			{
				"Site réservoir": entry.get("site_name", "Site"),
				"Localisation": result_json.get("localisation"),
				"Complétude (%)": completeness_pct,
				"Débit (m3/j)": flow_m3_j,
				"Volume réservoir (m3)": result_json.get("volume_reservoir_m3"),
				"Hauteur chute (m)": head_m,
				"Points pression": len(points),
				"Potentiel hydro": "Oui" if hydro_status is True else "Non" if hydro_status is False else "N/D",
				"Score Hydro": compute_hydro_score(result_json),
				"Priorité Hydro": weighted_priority,
			}
		)
	return sorted(rows, key=lambda row: row["Priorité Hydro"], reverse=True)


def render_comparative_analysis(results: list[dict], compare_config: dict | None = None) -> None:
	if not results:
		st.info("Aucun site à comparer pour ce run.")
		return

	config = compare_config or {}

	ranked_steu = build_ranked_steu_rows(
		results,
		min_surface_m2=float(config.get("min_surface_m2", 0)),
		min_completeness_pct=int(config.get("min_completeness_pct", 0)),
		weight_pv=float(config.get("weight_pv", 1.0)),
		weight_completeness=float(config.get("weight_steu_completeness", 0.0)),
	)
	ranked_udi = build_ranked_udi_rows(
		results,
		min_flow_m3j=float(config.get("min_flow_m3j", 0)),
		min_head_m=float(config.get("min_head_m", 0)),
		min_completeness_pct=int(config.get("min_completeness_pct", 0)),
		weight_hydro=float(config.get("weight_hydro", 1.0)),
		weight_flow=float(config.get("weight_flow", 1.0)),
		weight_head=float(config.get("weight_head", 1.0)),
		weight_points=float(config.get("weight_points", 0.5)),
		weight_completeness=float(config.get("weight_udi_completeness", 0.0)),
	)

	col1, col2, col3 = st.columns(3)
	col1.metric("Sites comparés", len(results))
	col2.metric("Stations STEU", len(ranked_steu))
	col3.metric("Sites UDI", len(ranked_udi))

	if ranked_steu:
		st.markdown("### Tableau STEU - comparaison PV (usines d'épuration)")
		st.dataframe(ranked_steu, use_container_width=True, hide_index=True)
		st.success(
			f"STEU prioritaire pour étude PV : {ranked_steu[0]['Station']} (score {ranked_steu[0]['Priorité PV']})."
		)

	if ranked_udi:
		st.markdown("### Tableau UDI - comparaison Hydro (sites réservoir)")
		st.dataframe(ranked_udi, use_container_width=True, hide_index=True)
		st.success(
			f"UDI prioritaire pour étude hydro : {ranked_udi[0]['Site réservoir']} (score {ranked_udi[0]['Priorité Hydro']})."
		)

	if not ranked_steu and not ranked_udi:
		st.info("Aucun indicateur STEU/UDI disponible pour la comparaison.")


def render_comparison_controls() -> dict:
	"""
	STEP 6 - Interactive comparison:
	Allow filtering and weighting directly in UI to support decision scenarios.
	"""
	with st.expander("Filtres et pondérations de comparaison", expanded=False):
		st.caption("Ajuste les seuils métier et les pondérations avant d'interpréter le classement.")

		col1, col2 = st.columns(2)
		with col1:
			min_surface_m2 = st.slider("STEU - Surface PV minimale (m2)", min_value=0, max_value=2000, value=0, step=50)
			min_flow_m3j = st.slider("UDI - Débit minimal (m3/j)", min_value=0, max_value=500, value=0, step=10)
			min_head_m = st.slider("UDI - Hauteur de chute minimale (m)", min_value=0, max_value=80, value=0, step=1)
			min_completeness_pct = st.slider("Complétude minimale (%)", min_value=0, max_value=100, value=0, step=5)

		with col2:
			weight_pv = st.slider("Poids score PV (STEU)", min_value=0.0, max_value=4.0, value=1.0, step=0.1)
			weight_steu_completeness = st.slider(
				"Poids complétude (STEU)", min_value=0.0, max_value=2.0, value=0.0, step=0.1
			)
			weight_hydro = st.slider("Poids score hydro (UDI)", min_value=0.0, max_value=4.0, value=1.0, step=0.1)
			weight_flow = st.slider("Poids débit (UDI)", min_value=0.0, max_value=3.0, value=1.0, step=0.1)
			weight_head = st.slider("Poids chute (UDI)", min_value=0.0, max_value=3.0, value=1.0, step=0.1)
			weight_points = st.slider("Poids points pression (UDI)", min_value=0.0, max_value=2.0, value=0.5, step=0.1)
			weight_udi_completeness = st.slider(
				"Poids complétude (UDI)", min_value=0.0, max_value=2.0, value=0.0, step=0.1
			)

	return {
		"min_surface_m2": min_surface_m2,
		"min_flow_m3j": min_flow_m3j,
		"min_head_m": min_head_m,
		"min_completeness_pct": min_completeness_pct,
		"weight_pv": weight_pv,
		"weight_steu_completeness": weight_steu_completeness,
		"weight_hydro": weight_hydro,
		"weight_flow": weight_flow,
		"weight_head": weight_head,
		"weight_points": weight_points,
		"weight_udi_completeness": weight_udi_completeness,
	}


def build_comparison_report(run_data: dict) -> str:
	results = run_data.get("results", [])
	steu_entries = [entry for entry in results if entry.get("document_type", "").lower() == "steu"]
	udi_entries = [entry for entry in results if entry.get("document_type", "").lower() == "udi"]

	lines: list[str] = []
	lines.append("# Rapport de comparaison multi-sites")
	lines.append("")
	lines.append(f"Date du run : {run_data.get('timestamp', '-')}")
	lines.append(f"Modele IA : {run_data.get('model', '-')}")
	lines.append(f"Fichiers analyses : {run_data.get('success_count', 0)}/{run_data.get('total_files', 0)}")
	lines.append(f"Erreurs : {run_data.get('error_count', 0)}")
	lines.append("")

	if steu_entries:
		lines.append("## Comparatif STEU (orientation PV)")
		steu_rows: list[dict] = []
		for entry in steu_entries:
			result_json = entry.get("result_json", {})
			pv_surface = result_json.get("surface_potentielle_solaire_m2")
			priority = compute_steu_priority_score(result_json)
			steu_rows.append(
				{
					"station": entry.get("site_name", "Site"),
					"commune": result_json.get("commune") or "N/D",
					"surface": pv_surface,
					"classe": pv_surface_band(pv_surface),
					"score": priority,
				}
			)
		ranked_steu = sorted(steu_rows, key=lambda row: row["score"], reverse=True)
		for idx, row in enumerate(ranked_steu, start=1):
			surface_label = f"{row['surface']} m2" if isinstance(row["surface"], (int, float)) else "N/D"
			lines.append(
				f"{idx}. {row['station']} ({row['commune']}) - Surface PV: {surface_label}, "
				f"classe: {row['classe']}, score PV: {row['score']}"
			)
		lines.append("")
		lines.append(f"Recommandation STEU PV : {ranked_steu[0]['station']}")
		lines.append("")

	if udi_entries:
		lines.append("## Comparatif UDI (orientation Hydro)")
		udi_rows: list[dict] = []
		for entry in udi_entries:
			result_json = entry.get("result_json", {})
			points = result_json.get("points_pression_reduction") or []
			priority = compute_udi_priority_score(result_json)
			udi_rows.append(
				{
					"site": entry.get("site_name", "Site"),
					"debit": result_json.get("debit_m3_j"),
					"chute": result_json.get("hauteur_chute_estimee_m"),
					"points": len(points),
					"hydro": result_json.get("potentiel_hydraulique"),
					"score": priority,
				}
			)
		ranked_udi = sorted(udi_rows, key=lambda row: row["score"], reverse=True)
		for idx, row in enumerate(ranked_udi, start=1):
			hydro_label = "Oui" if row["hydro"] is True else "Non" if row["hydro"] is False else "N/D"
			debit_label = f"{row['debit']} m3/j" if isinstance(row["debit"], (int, float)) else "N/D"
			chute_label = f"{row['chute']} m" if isinstance(row["chute"], (int, float)) else "N/D"
			lines.append(
				f"{idx}. {row['site']} - Debit: {debit_label}, Chute: {chute_label}, "
				f"Points pression: {row['points']}, Hydro: {hydro_label}, score Hydro: {row['score']}"
			)
		lines.append("")
		lines.append(f"Recommandation UDI Hydro : {ranked_udi[0]['site']}")
		lines.append("")

	if run_data.get("error_count", 0):
		lines.append("## Fichiers en erreur")
		for err in run_data.get("errors", []):
			lines.append(f"- {err.get('filename', 'fichier')} : {err.get('error', 'Erreur inconnue')}")

	return "\n".join(lines).strip() + "\n"


def render_site_detail(entry: dict, show_debug: bool) -> None:
	result_json = entry.get("result_json", {})
	description = entry.get("description", "")
	document_type = entry.get("document_type", "steu")
	debug_info = entry.get("debug", {})
	filename = entry.get("filename", "document.pdf")
	site_name = entry.get("site_name", "Site")

	if document_type == "udi":
		main_name = result_json.get("nom_udi") or site_name
		localisation = result_json.get("localisation") or "Non renseignée"
		debit = result_json.get("debit_m3_j")
		third_label = f"{debit} m³/j" if debit is not None else "N/A"
		third_title = "Débit"
	else:
		main_name = result_json.get("nom_station") or site_name
		localisation = result_json.get("commune") or "Non renseignée"
		capacite = result_json.get("capacite_eh")
		third_label = f"{capacite} EH" if capacite is not None else "N/A"
		third_title = "Capacité"

	completeness_pct, completeness_label = compute_data_completeness(result_json, document_type)

	st.markdown(f"### {site_name}")
	st.caption(f"Fichier : {filename} | Type détecté : {document_type.upper()}")
	col1, col2, col3 = st.columns(3)
	col1.metric("Référence", main_name)
	col2.metric("Localisation", localisation)
	col3.metric(third_title, third_label)
	st.caption(f"Complétude extraction : {completeness_pct}% ({completeness_label})")

	tab_desc, tab_hydro, tab_pv, tab_json, tab_debug = st.tabs(
		["Description", "Hydro", "PV", "JSON", "Debug"]
	)

	with tab_desc:
		if description:
			with st.container(border=True):
				st.markdown(format_description_text(description))
		else:
			st.info("Aucune description détaillée n'a été renvoyée par le modèle.")

	with tab_hydro:
		with st.container(border=True):
			for line in build_hydro_summary(result_json, document_type):
				st.write(f"- {line}")
			if document_type == "udi":
				linking = (debug_info or {}).get("udi_linking", {})
				related_files = linking.get("related_files") or []
				if related_files:
					st.write(f"- Fichiers UDI relies au meme site : {len(related_files)}")
					st.caption(", ".join(related_files[:6]) + (" ..." if len(related_files) > 6 else ""))
				group_key = linking.get("group_key")
				if group_key:
					st.caption(f"Cle de regroupement UDI : {group_key}")

	with tab_pv:
		with st.container(border=True):
			for line in build_pv_summary(result_json):
				st.write(f"- {line}")

	with tab_json:
		st.json(result_json)

	with tab_debug:
		if not show_debug:
			st.info("Active l'option debug dans la barre latérale pour afficher cette section.")
		elif debug_info:
			st.json(debug_info)
		else:
			st.info("Aucune donnée debug renvoyée par l'API pour ce document.")


def generate_pdf_report(run_data: dict) -> bytes | None:
	if not REPORTLAB_AVAILABLE:
		return None

	buffer = BytesIO()
	doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=28, rightMargin=28, topMargin=28, bottomMargin=28)
	styles = getSampleStyleSheet()
	title_style = ParagraphStyle("TitleBlue", parent=styles["Heading1"], textColor=colors.HexColor("#1f6fb2"))
	subtitle_style = ParagraphStyle("SubtitleGreen", parent=styles["Heading2"], textColor=colors.HexColor("#2da66f"))
	body_style = styles["BodyText"]

	results = run_data.get("results", [])
	ranked_steu = build_ranked_steu_rows(results)
	ranked_udi = build_ranked_udi_rows(results)

	story = [
		Paragraph("Rapport complet de comparaison multi-sites", title_style),
		Spacer(1, 8),
		Paragraph(f"Date du run : {run_data.get('timestamp', '-')}", body_style),
		Paragraph(f"Modele IA : {run_data.get('model', '-')}", body_style),
		Paragraph(
			f"Fichiers analyses : {run_data.get('success_count', 0)}/{run_data.get('total_files', 0)} | Erreurs : {run_data.get('error_count', 0)}",
			body_style,
		),
		Spacer(1, 10),
	]

	if ranked_steu:
		story.append(Paragraph("Comparatif STEU - Orientation PV", subtitle_style))
		steu_table_data = [["Station", "Commune", "Surface PV (m2)", "Classe", "Score PV", "Priorite PV"]]
		for row in ranked_steu:
			steu_table_data.append(
				[
					str(row.get("Station", "")),
					str(row.get("Commune") or "N/D"),
					str(row.get("Surface PV (m2)") or "N/D"),
					str(row.get("Classe surface") or "N/D"),
					str(row.get("Score PV") or 0),
					str(row.get("Priorité PV") or 0),
				]
			)
		table = Table(steu_table_data, repeatRows=1)
		table.setStyle(
			TableStyle(
				[
					("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d8ebfb")),
					("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0f3b57")),
					("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
					("FONTSIZE", (0, 0), (-1, -1), 8),
				]
			)
		)
		story.extend([table, Spacer(1, 10)])

	if ranked_udi:
		story.append(Paragraph("Comparatif UDI - Orientation Hydro", subtitle_style))
		udi_table_data = [["Site", "Localisation", "Debit (m3/j)", "Chute (m)", "Points", "Score Hydro", "Priorite Hydro"]]
		for row in ranked_udi:
			udi_table_data.append(
				[
					str(row.get("Site réservoir", "")),
					str(row.get("Localisation") or "N/D"),
					str(row.get("Débit (m3/j)") or "N/D"),
					str(row.get("Hauteur chute (m)") or "N/D"),
					str(row.get("Points pression") or 0),
					str(row.get("Score Hydro") or 0),
					str(row.get("Priorité Hydro") or 0),
				]
			)
		table = Table(udi_table_data, repeatRows=1)
		table.setStyle(
			TableStyle(
				[
					("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ddf5e9")),
					("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0f3b57")),
					("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
					("FONTSIZE", (0, 0), (-1, -1), 8),
				]
			)
		)
		story.extend([table, Spacer(1, 10)])

	story.append(Paragraph("Analyse detaillee par site", subtitle_style))
	for entry in results:
		result_json = entry.get("result_json", {})
		site_name = entry.get("site_name", "Site")
		doc_type = entry.get("document_type", "-").upper()
		description = entry.get("description", "") or "Description non disponible."
		story.append(Paragraph(f"<b>{site_name}</b> ({doc_type})", body_style))
		story.append(Paragraph(f"- Debit m3/j : {result_json.get('debit_m3_j', 'N/D')}", body_style))
		story.append(Paragraph(f"- Surface PV m2 : {result_json.get('surface_potentielle_solaire_m2', 'N/D')}", body_style))
		story.append(Paragraph(f"- Potentiel hydro : {result_json.get('potentiel_hydraulique', 'N/D')}", body_style))
		story.append(Paragraph(f"- Description : {description[:1200]}", body_style))
		story.append(Spacer(1, 6))

	if run_data.get("error_count", 0):
		story.append(Paragraph("Fichiers en erreur", subtitle_style))
		for err in run_data.get("errors", []):
			story.append(Paragraph(f"- {err.get('filename', 'fichier')} : {err.get('error', 'Erreur inconnue')}", body_style))

	doc.build(story)
	buffer.seek(0)
	return buffer.getvalue()


def render_history_selector() -> dict | None:
	history = st.session_state.analysis_history
	if not history:
		st.session_state.selected_history_run_id = None
		return None

	# Ensure all legacy entries also have an id.
	for run in history:
		if not run.get("run_id"):
			run["run_id"] = uuid.uuid4().hex

	run_ids = [run["run_id"] for run in history]
	if st.session_state.selected_history_run_id not in run_ids:
		st.session_state.selected_history_run_id = run_ids[0]

	selected_run_id = st.selectbox(
		"Historique des analyses",
		options=run_ids,
		key="selected_history_run_id",
		format_func=lambda run_id: next(
			(
				f"{run['timestamp']} · {run['success_count']}/{run['total_files']} fichiers · {run['model']}"
				for run in history
				if run["run_id"] == run_id
			),
			run_id,
		),
	)

	for run in history:
		if run["run_id"] == selected_run_id:
			return run

	return history[0]


def main() -> None:
	render_header()
	init_session_state()

	with st.sidebar:
		st.subheader("Configuration")
		selected_model = st.selectbox("Modèle IA", options=ALLOWED_MODELS, index=0)
		api_url = st.text_input("URL API", value=API_URL_DEFAULT)
		show_debug = st.toggle("Afficher debug extraction", value=True)
		if st.button("Vider l'historique"):
			st.session_state.analysis_history = []
			st.session_state.selected_history_run_id = None
			st.success("Historique vidé")
		if st.button("Vider le cache d'analyse"):
			st.session_state.analysis_cache = {}
			st.success("Cache d'analyse vidé")

	uploaded_files = st.file_uploader(
		"Dépose un ou plusieurs PDF techniques",
		type=["pdf"],
		accept_multiple_files=True,
	)

	with st.expander("Champs extraits", expanded=False):
		st.markdown(
			"- Détection automatique du type de PDF (STEU / UDI)\n"
			"- nom de la station (STEU) ou nom UDI\n"
			"- commune\n"
			"- capacité de la station (EH)\n"
			"- année de mise en service\n"
			"- coordonnées géographiques\n"
			"- surface d'infiltration\n"
			"- ouvrages hydrauliques\n"
			"- nombre de drains / casiers\n"
			"- débit (m³/j)\n"
			"- surface potentielle solaire\n"
			"- potentiel hydraulique"
		)

	if st.button("Analyser les PDF", type="primary", disabled=not uploaded_files):
		if not uploaded_files:
			st.warning("Ajoute au moins un PDF avant l'analyse.")
			return

		success_results: list[dict] = []
		error_results: list[dict] = []
		reused_count = 0
		fresh_count = 0
		progress = st.progress(0, text="Analyse batch en cours...")
		# Reuse a single HTTP session for the full batch.
		session = requests.Session()

		for index, uploaded_file in enumerate(uploaded_files, start=1):
			file_bytes = uploaded_file.getvalue()
			cache_key = build_cache_key(file_bytes, selected_model)
			cached_entry = st.session_state.analysis_cache.get(cache_key)

			if cached_entry:
				reused_count += 1
				success_results.append(
					{
						"filename": uploaded_file.name,
						"site_name": cached_entry.get("site_name", uploaded_file.name),
						"document_type": cached_entry.get("document_type", "steu"),
						"result_json": cached_entry.get("result_json", {}),
						"description": cached_entry.get("description", ""),
						"debug": cached_entry.get("debug", {}),
					}
				)
				progress.progress(index / len(uploaded_files), text=f"Analyse {index}/{len(uploaded_files)} (cache)")
				continue

			payload, api_error = request_extract_with_retry(
				session=session,
				api_url=api_url,
				filename=uploaded_file.name,
				file_bytes=file_bytes,
				model_name=selected_model,
			)
			if api_error or not payload:
				error_results.append({"filename": uploaded_file.name, "error": api_error or "Erreur API inconnue"})
				progress.progress(index / len(uploaded_files), text=f"Analyse {index}/{len(uploaded_files)}")
				continue

			result_json = payload.get("result_json") or payload.get("result", {})
			document_type = payload.get("document_type", "steu")
			site_name = get_site_name(result_json, document_type, uploaded_file.name)
			fresh_count += 1

			cache_payload = {
				"site_name": site_name,
				"document_type": document_type,
				"result_json": result_json,
				"description": payload.get("description", ""),
				"debug": payload.get("debug", {}),
			}
			st.session_state.analysis_cache[cache_key] = cache_payload

			success_results.append(
				{
					"filename": uploaded_file.name,
					"site_name": site_name,
					"document_type": document_type,
					"result_json": result_json,
					"description": cache_payload["description"],
					"debug": cache_payload["debug"],
				}
			)
			progress.progress(index / len(uploaded_files), text=f"Analyse {index}/{len(uploaded_files)}")

		if reused_count:
			st.info(f"Réutilisation cache : {reused_count} site(s). Nouveaux calculs : {fresh_count} site(s).")

		sorted_results = sorted(
			success_results,
			key=lambda item: (normalize_sort_key(item.get("site_name", "")), normalize_sort_key(item.get("filename", ""))),
		)
		sorted_results = link_udi_entries_by_site(sorted_results)

		run_record = {
			"run_id": uuid.uuid4().hex,
			"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
			"model": selected_model,
			"api_url": api_url,
			"total_files": len(uploaded_files),
			"success_count": len(sorted_results),
			"error_count": len(error_results),
			"results": sorted_results,
			"errors": error_results,
			"udi_linking_done": True,
		}
		st.session_state.analysis_history.insert(0, run_record)
		st.session_state.selected_history_run_id = run_record["run_id"]

	if st.session_state.analysis_history:
		selected_run = render_history_selector()
		if selected_run:
			if not selected_run.get("udi_linking_done"):
				selected_run["results"] = link_udi_entries_by_site(selected_run.get("results", []))
				selected_run["udi_linking_done"] = True

			st.subheader("Résultats par site (tri automatique)")
			st.caption(
				f"Run du {selected_run['timestamp']} · {selected_run['success_count']}/{selected_run['total_files']} fichiers analysés"
			)

			tab_overview, tab_compare, tab_sites, tab_report = st.tabs(
				["Vue generale", "Comparaison", "Sites", "Rapport PDF"]
			)

			with tab_overview:
				run_results = selected_run.get("results", [])
				steu_count = sum(1 for entry in run_results if entry.get("document_type", "").lower() == "steu")
				udi_count = sum(1 for entry in run_results if entry.get("document_type", "").lower() == "udi")
				site_names = [entry.get("site_name", "Site") for entry in run_results]
				site_list_label = ", ".join(site_names[:8]) if site_names else "Aucun site"
				if len(site_names) > 8:
					site_list_label += f" ... (+{len(site_names) - 8} autres)"

				col_a, col_b, col_c = st.columns(3)
				col_a.metric("Fichiers total", selected_run.get("total_files", 0))
				col_b.metric("Succes", selected_run.get("success_count", 0))
				col_c.metric("Erreurs", selected_run.get("error_count", 0))

				st.markdown("### Description du run")
				st.info(
					f"Ce run contient **{selected_run.get('total_files', 0)}** fichier(s) "
					f"dont **{selected_run.get('success_count', 0)}** analyse(s) exploitable(s). "
					f"Types detectes : **{steu_count} STEU** et **{udi_count} UDI**."
				)
				st.markdown(
					"\n".join(
						[
							"- **Sites inclus** : " + site_list_label,
							"- **Comparaison realisee** : tableau STEU oriente PV (surface disponible) et tableau UDI oriente Hydro (debit, chute, points de pression).",
							"- **Objectif** : prioriser les sites a instruire en premier pour les etudes ENR (photovoltaïque et micro-hydraulique).",
						]
					)
				)

				if selected_run.get("error_count", 0):
					st.markdown("### Fichiers en erreur")
					for item in selected_run.get("errors", []):
						st.error(f"{item.get('filename', 'fichier')} : {item.get('error', 'Erreur inconnue')}")

			with tab_compare:
				compare_config = render_comparison_controls()
				render_comparative_analysis(selected_run.get("results", []), compare_config=compare_config)

			with tab_sites:
				site_results = selected_run.get("results", [])
				if not site_results:
					st.info("Aucun site disponible dans ce run.")
				else:
					selected_site_name = st.selectbox(
						"Selectionner un site",
						options=[entry.get("site_name", "Site") for entry in site_results],
						index=0,
					)
					selected_entry = next(
						(entry for entry in site_results if entry.get("site_name", "Site") == selected_site_name),
						site_results[0],
					)
					render_site_detail(selected_entry, show_debug=show_debug)

			with tab_report:
				st.markdown("### Rapport complet et detaille")
				if not REPORTLAB_AVAILABLE:
					st.error("Le package 'reportlab' est requis pour generer le PDF. Installe-le avec: pip install reportlab")
				else:
					pdf_data = generate_pdf_report(selected_run)
					if pdf_data:
						st.success("Rapport PDF pret.")
						st.download_button(
							label="Telecharger le rapport comparatif (.pdf)",
							data=pdf_data,
							file_name=f"rapport_comparatif_{selected_run.get('timestamp', 'run').replace(':', '-').replace(' ', '_')}.pdf",
							mime="application/pdf",
						)

				st.download_button(
					label="Telecharger le resultat brut (.json)",
					data=json.dumps(selected_run, ensure_ascii=False, indent=2),
					file_name="station_extraction_historique_run.json",
					mime="application/json",
				)


if __name__ == "__main__":
	main()
