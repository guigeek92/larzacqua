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
import streamlit.components.v1 as components

try:
	import fitz  # type: ignore
	PYMUPDF_AVAILABLE = True
except Exception:
	fitz = None  # type: ignore
	PYMUPDF_AVAILABLE = False

try:
	from reportlab.lib import colors
	from reportlab.lib.pagesizes import A4
	from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
	from reportlab.platypus import Image as RLImage
	from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
	REPORTLAB_AVAILABLE = True
except ImportError:
	REPORTLAB_AVAILABLE = False

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
	sys.path.insert(0, str(ROOT_DIR))

from src.ai_extraction import ALLOWED_MODELS
from src.run_history_store import RunHistoryStore

API_URL_DEFAULT = "http://127.0.0.1:8010/extract"
API_TIMEOUT_SECONDS = 180
API_MAX_RETRIES = 3
API_BACKOFF_SECONDS = 1.0
MAX_FILES_PER_ANALYSIS = 10
GEOCODING_TIMEOUT_SECONDS = 12
NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
GEOCODER_USER_AGENT = "energy-ai-tool/1.0 (streamlit-localisation)"
OSM_DEFAULT_ZOOM = 12
OSM_DELTA_DEGREES = 0.045
LOGO_PATH = ROOT_DIR / "Image1.png"
RUNS_DIR = ROOT_DIR / "data" / "runs"
RUN_HISTORY_DB = RUNS_DIR / "history.sqlite3"
RUN_HISTORY_STORE = RunHistoryStore(RUN_HISTORY_DB)

UDI_INFRA_ATTACHMENT_KEYWORDS = (
	"reservoir",
	"source",
	"captage",
	"forage",
	"puits",
	"pompage",
	"surpresseur",
	"brise charge",
	"reducteur pression",
	"prise eau",
	"prise d eau",
)


def inject_brand_theme() -> None:
	st.markdown(
		"""
		<style>
		@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

		:root {
			--neon-cyan: #00d4ff;
			--neon-green: #00ff9d;
			--neon-blue: #1a7fe8;
			--dark-bg: #060d1a;
			--dark-panel: #0d1a2e;
			--dark-card: #111f38;
			--dark-border: rgba(0, 212, 255, 0.18);
			--dark-border-strong: rgba(0, 212, 255, 0.42);
			--text-primary: #f2f8ff;
			--text-secondary: #c2d7e8;
			--text-muted: #9cb4c9;
			--glow-blue: 0 0 20px rgba(0, 212, 255, 0.25), 0 0 40px rgba(0, 212, 255, 0.08);
			--glow-green: 0 0 20px rgba(0, 255, 157, 0.25), 0 0 40px rgba(0, 255, 157, 0.08);
			--glow-cyan: 0 0 16px rgba(0, 212, 255, 0.45), 0 0 34px rgba(0, 212, 255, 0.2);
			--gradient-main: linear-gradient(135deg, #00d4ff 0%, #00ff9d 100%);
			--gradient-dark: linear-gradient(135deg, rgba(0,212,255,0.12) 0%, rgba(0,255,157,0.08) 100%);
		}

		/* ── FOND GLOBAL ── */
		.stApp, .stApp > div, [data-testid="stAppViewContainer"] {
			background: var(--dark-bg) !important;
			color: var(--text-primary) !important;
			font-family: 'Inter', sans-serif !important;
		}

		/* ── LISIBILITÉ GLOBALE TEXTE ── */
		p,
		span,
		label,
		li,
		div[data-testid="stMarkdownContainer"],
		[data-testid="stText"],
		[data-testid="stCaptionContainer"] {
			color: var(--text-secondary) !important;
		}

		[data-testid="stCaptionContainer"],
		small {
			color: var(--text-muted) !important;
		}

		strong,
		b {
			color: var(--text-primary) !important;
		}

		[data-testid="stHeader"] {
			background: transparent !important;
			border-bottom: none !important;
			height: 0 !important;
		}

		[data-testid="stToolbar"] {
			right: 0.6rem !important;
			top: 0.4rem !important;
		}

		/* Grid subtle en fond */
		[data-testid="stAppViewContainer"]::before {
			content: '';
			position: fixed;
			inset: 0;
			background-image:
				linear-gradient(rgba(0,212,255,0.03) 1px, transparent 1px),
				linear-gradient(90deg, rgba(0,212,255,0.03) 1px, transparent 1px);
			background-size: 40px 40px;
			pointer-events: none;
			z-index: 0;
		}

		/* ── SIDEBAR ── */
		[data-testid="stSidebar"] {
			background: var(--dark-panel) !important;
			border-right: 1px solid var(--dark-border) !important;
		}
		[data-testid="stSidebar"] * {
			color: var(--text-primary) !important;
		}

		/* ── TITRES ── */
		h1, h2, h3 {
			color: var(--text-primary) !important;
			font-family: 'Inter', sans-serif !important;
		}
		h4, h5, h6 {
			color: var(--text-secondary) !important;
		}
		h1 { 
			background: var(--gradient-main);
			-webkit-background-clip: text;
			-webkit-text-fill-color: transparent;
			background-clip: text;
			font-weight: 700 !important;
		}

		/* ── HERO BANNER ── */
		.larzac-hero {
			padding: 1.2rem 1.5rem;
			border-radius: 16px;
			background: linear-gradient(135deg, rgba(0,212,255,0.12) 0%, rgba(0,255,157,0.08) 100%);
			border: 1px solid var(--dark-border-strong);
			box-shadow: var(--glow-blue);
			margin-bottom: 1rem;
			position: relative;
			overflow: hidden;
		}
		.larzac-hero::before {
			content: '';
			position: absolute;
			top: -50%;
			right: -10%;
			width: 300px;
			height: 300px;
			background: radial-gradient(circle, rgba(0,212,255,0.08) 0%, transparent 70%);
			pointer-events: none;
		}

		/* ── CARTES ── */
		.larzac-card {
			padding: 1rem 1.2rem;
			border-radius: 12px;
			border-left: 3px solid var(--neon-cyan);
			background: var(--dark-card);
			box-shadow: var(--glow-blue);
			margin-bottom: 0.6rem;
			transition: transform 0.2s ease, box-shadow 0.2s ease;
		}
		.larzac-card:hover {
			transform: translateY(-2px);
			box-shadow: 0 0 28px rgba(0,212,255,0.35), 0 0 56px rgba(0,212,255,0.12);
		}
		.larzac-card strong { color: var(--neon-cyan); }

		/* ── BOUTON PRIMAIRE (Analyser les PDF) ── */
		.stButton > button[kind="primary"],
		button[data-testid="baseButton-primary"] {
			background: transparent !important;
			border: 2px solid var(--neon-cyan) !important;
			color: var(--neon-cyan) !important;
			font-weight: 700 !important;
			font-size: 1rem !important;
			letter-spacing: 0.08em !important;
			text-transform: uppercase !important;
			border-radius: 8px !important;
			padding: 0.7rem 1.5rem !important;
			box-shadow: 0 0 14px rgba(0,212,255,0.35), inset 0 0 14px rgba(0,212,255,0.06) !important;
			transition: all 0.25s ease !important;
			position: relative !important;
			overflow: hidden !important;
		}
		.stButton > button[kind="primary"]:hover,
		button[data-testid="baseButton-primary"]:hover {
			background: rgba(0,212,255,0.12) !important;
			box-shadow: 0 0 28px rgba(0,212,255,0.6), inset 0 0 28px rgba(0,212,255,0.12) !important;
			transform: translateY(-1px) !important;
		}

		/* ── BOUTONS SECONDAIRES ── */
		.stButton > button:not([kind="primary"]),
		button[data-testid="baseButton-secondary"] {
			background: var(--dark-card) !important;
			border: 1px solid var(--dark-border-strong) !important;
			color: var(--text-primary) !important;
			border-radius: 8px !important;
			font-weight: 500 !important;
			transition: all 0.2s ease !important;
		}
		.stButton > button:not([kind="primary"]):hover {
			border-color: var(--neon-cyan) !important;
			box-shadow: 0 0 12px rgba(0,212,255,0.2) !important;
		}

		/* ── DOWNLOAD BUTTON ── */
		[data-testid="stDownloadButton"] > button {
			background: linear-gradient(135deg, rgba(0,212,255,0.15) 0%, rgba(0,255,157,0.10) 100%) !important;
			border: 1px solid var(--neon-green) !important;
			color: var(--neon-green) !important;
			border-radius: 8px !important;
			font-weight: 600 !important;
			transition: all 0.2s ease !important;
		}
		[data-testid="stDownloadButton"] > button:hover {
			box-shadow: var(--glow-green) !important;
			transform: translateY(-1px) !important;
		}

		/* ── ONGLETS ── */
		div[data-baseweb="tab-list"] {
			gap: 0.3rem;
			background: var(--dark-panel) !important;
			border-radius: 10px;
			padding: 4px;
			border: 1px solid var(--dark-border);
		}
		button[data-baseweb="tab"] {
			border-radius: 8px !important;
			padding: 0.45rem 0.9rem !important;
			font-weight: 600 !important;
			color: var(--text-primary) !important;
			background: transparent !important;
			transition: all 0.2s ease !important;
			font-size: 0.82rem !important;
		}
		button[data-baseweb="tab"][aria-selected="true"] {
			background: var(--gradient-main) !important;
			color: var(--dark-bg) !important;
			box-shadow: var(--glow-cyan) !important;
		}

		/* ── MÉTRIQUES ── */
		div[data-testid="stMetric"] {
			background: var(--dark-card) !important;
			border: 1px solid var(--dark-border) !important;
			border-radius: 12px !important;
			padding: 0.8rem 1rem !important;
			transition: box-shadow 0.2s ease;
		}
		div[data-testid="stMetric"]:hover {
			box-shadow: var(--glow-blue);
		}
		div[data-testid="stMetric"] label {
			color: var(--text-muted) !important;
			font-size: 0.78rem !important;
			text-transform: uppercase !important;
			letter-spacing: 0.06em !important;
		}
		div[data-testid="stMetric"] [data-testid="stMetricValue"] {
			color: var(--neon-cyan) !important;
			font-weight: 700 !important;
			font-size: 1.5rem !important;
		}

		/* ── PROGRESS BAR ── */
		div[data-testid="stProgressBar"] > div {
			background: var(--dark-panel) !important;
			border-radius: 999px !important;
			border: 1px solid var(--dark-border) !important;
			overflow: hidden !important;
		}
		div[data-testid="stProgressBar"] > div > div {
			background: var(--gradient-main) !important;
			border-radius: 999px !important;
			box-shadow: 0 0 12px rgba(0,212,255,0.6) !important;
			animation: pulse-glow 1.5s ease-in-out infinite alternate !important;
		}
		@keyframes pulse-glow {
			from { box-shadow: 0 0 8px rgba(0,212,255,0.5); }
			to   { box-shadow: 0 0 22px rgba(0,212,255,0.9), 0 0 40px rgba(0,255,157,0.4); }
		}
		div[data-testid="stProgressBar"] p {
			color: var(--neon-cyan) !important;
			font-weight: 600 !important;
			font-size: 0.82rem !important;
			letter-spacing: 0.04em !important;
		}

		/* ── INPUTS / SELECTS ── */
		div[data-baseweb="input"] > div,
		div[data-baseweb="select"] > div:first-child,
		textarea {
			background: var(--dark-card) !important;
			border-color: var(--dark-border-strong) !important;
			color: var(--text-primary) !important;
			border-radius: 8px !important;
		}
		input,
		textarea,
		[data-baseweb="select"] * {
			color: var(--text-primary) !important;
		}
		input::placeholder,
		textarea::placeholder {
			color: var(--text-muted) !important;
			opacity: 1 !important;
		}
		div[data-baseweb="input"] > div:focus-within,
		div[data-baseweb="select"] > div:first-child:focus-within {
			border-color: var(--neon-cyan) !important;
			box-shadow: 0 0 0 2px rgba(0,212,255,0.2) !important;
		}

		/* ── FILE UPLOADER ── */
		[data-testid="stFileUploader"] {
			background: var(--dark-card) !important;
			border: 2px dashed var(--dark-border-strong) !important;
			border-radius: 12px !important;
			transition: all 0.2s ease !important;
		}
		[data-testid="stFileUploader"]:hover {
			border-color: var(--neon-cyan) !important;
			box-shadow: var(--glow-blue) !important;
		}
		[data-testid="stFileUploader"] * { color: var(--text-secondary) !important; }
		[data-testid="stFileUploader"] button,
		[data-testid="stFileUploader"] label {
			color: var(--text-primary) !important;
		}

		/* ── EXPANDERS ── */
		details[data-testid="stExpander"] {
			background: var(--dark-card) !important;
			border: 1px solid var(--dark-border) !important;
			border-radius: 10px !important;
		}
		details[data-testid="stExpander"] summary {
			color: var(--text-primary) !important;
			font-weight: 600 !important;
		}

		/* ── ALERTS ── */
		div[data-testid="stAlert"][data-baseweb="notification"] {
			border-radius: 10px !important;
			border-width: 1px !important;
		}
		/* Success */
		div[data-testid="stNotification"][kind="success"],
		div[class*="success"] { border-color: var(--neon-green) !important; }
		/* Info */
		div[data-testid="stNotification"][kind="info"] { border-color: var(--neon-cyan) !important; }

		/* ── DATAFRAME ── */
		[data-testid="stDataFrame"] {
			border: 1px solid var(--dark-border) !important;
			border-radius: 10px !important;
			overflow: hidden !important;
		}

		/* ── PANEL DOUX ── */
		.larzac-soft-panel {
			padding: 0.9rem 1.1rem;
			border-radius: 12px;
			background: var(--dark-card);
			border: 1px solid var(--dark-border);
			margin: 0.25rem 0 0.75rem 0;
		}

		/* ── SLIDERS ── */
		[data-testid="stSlider"] [role="slider"] {
			background: var(--neon-cyan) !important;
			box-shadow: 0 0 8px rgba(0,212,255,0.7) !important;
		}
		[data-testid="stSlider"] [data-testid="stSliderTrack"] > div:first-child {
			background: var(--dark-border) !important;
		}
		[data-testid="stSlider"] [data-testid="stSliderTrack"] > div:last-child {
			background: var(--gradient-main) !important;
		}

		/* ── TOGGLE ── */
		[data-testid="stToggle"] [role="switch"][aria-checked="true"] {
			background: var(--neon-cyan) !important;
		}

		/* ── CODE BLOCK ── */
		code, pre { font-family: 'JetBrains Mono', monospace !important; }
		div[data-testid="stCodeBlock"] pre {
			background: #030810 !important;
			border: 1px solid var(--dark-border) !important;
			border-radius: 8px !important;
			color: var(--neon-cyan) !important;
		}

		/* ── SPINNER ── */
		[data-testid="stSpinner"] {
			color: var(--neon-cyan) !important;
		}

		/* ── SCROLLBAR ── */
		::-webkit-scrollbar { width: 6px; height: 6px; }
		::-webkit-scrollbar-track { background: var(--dark-bg); }
		::-webkit-scrollbar-thumb { background: var(--dark-border-strong); border-radius: 3px; }
		::-webkit-scrollbar-thumb:hover { background: var(--neon-cyan); }

		/* ── RESPONSIVE ── */
		@media (max-width: 768px) {
			div[data-testid="stHorizontalBlock"] { flex-direction: column; gap: 0.5rem; }
			div[data-testid="stColumn"], div[data-testid="column"] { width: 100% !important; flex: 1 1 100% !important; }
			iframe { height: 260px !important; }
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


def _parse_float_candidate(value) -> float | None:
	if isinstance(value, (int, float)):
		return float(value)
	if not isinstance(value, str):
		return None
	cleaned = value.strip().replace(",", ".")
	if not cleaned:
		return None
	try:
		return float(cleaned)
	except ValueError:
		return None


def _is_plausible_lat_lon(lat: float, lon: float) -> bool:
	return -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


def _extract_lat_lon_from_text(text: str) -> tuple[float, float] | None:
	if not text:
		return None
	match = re.search(
		r"\b(?:lat(?:itude)?\s*[:=]?)?\s*([+-]?\d{1,2}(?:[\.,]\d{3,}))\s*[,;\s/]\s*(?:lon(?:gitude)?\s*[:=]?)?\s*([+-]?\d{1,3}(?:[\.,]\d{3,}))\b",
		text,
		re.IGNORECASE,
	)
	if not match:
		return None
	lat = _parse_float_candidate(match.group(1))
	lon = _parse_float_candidate(match.group(2))
	if lat is None or lon is None:
		return None
	if _is_plausible_lat_lon(lat, lon):
		return lat, lon
	return None


def extract_gps_coordinates(result_json: dict) -> tuple[float, float] | None:
	# Direct numeric fields from extraction have priority.
	lat = _parse_float_candidate(result_json.get("latitude") or result_json.get("lat"))
	lon = _parse_float_candidate(
		result_json.get("longitude")
		or result_json.get("lon")
		or result_json.get("lng")
	)
	if lat is not None and lon is not None and _is_plausible_lat_lon(lat, lon):
		return lat, lon

	# Fallback: scan textual fields where coordinates may have been merged.
	for field in ["coordonnees", "localisation", "nom_station", "nom_udi"]:
		value = result_json.get(field)
		if isinstance(value, str):
			from_text = _extract_lat_lon_from_text(value)
			if from_text:
				return from_text

	return None


def extract_projected_xy(coordonnees_value: str) -> tuple[float, float] | None:
	if not isinstance(coordonnees_value, str) or not coordonnees_value.strip():
		return None
	match = re.search(
		r"X\s*=\s*([0-9\s]+(?:[\.,][0-9]+)?)\s*m\s*;\s*Y\s*=\s*([0-9\s]+(?:[\.,][0-9]+)?)\s*m",
		coordonnees_value,
		re.IGNORECASE,
	)
	if not match:
		return None
	x = _parse_float_candidate(match.group(1).replace(" ", ""))
	y = _parse_float_candidate(match.group(2).replace(" ", ""))
	if x is None or y is None:
		return None
	return x, y


def _build_geocoding_queries(site_name: str, result_json: dict) -> list[str]:
	queries: list[str] = []
	name = str(result_json.get("nom_udi") or result_json.get("nom_station") or site_name or "").strip()
	localisation = str(result_json.get("localisation") or result_json.get("commune") or "").strip()
	communes = result_json.get("communes") or []
	commune_hint = ""
	if isinstance(communes, list) and communes:
		commune_hint = str(communes[0]).strip()

	reservoir_name = ""
	reservoirs = result_json.get("reservoirs_udi") or []
	if isinstance(reservoirs, list):
		for item in reservoirs:
			if not isinstance(item, dict):
				continue
			candidate = str(item.get("reservoir") or "").strip()
			if candidate:
				reservoir_name = candidate
				break

	udi_site_name = ""
	sites = result_json.get("sites_udi") or []
	if isinstance(sites, list):
		for item in sites:
			if not isinstance(item, dict):
				continue
			candidate = str(item.get("site") or "").strip()
			if candidate:
				udi_site_name = candidate
				break

	base_parts = [part for part in [name, localisation or commune_hint] if part]
	if base_parts:
		queries.append(", ".join(base_parts))
	if reservoir_name and (localisation or commune_hint):
		queries.append(f"{reservoir_name}, {localisation or commune_hint}")
	if udi_site_name and (localisation or commune_hint):
		queries.append(f"{udi_site_name}, {localisation or commune_hint}")
	if reservoir_name and name and normalize_sort_key(reservoir_name) not in normalize_sort_key(name):
		queries.append(f"{reservoir_name}, {name}")
	if name and commune_hint and commune_hint.lower() not in (localisation or "").lower():
		queries.append(f"{name}, {commune_hint}")
	if name:
		queries.append(f"{name}, Herault, France")
	if reservoir_name:
		queries.append(f"{reservoir_name}, Herault, France")
	if localisation:
		queries.append(f"{localisation}, France")

	seen: set[str] = set()
	cleaned: list[str] = []
	for query in queries:
		normalized = normalize_sort_key(query)
		if normalized and normalized not in seen:
			seen.add(normalized)
			cleaned.append(query)
	return cleaned


def _geo_match_tokens(value: str) -> list[str]:
	normalized = normalize_sort_key(value)
	normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
	stop_words = {
		"france",
		"herault",
		"reservoir",
		"reservoirt",
		"udi",
		"site",
		"station",
		"commune",
		"les",
		"des",
		"de",
		"du",
		"la",
		"le",
	}
	tokens = [token for token in normalized.split() if len(token) >= 3 and token not in stop_words]
	return tokens


def _is_incoherent_geocode_result(query: str, display_name: str) -> bool:
	query_tokens = _geo_match_tokens(query)
	if not query_tokens:
		return False
	display_tokens = set(_geo_match_tokens(display_name))
	if not display_tokens:
		return True

	shared = sum(1 for token in query_tokens if token in display_tokens)
	overlap = shared / max(1, len(query_tokens))
	return overlap < 0.34


def _classify_geocode_confidence(importance: float) -> tuple[str, str]:
	if importance >= 0.55:
		return "Élevée", "high"
	if importance >= 0.30:
		return "Moyenne", "medium"
	return "Faible", "low"


def _nominatim_lookup(query: str) -> dict | None:
	try:
		response = requests.get(
			NOMINATIM_SEARCH_URL,
			params={
				"q": query,
				"format": "jsonv2",
				"limit": 1,
				"addressdetails": 1,
			},
			headers={
				"User-Agent": GEOCODER_USER_AGENT,
				"Accept-Language": "fr",
			},
			timeout=GEOCODING_TIMEOUT_SECONDS,
		)
		response.raise_for_status()
		payload = response.json()
		if not isinstance(payload, list) or not payload:
			return None
		best = payload[0]
		lat = _parse_float_candidate(best.get("lat"))
		lon = _parse_float_candidate(best.get("lon"))
		if lat is None or lon is None or not _is_plausible_lat_lon(lat, lon):
			return None
		display_name = str(best.get("display_name") or "")
		if _is_incoherent_geocode_result(query, display_name):
			return None
		importance = _parse_float_candidate(best.get("importance")) or 0.0
		confidence_label, confidence_level = _classify_geocode_confidence(float(importance))
		return {
			"lat": lat,
			"lon": lon,
			"query": query,
			"display_name": display_name,
			"importance": float(importance),
			"confidence_label": confidence_label,
			"confidence_level": confidence_level,
		}
	except requests.RequestException:
		return None


def geocode_site_from_metadata(site_name: str, result_json: dict) -> dict | None:
	queries = _build_geocoding_queries(site_name, result_json)
	if not queries:
		return None

	for query in queries:
		cache_key = normalize_sort_key(query)
		cached = st.session_state.geocode_cache.get(cache_key)
		if cache_key in st.session_state.geocode_cache:
			if cached:
				return cached
			continue

		found = _nominatim_lookup(query)
		st.session_state.geocode_cache[cache_key] = found
		if found:
			return found

	return None


def render_osm_map(lat: float, lon: float) -> None:
	delta = OSM_DELTA_DEGREES
	bbox = f"{lon - delta:.6f}%2C{lat - delta:.6f}%2C{lon + delta:.6f}%2C{lat + delta:.6f}"
	marker = f"{lat:.6f}%2C{lon:.6f}"
	embed_url = f"https://www.openstreetmap.org/export/embed.html?bbox={bbox}&layer=mapnik&marker={marker}"
	viewer_url = f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}#map={OSM_DEFAULT_ZOOM}/{lat:.6f}/{lon:.6f}"

	components.html(
		f'<iframe width="100%" height="360" frameborder="0" scrolling="no" marginheight="0" marginwidth="0" src="{embed_url}"></iframe>',
		height=370,
	)
	st.link_button("Ouvrir dans OpenStreetMap", viewer_url)


def render_location_tab(site_name: str, result_json: dict) -> None:
	gps = extract_gps_coordinates(result_json)
	localisation_label = result_json.get("localisation") or result_json.get("commune") or "Non renseignée"
	st.write(f"- Localisation déclarée : {localisation_label}")

	if gps:
		lat, lon = gps
		col1, col2 = st.columns(2)
		col1.metric("Latitude", f"{lat:.6f}")
		col2.metric("Longitude", f"{lon:.6f}")
		render_osm_map(lat, lon)
		st.caption("Carte centrée sur les coordonnées GPS extraites du document.")
		return

	geocoded = geocode_site_from_metadata(site_name, result_json)
	if geocoded:
		lat = geocoded["lat"]
		lon = geocoded["lon"]
		col1, col2, col3 = st.columns(3)
		col1.metric("Latitude (API)", f"{lat:.6f}")
		col2.metric("Longitude (API)", f"{lon:.6f}")
		col3.metric("Confiance", geocoded.get("confidence_label", "N/D"))
		render_osm_map(lat, lon)
		st.caption(f"Adresse estimée : {geocoded.get('display_name', 'N/D')}")
		st.caption(f"Requête géocodage : {geocoded.get('query', '')}")
		if geocoded.get("confidence_level") != "high":
			st.warning("Position estimée automatiquement: validation manuelle recommandée.")
		return

	xy = extract_projected_xy(str(result_json.get("coordonnees") or ""))
	if xy:
		x, y = xy
		st.warning("Coordonnées projetées détectées (X/Y), mais pas de GPS direct (lat/lon).")
		st.write(f"- X/Y détectés : X={x:.2f} m ; Y={y:.2f} m")
		st.caption("Le géocodage par nom/adresse n'a pas trouvé de résultat fiable pour ce site.")
	else:
		st.info("Aucune coordonnée exploitable ni adresse géocodable trouvée pour ce site.")

	st.caption(f"Site : {site_name}")


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
	udi_sources = [
		str(result_json.get("nom_udi", "")),
		str(entry.get("site_name", "")),
		str(entry.get("filename", "")),
	]
	sites = result_json.get("sites_udi") or []
	if isinstance(sites, list):
		for site in sites[:3]:
			if isinstance(site, dict):
				udi_sources.append(str(site.get("site", "")))

	for source in udi_sources:
		m = re.search(r"\budi\s*([0-9]{1,3})\b", source or "", re.IGNORECASE)
		if m:
			return f"udi-{m.group(1)}"

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


def is_udi_infrastructure_attachment_filename(filename: str) -> bool:
	filename_norm = normalize_sort_key(str(filename or ""))
	if not filename_norm:
		return False
	if "synoptique" in filename_norm:
		return False
	return any(keyword in filename_norm for keyword in UDI_INFRA_ATTACHMENT_KEYWORDS)


def is_udi_infrastructure_attachment_entry(entry: dict) -> bool:
	if entry.get("document_type", "").lower() != "udi":
		return False
	return is_udi_infrastructure_attachment_filename(str(entry.get("filename", "")))


def is_udi_reservoir_attachment_entry(entry: dict) -> bool:
	# Legacy alias kept for backward compatibility with existing tests/scripts.
	return is_udi_infrastructure_attachment_entry(entry)


def _aggregate_udi_group(entries: list[dict]) -> dict:
	numeric_fields = [
		"debit_m3_j",
		"hauteur_chute_estimee_m",
		"denivele_source_reservoir_m",
		"denivele_estime_m",
		"volume_reservoir_m3",
		"volume_reference_m3_j",
		"nombre_brise_charge",
		"nombre_reducteurs_pression",
	]
	list_fields = [
		"communes",
		"altitudes_ngf_m",
		"sites_udi",
		"reservoirs_udi",
		"description_reservoirs",
		"volume_reservoir_confidence_by_site",
		"points_pression_reduction",
		"emplacements_turbine_potentiels",
		"elements_interessants_micro_hydro",
		"contraintes_techniques",
	]
	text_fields = ["nom_udi", "localisation", "volume_reservoir_confidence"]

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

	reducers_presence_values = [
		entry.get("result_json", {}).get("presence_reducteurs_pression")
		for entry in entries
		if entry.get("result_json", {}).get("presence_reducteurs_pression") in (True, False)
	]
	if reducers_presence_values:
		aggregated["presence_reducteurs_pression"] = True if any(reducers_presence_values) else False

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

	confidence_rank = {"low": 0, "medium": 1, "high": 2}
	best_confidence = "low"
	for entry in entries:
		level = str(entry.get("result_json", {}).get("volume_reservoir_confidence") or "low").lower()
		if level in confidence_rank and confidence_rank[level] > confidence_rank[best_confidence]:
			best_confidence = level
	aggregated["volume_reservoir_confidence"] = best_confidence

	return aggregated


def _split_single_udi_entry_by_sites(entry: dict) -> list[dict]:
	if entry.get("document_type", "").lower() != "udi":
		return [entry]

	result_json = entry.get("result_json", {})
	sites = result_json.get("sites_udi") or []
	if not isinstance(sites, list):
		sites = []

	reservoirs = result_json.get("reservoirs_udi") or []
	if not isinstance(reservoirs, list):
		reservoirs = []

	forced_udi_number = _forced_udi_number_from_filename(str(entry.get("filename", "")))
	if not forced_udi_number:
		# Keep a single card if the PDF was not physically segmented first.
		return [entry]

	if len(sites) <= 1 and reservoirs:
		# Fallback: build per-site stubs from reservoir labels when sites_udi is incomplete.
		sites_from_res: list[dict] = []
		seen_site_names: set[str] = set()
		for res in reservoirs:
			if not isinstance(res, dict):
				continue
			res_site = str(res.get("site_udi") or "").strip()
			if not res_site:
				continue
			key = normalize_sort_key(res_site)
			if key in seen_site_names:
				continue
			seen_site_names.add(key)
			sites_from_res.append({"site": res_site})

		if len(sites_from_res) > 1:
			sites = sites_from_res

	if len(sites) <= 1:
		return [entry]

	split_entries: list[dict] = []
	for idx, site in enumerate(sites, start=1):
		if not isinstance(site, dict):
			continue

		site_name = str(site.get("site") or "").strip() or f"{entry.get('site_name', 'Site')} - UDI {idx}"
		site_name_key = _normalize_udi_identifier(site_name)
		site_udi_num_match = re.search(r"\budi\s*([0-9]{1,3})\b", site_name, re.IGNORECASE)
		site_udi_num = site_udi_num_match.group(1) if site_udi_num_match else None
		if site_udi_num and site_udi_num != forced_udi_number:
			continue

		site_reservoirs: list[dict] = []
		for res in reservoirs:
			if not isinstance(res, dict):
				continue
			res_site_name = str(res.get("site_udi") or "").strip()
			if res_site_name and _normalize_udi_identifier(res_site_name) == site_name_key:
				site_reservoirs.append(res)
				continue
			if site_udi_num:
				res_udi_num_match = re.search(r"\budi\s*([0-9]{1,3})\b", res_site_name, re.IGNORECASE)
				res_udi_num = res_udi_num_match.group(1) if res_udi_num_match else None
				if res_udi_num == site_udi_num:
					site_reservoirs.append(res)

		new_result_json = dict(result_json)
		new_result_json["sites_udi"] = [site]
		new_result_json["reservoirs_udi"] = site_reservoirs
		new_result_json["description_reservoirs"] = _filter_description_reservoirs_for_site(
			result_json.get("description_reservoirs") or [],
			site_name,
			site_reservoirs,
		)
		new_result_json["nom_udi"] = site_name

		signed = site.get("denivele_source_reservoir_m")
		if not isinstance(signed, (int, float)) and site_reservoirs:
			res_signed = [
				res.get("denivele_source_reservoir_m")
				for res in site_reservoirs
				if isinstance(res.get("denivele_source_reservoir_m"), (int, float))
			]
			if res_signed:
				signed = max((float(v) for v in res_signed), key=lambda x: abs(x))
		if isinstance(signed, (int, float)):
			new_result_json["denivele_source_reservoir_m"] = float(signed)
			new_result_json["denivele_estime_m"] = abs(float(signed))
			new_result_json["hauteur_chute_estimee_m"] = float(signed)
			new_result_json["potentiel_hydraulique"] = bool(float(signed) > 0)

		if isinstance(site.get("volume_reservoir_m3"), (int, float)):
			new_result_json["volume_reservoir_m3"] = float(site.get("volume_reservoir_m3"))
			site_conf = str(site.get("volume_reservoir_confidence") or "").lower()
			if site_conf in {"high", "medium", "low"}:
				new_result_json["volume_reservoir_confidence"] = site_conf
		elif site_reservoirs:
			vols = [res.get("volume_reservoir_m3") for res in site_reservoirs if isinstance(res.get("volume_reservoir_m3"), (int, float))]
			if vols:
				new_result_json["volume_reservoir_m3"] = max(float(v) for v in vols)
				if new_result_json.get("volume_reservoir_confidence") not in {"high", "medium", "low"}:
					new_result_json["volume_reservoir_confidence"] = "medium"

		new_entry = dict(entry)
		new_entry["site_name"] = site_name
		new_entry["result_json"] = new_result_json
		new_entry["description"] = _filter_udi_description_for_site(str(entry.get("description") or ""), site_name)
		debug_info = dict(entry.get("debug", {}) or {})
		debug_info["udi_site_split"] = {
			"split_from_file": entry.get("filename", ""),
			"site_name": site_name,
			"site_index": idx,
			"site_count": len(sites),
			"forced_udi": forced_udi_number,
		}
		new_entry["debug"] = debug_info
		split_entries.append(new_entry)

	return split_entries or [entry]


def expand_udi_results_by_sites(results: list[dict]) -> list[dict]:
	if not results:
		return results

	expanded: list[dict] = []
	for entry in results:
		expanded.extend(_split_single_udi_entry_by_sites(entry))
	return expanded


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
		has_primary_entry = any(not is_udi_infrastructure_attachment_entry(item) for item in group_entries)
		if is_udi_infrastructure_attachment_entry(entry) and has_primary_entry:
			# Reservoir sheets enrich the main UDI site but should not create standalone site cards.
			continue
		aggregated = _aggregate_udi_group(group_entries)

		new_entry = dict(entry)
		new_result_json = dict(entry.get("result_json", {}))
		filled_fields: list[str] = []
		for field, value in aggregated.items():
			existing_value = new_result_json.get(field)
			if isinstance(existing_value, list) and isinstance(value, list):
				merged_list = list(existing_value)
				for item in value:
					if item not in merged_list:
						merged_list.append(item)
				if merged_list != existing_value:
					new_result_json[field] = merged_list
					filled_fields.append(field)
				continue

			if field not in new_result_json or is_missing_value(existing_value):
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


def _get_linked_udi_entries(entry: dict, all_results: list[dict] | None) -> list[dict]:
	if entry.get("document_type", "").lower() != "udi" or not all_results:
		return []

	target_key = entry.get("site_group_key") or infer_udi_site_group_key(entry)
	linked: list[dict] = []
	for candidate in all_results:
		if candidate.get("document_type", "").lower() != "udi":
			continue
		candidate_key = candidate.get("site_group_key") or infer_udi_site_group_key(candidate)
		if candidate_key == target_key:
			linked.append(candidate)
	return linked


def render_infrastructure_site_tab(entry: dict, all_results: list[dict] | None) -> None:
	if entry.get("document_type", "").lower() != "udi":
		st.info("Cet onglet est spécifique aux sites UDI.")
		return

	debug_info = dict(entry.get("debug", {}) or {})
	linking = dict(debug_info.get("udi_linking", {}) or {})
	group_key = linking.get("group_key") or entry.get("site_group_key") or infer_udi_site_group_key(entry)

	linked_entries = _get_linked_udi_entries(entry, all_results)
	if linked_entries:
		related_files = [item.get("filename", "") for item in linked_entries if item.get("filename")]
	else:
		related_files = [str(name) for name in (linking.get("related_files") or []) if str(name).strip()]

	if not related_files:
		current_filename = entry.get("filename", "")
		related_files = [current_filename] if current_filename else []

	dedup_related: list[str] = []
	for name in related_files:
		if name and name not in dedup_related:
			dedup_related.append(name)

	attachment_files: list[str] = []
	main_files: list[str] = []
	if linked_entries:
		for item in linked_entries:
			filename = str(item.get("filename") or "")
			if not filename:
				continue
			if is_udi_infrastructure_attachment_entry(item):
				attachment_files.append(filename)
			else:
				main_files.append(filename)
	else:
		current_name = str(entry.get("filename") or "")
		for filename in dedup_related:
			if filename == current_name:
				main_files.append(filename)
			elif is_udi_infrastructure_attachment_filename(filename):
				attachment_files.append(filename)
			else:
				main_files.append(filename)

	st.write(f"- Clé de regroupement UDI : `{group_key}`")
	st.write(f"- Fichiers liés au site : {len(dedup_related)}")

	if main_files:
		st.markdown("**Fichier(s) principal(aux) UDI**")
		for filename in sorted(set(main_files), key=normalize_sort_key):
			st.write(f"- {filename}")

	if attachment_files:
		st.markdown("**Fichier(s) complémentaire(s) infrastructure**")
		for filename in sorted(set(attachment_files), key=normalize_sort_key):
			st.write(f"- {filename}")

	filled_fields = linking.get("filled_fields") or []
	if isinstance(filled_fields, list) and filled_fields:
		st.markdown("**Champs complétés grâce aux fichiers liés**")
		for field in filled_fields:
			st.write(f"- {field}")
	else:
		st.caption("Aucun champ complémentaire explicite n'a été tracé pour ce site sur ce run.")


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
		if (isinstance(denivele_sr, (int, float)) and denivele_sr <= 0) or (
			isinstance(hauteur, (int, float)) and hauteur <= 0
		):
			lines.append("NO_HEAD_WARNING")
		vol_res = result_json.get("volume_reservoir_m3")
		if vol_res is not None:
			lines.append(f"Volume réservoir : {vol_res} m³")
		conf = str(result_json.get("volume_reservoir_confidence") or "").lower()
		if conf in {"high", "medium", "low"}:
			conf_label = {"high": "élevée", "medium": "moyenne", "low": "faible"}[conf]
			lines.append(f"Confiance volume réservoir : {conf_label}")
		reducers_present = result_json.get("presence_reducteurs_pression")
		reducers_count = result_json.get("nombre_reducteurs_pression")
		if reducers_present is True:
			lines.append(f"Réducteurs de pression : présents ({reducers_count if reducers_count is not None else 'N/D'})")
		elif reducers_present is False:
			lines.append("Réducteurs de pression : absents")
		sites = result_json.get("sites_udi") or []
		if sites:
			lines.append(f"Sites UDI analysés : {len(sites)}")
			for site in sites:
				if not isinstance(site, dict):
					continue
				site_name = str(site.get("site", "Site UDI")).strip() or "Site UDI"
				site_drop = site.get("denivele_source_reservoir_m")
				if isinstance(site_drop, (int, float)) and site_drop <= 0:
					lines.append(f"NO_HEAD_SITE:{site_name}")
		points = result_json.get("points_pression_reduction") or []
		if points:
			lines.append(f"Points de réduction de pression détectés : {len(points)}")
		reservoirs = result_json.get("reservoirs_udi") or []
		if reservoirs:
			lines.append(f"Réservoirs détectés : {len(reservoirs)}")
			for res in reservoirs[:5]:
				if not isinstance(res, dict):
					continue
				res_name = str(res.get("reservoir") or "Réservoir")
				head = res.get("hauteur_chute_disponible_m")
				if isinstance(head, (int, float)):
					lines.append(f"  - {res_name}: chute dispo {head} m")
				else:
					lines.append(f"  - {res_name}: pas de hauteur de chute")

		description_reservoirs = result_json.get("description_reservoirs") or []
		if isinstance(description_reservoirs, list) and description_reservoirs:
			description_reservoirs = _filter_description_reservoirs_for_site(
				description_reservoirs,
				str(result_json.get("nom_udi") or ""),
				result_json.get("reservoirs_udi") or [],
			)
		if isinstance(description_reservoirs, list) and description_reservoirs:
			lines.append("Description réservoirs :")
			for item in description_reservoirs[:6]:
				if isinstance(item, str) and item.strip():
					lines.append(f"  - {item.strip()}")

		interesting = result_json.get("elements_interessants_micro_hydro") or []
		if isinstance(interesting, list) and interesting:
			lines.append("Éléments intéressants micro-hydro :")
			for item in interesting[:8]:
				if isinstance(item, str) and item.strip():
					lines.append(f"  - {item.strip()}")

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


def _to_positive_float(value) -> float | None:
	parsed = _parse_float_candidate(value)
	if parsed is None or parsed <= 0:
		return None
	return float(parsed)


def _get_hydro_head_m(result_json: dict) -> float | None:
	# Prefer direct estimated head, then fallback to absolute source->reservoir drop.
	head = _to_positive_float(result_json.get("hauteur_chute_estimee_m"))
	if head is not None:
		return head

	denivele_sr = _parse_float_candidate(result_json.get("denivele_source_reservoir_m"))
	if isinstance(denivele_sr, (int, float)) and denivele_sr != 0:
		return abs(float(denivele_sr))

	return None


def compute_site_enr_simulation(
	result_json: dict,
	document_type: str,
	pv_specific_yield_kwh_kwp: float,
	pv_kwp_per_m2: float,
	pv_performance_ratio: float,
	hydro_efficiency: float,
	hydro_operating_hours: int,
	co2_factor_kg_per_kwh: float,
) -> dict:
	# --- PV ---
	pv_surface_m2 = _to_positive_float(result_json.get("surface_potentielle_solaire_m2"))
	pv_capacity_kwp = 0.0
	pv_energy_kwh_year = 0.0
	if pv_surface_m2 is not None:
		pv_capacity_kwp = pv_surface_m2 * max(0.0, pv_kwp_per_m2)
		pv_energy_kwh_year = pv_capacity_kwp * max(0.0, pv_specific_yield_kwh_kwp) * max(0.0, pv_performance_ratio)

	# --- Hydro ---
	flow_m3_day = _to_positive_float(result_json.get("debit_m3_j"))
	head_m = _get_hydro_head_m(result_json)
	hydro_power_kw = 0.0
	hydro_energy_kwh_year = 0.0
	if flow_m3_day is not None and head_m is not None:
		flow_m3_s = flow_m3_day / 86400.0
		eta = max(0.0, hydro_efficiency)
		# P(kW) = rho*g*Q*H*eta / 1000 with rho~=1000 kg/m3 and g=9.81 m/s2.
		hydro_power_kw = 9.81 * flow_m3_s * head_m * eta
		hydro_energy_kwh_year = hydro_power_kw * max(0, hydro_operating_hours)

	total_energy_kwh_year = pv_energy_kwh_year + hydro_energy_kwh_year
	co2_avoided_tons_year = (total_energy_kwh_year * max(0.0, co2_factor_kg_per_kwh)) / 1000.0

	return {
		"document_type": document_type,
		"pv_surface_m2": pv_surface_m2,
		"pv_capacity_kwp": pv_capacity_kwp,
		"pv_energy_kwh_year": pv_energy_kwh_year,
		"hydro_flow_m3_day": flow_m3_day,
		"hydro_head_m": head_m,
		"hydro_power_kw": hydro_power_kw,
		"hydro_energy_kwh_year": hydro_energy_kwh_year,
		"total_energy_kwh_year": total_energy_kwh_year,
		"co2_avoided_tons_year": co2_avoided_tons_year,
	}


def render_simulation_tab(result_json: dict, document_type: str, key_prefix: str) -> None:
	st.caption("Simulation simplifiée pour une première évaluation du potentiel ENR du site.")

	if document_type == "udi":
		default_hydro_hours = 4500
		default_pv_yield = 1450
	else:
		default_hydro_hours = 3500
		default_pv_yield = 1350

	col_cfg1, col_cfg2 = st.columns(2)
	with col_cfg1:
		pv_specific_yield_kwh_kwp = st.slider(
			"Productible PV spécifique (kWh/kWc/an)",
			min_value=900,
			max_value=1900,
			value=default_pv_yield,
			step=50,
			key=f"sim_pv_yield_{key_prefix}",
		)
		pv_kwp_per_m2 = st.slider(
			"Densité PV (kWc/m²)",
			min_value=0.10,
			max_value=0.30,
			value=0.20,
			step=0.01,
			key=f"sim_pv_density_{key_prefix}",
		)
		pv_performance_ratio = st.slider(
			"Performance ratio PV",
			min_value=0.60,
			max_value=1.00,
			value=0.82,
			step=0.01,
			key=f"sim_pv_pr_{key_prefix}",
		)
	with col_cfg2:
		hydro_efficiency = st.slider(
			"Rendement hydro global",
			min_value=0.40,
			max_value=0.90,
			value=0.70,
			step=0.01,
			key=f"sim_hydro_eta_{key_prefix}",
		)
		hydro_operating_hours = st.slider(
			"Heures de fonctionnement hydro (h/an)",
			min_value=1000,
			max_value=8500,
			value=default_hydro_hours,
			step=100,
			key=f"sim_hydro_hours_{key_prefix}",
		)
		co2_factor_kg_per_kwh = st.slider(
			"Facteur CO2 évité (kgCO2/kWh)",
			min_value=0.02,
			max_value=0.90,
			value=0.06,
			step=0.01,
			key=f"sim_co2_factor_{key_prefix}",
		)

	sim = compute_site_enr_simulation(
		result_json=result_json,
		document_type=document_type,
		pv_specific_yield_kwh_kwp=float(pv_specific_yield_kwh_kwp),
		pv_kwp_per_m2=float(pv_kwp_per_m2),
		pv_performance_ratio=float(pv_performance_ratio),
		hydro_efficiency=float(hydro_efficiency),
		hydro_operating_hours=int(hydro_operating_hours),
		co2_factor_kg_per_kwh=float(co2_factor_kg_per_kwh),
	)

	col_m1, col_m2, col_m3 = st.columns(3)
	col_m1.metric("Production PV", f"{sim['pv_energy_kwh_year'] / 1000:.1f} MWh/an")
	col_m2.metric("Production Hydro", f"{sim['hydro_energy_kwh_year'] / 1000:.1f} MWh/an")
	col_m3.metric("Production ENR totale", f"{sim['total_energy_kwh_year'] / 1000:.1f} MWh/an")

	col_d1, col_d2 = st.columns(2)
	with col_d1:
		st.markdown("**Détails PV**")
		if sim["pv_surface_m2"] is None:
			st.info("Surface PV non disponible dans l'extraction pour ce site.")
		else:
			st.write(f"- Surface considérée : {sim['pv_surface_m2']:.1f} m²")
			st.write(f"- Puissance installable estimée : {sim['pv_capacity_kwp']:.1f} kWc")

	with col_d2:
		st.markdown("**Détails Hydro**")
		if sim["hydro_flow_m3_day"] is None or sim["hydro_head_m"] is None:
			st.info("Débit et/ou hauteur de chute non disponibles pour la simulation hydro.")
		else:
			st.write(f"- Débit considéré : {sim['hydro_flow_m3_day']:.1f} m³/j")
			st.write(f"- Hauteur de chute considérée : {sim['hydro_head_m']:.1f} m")
			st.write(f"- Puissance hydro estimée : {sim['hydro_power_kw']:.2f} kW")

	# Detailed transparency block for simulation assumptions and missing inputs.
	with st.expander("Détail du calcul et données manquantes", expanded=False):
		st.markdown("**Formules utilisées**")
		st.code(
			"PV_kWc = Surface_PV_m² x Densité_kWc_m²\n"
			"PV_kWh_an = PV_kWc x Productible_kWh_kWc_an x Performance_ratio\n"
			"Q_m3_s = Débit_m3_j / 86400\n"
			"P_hydro_kW = 9.81 x Q_m3_s x H_m x Rendement\n"
			"E_hydro_kWh_an = P_hydro_kW x Heures_fonctionnement_an\n"
			"E_totale_kWh_an = E_PV_kWh_an + E_hydro_kWh_an\n"
			"CO2_t_an = (E_totale_kWh_an x Facteur_kgCO2_kWh) / 1000",
			language="text",
		)

		st.markdown("**Valeurs appliquées au site**")
		st.write(
			f"- PV: surface={sim['pv_surface_m2'] if sim['pv_surface_m2'] is not None else 'N/D'} m², "
			f"densité={float(pv_kwp_per_m2):.2f} kWc/m², "
			f"productible={int(pv_specific_yield_kwh_kwp)} kWh/kWc/an, PR={float(pv_performance_ratio):.2f}"
		)
		st.write(
			f"- Hydro: débit={sim['hydro_flow_m3_day'] if sim['hydro_flow_m3_day'] is not None else 'N/D'} m³/j, "
			f"chute={sim['hydro_head_m'] if sim['hydro_head_m'] is not None else 'N/D'} m, "
			f"rendement={float(hydro_efficiency):.2f}, heures={int(hydro_operating_hours)} h/an"
		)
		st.write(f"- CO2: facteur={float(co2_factor_kg_per_kwh):.2f} kgCO2/kWh")

		missing_inputs: list[str] = []
		if sim["pv_surface_m2"] is None:
			missing_inputs.append("surface_potentielle_solaire_m2")
		if sim["hydro_flow_m3_day"] is None:
			missing_inputs.append("debit_m3_j")
		if sim["hydro_head_m"] is None:
			missing_inputs.append("hauteur_chute_estimee_m / denivele_source_reservoir_m")

		if missing_inputs:
			st.warning("Données manquantes impactant la simulation:")
			for item in missing_inputs:
				st.write(f"- {item}")
			st.caption("Les composantes concernées sont mises à 0 tant que ces données ne sont pas disponibles.")
		else:
			st.success("Toutes les données d'entrée principales sont disponibles pour la simulation PV + Hydro.")

	st.success(f"CO2 évité estimé : {sim['co2_avoided_tons_year']:.1f} tCO2/an")
	st.caption("Hypothèses simplifiées: résultats indicatifs à valider par une étude technico-économique détaillée.")


def init_session_state() -> None:
	if "analysis_history" not in st.session_state:
		st.session_state.analysis_history = load_persisted_runs(limit=30)
	if "selected_history_run_id" not in st.session_state:
		st.session_state.selected_history_run_id = None
	if "analysis_cache" not in st.session_state:
		st.session_state.analysis_cache = {}
	if "geocode_cache" not in st.session_state:
		st.session_state.geocode_cache = {}
	if "last_completed_run_id" not in st.session_state:
		st.session_state.last_completed_run_id = None
	if "selected_site_idx" not in st.session_state:
		st.session_state.selected_site_idx = 0


def load_persisted_runs(limit: int = 30) -> list[dict]:
	runs = RUN_HISTORY_STORE.list_runs(limit=limit)
	if runs:
		return runs

	if not RUNS_DIR.exists():
		return []

	legacy_runs: list[dict] = []
	for run_file in sorted(RUNS_DIR.glob("run_*.json"), reverse=True):
		try:
			run = json.loads(run_file.read_text(encoding="utf-8"))
			if not isinstance(run, dict):
				continue
			if not run.get("run_id"):
				run["run_id"] = uuid.uuid4().hex
			RUN_HISTORY_STORE.upsert_run(run)
			legacy_runs.append(run)
		except Exception:
			continue
		if len(legacy_runs) >= limit:
			break

	if legacy_runs:
		return RUN_HISTORY_STORE.list_runs(limit=limit)
	return []


def persist_run_record(run_record: dict) -> None:
	RUNS_DIR.mkdir(parents=True, exist_ok=True)
	run_id = run_record.get("run_id", uuid.uuid4().hex)
	run_record["run_id"] = run_id
	RUN_HISTORY_STORE.upsert_run(run_record)
	run_file = RUNS_DIR / f"run_{run_id}.json"
	run_file.write_text(json.dumps(run_record, ensure_ascii=False, indent=2), encoding="utf-8")


def render_run_data_editor(selected_run: dict) -> None:
	run_results = selected_run.get("results", [])
	editable_indices = [
		idx
		for idx, entry in enumerate(run_results)
		if isinstance(entry, dict) and not is_udi_infrastructure_attachment_entry(entry)
	]
	if not editable_indices:
		st.info("Aucune donnée de site éditable dans ce run.")
		return

	run_id = str(selected_run.get("run_id") or "")
	labels: list[str] = []
	label_to_index: dict[str, int] = {}
	for idx in editable_indices:
		entry = run_results[idx]
		site_name = entry.get("site_name", f"Site {idx + 1}")
		doc_type = str(entry.get("document_type", "-")).upper()
		label = f"{site_name} ({doc_type}) #{idx + 1}"
		labels.append(label)
		label_to_index[label] = idx

	selected_label = st.selectbox(
		"Site à mettre à jour",
		options=labels,
		key=f"run-editor-site-{run_id}",
	)
	entry_index = label_to_index[selected_label]
	entry = run_results[entry_index]
	json_key = f"run-editor-json-{run_id}-{entry_index}"
	default_json_payload = json.dumps(entry.get("result_json", {}), ensure_ascii=False, indent=2)
	if json_key not in st.session_state:
		st.session_state[json_key] = default_json_payload

	st.text_area(
		"Données JSON du site",
		height=320,
		key=json_key,
		help="Modifie les champs extraits puis enregistre pour persister la mise à jour.",
	)

	if st.button(
		"Enregistrer la mise à jour",
		key=f"run-editor-save-{run_id}-{entry_index}",
		use_container_width=True,
	):
		try:
			updated_result_json = json.loads(st.session_state[json_key])
			expected_doc_type = str(entry.get("document_type", "steu"))
			expected_filename = str(entry.get("filename", "site.pdf"))
			entry["result_json"] = updated_result_json
			entry["site_name"] = get_site_name(updated_result_json, expected_doc_type, expected_filename)
		except json.JSONDecodeError as err:
			st.error(f"JSON invalide: {err}")
			return

		selected_run["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
		selected_run["last_updated_at"] = datetime.now().isoformat(timespec="seconds")
		persist_run_record(selected_run)

		history = [
			run
			for run in st.session_state.analysis_history
			if str(run.get("run_id") or "") != run_id
		]
		history.insert(0, selected_run)
		st.session_state.analysis_history = history
		st.session_state.selected_history_run_id = run_id
		st.success("Mise à jour enregistrée dans l'historique permanent.")


def build_cache_key(file_bytes: bytes, model_name: str) -> str:
	content_hash = hashlib.sha256(file_bytes).hexdigest()
	return f"{model_name}:{content_hash}"


def _first_udi_number(text: str) -> str | None:
	m = re.search(r"\bUDI\s*([0-9]{1,3})\b", text or "", re.IGNORECASE)
	return m.group(1) if m else None


def _all_udi_numbers(text: str) -> list[str]:
	if not text:
		return []
	seen: list[str] = []
	for m in re.finditer(r"\bUDI\s*([0-9]{1,3})\b", text, re.IGNORECASE):
		num = m.group(1)
		if num not in seen:
			seen.append(num)
	return seen


def _udi_numbers_from_filename(filename: str) -> list[str]:
	"""Extract UDI numbers from compact filenames like 'UDI 7 ... & 9 ... -24 ...'."""
	base = re.sub(r"\.[Pp][Dd][Ff]$", "", str(filename or ""))
	if not base:
		return []

	seen: list[str] = []
	for match in re.finditer(r"\bUDI\s*([0-9]{1,3})(?:[a-z])?\b", base, flags=re.IGNORECASE):
		num = match.group(1)
		if num not in seen:
			seen.append(num)

	if "udi" not in base.lower():
		return seen

	for match in re.finditer(r"(?:\&|\bet\b|,|/|\-)\s*([0-9]{1,3})(?:[a-z])?\b", base, flags=re.IGNORECASE):
		num = match.group(1)
		if num not in seen:
			seen.append(num)

	return seen


def _extract_udi_number(text: str) -> str | None:
	m = re.search(r"\budi\s*([0-9]{1,3})\b", str(text or ""), re.IGNORECASE)
	return m.group(1) if m else None


def _normalize_udi_identifier(text: str) -> str:
	number = _extract_udi_number(text)
	if number:
		return f"udi-{number}"
	return normalize_sort_key(str(text or ""))


def _filter_udi_description_for_site(description: str, site_name: str) -> str:
	text = str(description or "").strip()
	if not text:
		return text

	target_udi = _extract_udi_number(site_name)
	if not target_udi:
		return text

	other_udi_ids = [num for num in _all_udi_numbers(text) if num != target_udi]
	if not other_udi_ids:
		return text

	paragraphs = [chunk.strip() for chunk in re.split(r"\n{2,}", text) if chunk.strip()]
	if not paragraphs:
		return text

	filtered: list[str] = []
	target_pattern = re.compile(rf"\bUDI\s*{re.escape(target_udi)}\b", re.IGNORECASE)
	other_patterns = [re.compile(rf"\bUDI\s*{re.escape(uid)}\b", re.IGNORECASE) for uid in other_udi_ids]
	for para in paragraphs:
		has_target = bool(target_pattern.search(para))
		has_other = any(pattern.search(para) for pattern in other_patterns)
		if has_target or not has_other:
			filtered.append(para)

	return "\n\n".join(filtered) if filtered else text


def _filter_description_reservoirs_for_site(
	description_reservoirs: list,
	site_name: str,
	site_reservoirs: list[dict],
) -> list:
	if not isinstance(description_reservoirs, list) or not description_reservoirs:
		return []

	reservoir_tokens = {
		normalize_sort_key(str(res.get("reservoir") or ""))
		for res in site_reservoirs
		if isinstance(res, dict) and str(res.get("reservoir") or "").strip()
	}
	target_udi = _extract_udi_number(site_name)

	filtered: list[str] = []
	for item in description_reservoirs:
		if not isinstance(item, str):
			continue
		entry = item.strip()
		if not entry:
			continue
		entry_norm = normalize_sort_key(entry)
		if reservoir_tokens and any(token and token in entry_norm for token in reservoir_tokens):
			filtered.append(entry)
			continue
		if target_udi and re.search(rf"\budi\s*{re.escape(target_udi)}\b", entry, re.IGNORECASE):
			filtered.append(entry)

	if filtered:
		return filtered

	if target_udi:
		fallback = [
			item
			for item in description_reservoirs
			if isinstance(item, str) and re.search(rf"\budi\s*{re.escape(target_udi)}\b", item, re.IGNORECASE)
		]
		if fallback:
			return fallback

	return [item for item in description_reservoirs if isinstance(item, str)]


def _detect_udi_markers_on_page(page) -> list[tuple[str, float, float]]:
	"""Return ordered (udi_number, x_center, y_top) markers detected from text lines on a page."""
	markers: list[tuple[str, float, float]] = []
	try:
		text_dict = page.get_text("dict") or {}
		for block in text_dict.get("blocks", []):
			if block.get("type") != 0:
				continue
			for line in block.get("lines", []):
				spans = line.get("spans", []) or []
				line_text = "".join(str(span.get("text") or "") for span in spans).strip()
				m = re.search(r"^\s*UDI\s*([0-9]{1,3})\b", line_text, re.IGNORECASE)
				if not m:
					continue
				bbox = line.get("bbox") or [0, 0, 0, 0]
				x_center = float((float(bbox[0]) + float(bbox[2])) / 2.0)
				y_top = float(bbox[1])
				markers.append((m.group(1), x_center, y_top))
	except Exception:
		return []

	if not markers:
		return []

	markers.sort(key=lambda item: (item[2], item[1]))
	filtered: list[tuple[str, float, float]] = []
	seen_nums: set[str] = set()
	for num, x, y in markers:
		if num in seen_nums:
			continue
		seen_nums.add(num)
		filtered.append((num, x, y))

	return filtered


def _build_udi_anchor_cells(markers: list[tuple[str, float, float]], page_rect) -> list[tuple[str, object]]:
	"""Build crop cells from UDI heading anchors, supporting multi-row and multi-column pages."""
	if len(markers) < 2:
		return []

	# Group headings by rows using a Y tolerance for OCR drift.
	row_tolerance = 45.0
	ordered = sorted(markers, key=lambda item: (item[2], item[1]))
	rows: list[list[tuple[str, float, float]]] = []
	for marker in ordered:
		if not rows:
			rows.append([marker])
			continue
		row_mean_y = sum(item[2] for item in rows[-1]) / len(rows[-1])
		if abs(marker[2] - row_mean_y) <= row_tolerance:
			rows[-1].append(marker)
		else:
			rows.append([marker])

	row_tops = [min(item[2] for item in row) for row in rows]
	vertical_bounds = [page_rect.y0]
	for idx in range(len(row_tops) - 1):
		vertical_bounds.append((row_tops[idx] + row_tops[idx + 1]) / 2.0)
	vertical_bounds.append(page_rect.y1)

	cells: list[tuple[str, object]] = []
	for row_idx, row in enumerate(rows):
		row_sorted = sorted(row, key=lambda item: item[1])
		x_centers = [item[1] for item in row_sorted]
		horizontal_bounds = [page_rect.x0]
		for idx in range(len(x_centers) - 1):
			horizontal_bounds.append((x_centers[idx] + x_centers[idx + 1]) / 2.0)
		horizontal_bounds.append(page_rect.x1)

		y0 = vertical_bounds[row_idx]
		y1 = vertical_bounds[row_idx + 1]
		row_top = min(item[2] for item in row_sorted)
		if row_idx > 0:
			y0 = max(y0, row_top - 28.0)
		if row_idx < len(rows) - 1:
			next_row_top = min(item[2] for item in rows[row_idx + 1])
			y1 = min(y1, next_row_top - 18.0)
		for col_idx, (udi_number, _x, _y) in enumerate(row_sorted):
			x0 = horizontal_bounds[col_idx]
			x1 = horizontal_bounds[col_idx + 1]
			inset_x = min(16.0, max(4.0, (x1 - x0) * 0.03))
			inset_y = min(12.0, max(3.0, (y1 - y0) * 0.02))
			x0 += inset_x
			x1 -= inset_x
			y0c = y0 + inset_y
			y1c = y1 - inset_y
			rect = fitz.Rect(x0, y0c, x1, y1c)
			if rect.width < 120 or rect.height < 80:
				continue
			cells.append((udi_number, rect))

	return cells


def split_udi_pdf_halves_if_needed(filename: str, file_bytes: bytes) -> list[tuple[str, bytes]]:
	"""
	Best-effort splitter for synoptic UDI PDFs where a page contains multiple UDI sections.
	It detects UDI headings and crops one vertical section per detected UDI.
	If split detection fails, returns the original file unchanged.
	"""
	if not PYMUPDF_AVAILABLE:
		return [(filename, file_bytes)]

	src = None
	try:
		src = fitz.open(stream=file_bytes, filetype="pdf")
		if src.page_count != 1:
			return [(filename, file_bytes)]

		page = src[0]
		rect = page.rect

		full_text = page.get_text("text") or ""
		unique_udis = _all_udi_numbers(full_text)
		if len(unique_udis) < 2:
			unique_udis = _udi_numbers_from_filename(filename)
		if len(unique_udis) < 2:
			return [(filename, file_bytes)]

		markers = _detect_udi_markers_on_page(page)
		if len(markers) < 2:
			# Fallback to 2-section split when only distinct UDI ids are known.
			mid_y = (rect.y0 + rect.y1) / 2.0
			markers = [
				(unique_udis[0], (rect.x0 + rect.x1) / 2.0, rect.y0),
				(unique_udis[1], (rect.x0 + rect.x1) / 2.0, mid_y),
			]

		markers = markers[: max(2, len(unique_udis))]
		if len(markers) < 2:
			return [(filename, file_bytes)]

		anchor_cells = _build_udi_anchor_cells(markers, rect)

		stem = re.sub(r"\.[Pp][Dd][Ff]$", "", filename)
		parts: list[tuple[str, bytes]] = []
		if anchor_cells:
			for idx, (udi_number, clip_rect) in enumerate(anchor_cells, start=1):
				dst = fitz.open()
				new_page = dst.new_page(width=clip_rect.width, height=clip_rect.height)
				new_page.show_pdf_page(new_page.rect, src, 0, clip=clip_rect)
				part_name = f"{stem}__UDI_{udi_number}_s{idx}.pdf"
				parts.append((part_name, dst.tobytes()))
				dst.close()
		else:
			# Legacy fallback: vertical-only sections when heading grid cannot be inferred.
			y_positions = [y for _, _, y in markers]
			bounds = [rect.y0]
			for i in range(len(y_positions) - 1):
				bounds.append((y_positions[i] + y_positions[i + 1]) / 2.0)
			bounds.append(rect.y1)
			for idx, (udi_number, _x, _y) in enumerate(markers, start=1):
				y0 = bounds[idx - 1]
				y1 = bounds[idx]
				if y1 - y0 < 40:
					continue
				clip_rect = fitz.Rect(rect.x0, y0, rect.x1, y1)
				dst = fitz.open()
				new_page = dst.new_page(width=rect.width, height=clip_rect.height)
				new_page.show_pdf_page(new_page.rect, src, 0, clip=clip_rect)
				part_name = f"{stem}__UDI_{udi_number}_s{idx}.pdf"
				parts.append((part_name, dst.tobytes()))
				dst.close()

		return parts if len(parts) >= 2 else [(filename, file_bytes)]
	except Exception:
		return [(filename, file_bytes)]
	finally:
		try:
			src.close()
		except Exception:
			pass


def _forced_udi_number_from_filename(filename: str) -> str | None:
	m = re.search(r"__UDI_([0-9]{1,3})_", filename or "", re.IGNORECASE)
	return m.group(1) if m else None


def _extract_forced_udi_label(text: str, forced_number: str) -> str | None:
	if not text:
		return None
	pattern = rf"UDI\s*{re.escape(forced_number)}\s*[-:]?\s*([^\n\r]{0,120})"
	m = re.search(pattern, text, re.IGNORECASE)
	if not m:
		return None
	tail = str(m.group(1) or "")
	tail = re.split(r"\bUDI\s*[0-9]{1,3}\b", tail, maxsplit=1, flags=re.IGNORECASE)[0]
	tail = re.sub(r"\s+", " ", tail).strip(" -")
	if tail:
		return f"UDI {forced_number} - {tail}"
	return f"UDI {forced_number}"


def _extract_udi_name_tail(label: str) -> str:
	text = str(label or "").strip()
	if not text:
		return ""
	m = re.search(r"\bUDI\s*[0-9]{1,3}\s*[-:]\s*(.+)$", text, re.IGNORECASE)
	if m:
		return normalize_sort_key(m.group(1))
	return ""


def _apply_forced_udi_context(result_json: dict, filename: str) -> dict:
	forced = _forced_udi_number_from_filename(filename)
	if not forced:
		return result_json

	out = dict(result_json or {})
	forced_nom = None
	has_forced_site_match = False
	has_forced_reservoir_match = False
	selected_site_volume = None
	original_sites = out.get("sites_udi") or []
	sites = out.get("sites_udi") or []
	if isinstance(sites, list):
		filtered_sites = []
		for site in sites:
			if not isinstance(site, dict):
				continue
			label = str(site.get("site") or "")
			if forced_nom is None:
				forced_nom = _extract_forced_udi_label(label, forced)
			if re.search(rf"\bUDI\s*{re.escape(forced)}\b", label, re.IGNORECASE):
				filtered_sites.append(site)
		if filtered_sites:
			has_forced_site_match = True
			selected_site = filtered_sites[0]
			out["sites_udi"] = filtered_sites
			selected_name = str(selected_site.get("site") or "").strip()
			out["nom_udi"] = forced_nom or _extract_forced_udi_label(selected_name, forced) or selected_name or out.get("nom_udi")
			if isinstance(selected_site.get("volume_reservoir_m3"), (int, float)):
				selected_site_volume = float(selected_site.get("volume_reservoir_m3"))
			signed = selected_site.get("denivele_source_reservoir_m")
			reservoirs_all = out.get("reservoirs_udi") or []
			if isinstance(reservoirs_all, list):
				res_signed_candidates = []
				for res in reservoirs_all:
					if not isinstance(res, dict):
						continue
					res_site = str(res.get("site_udi") or "")
					if not re.search(rf"\bUDI\s*{re.escape(forced)}\b", res_site, re.IGNORECASE):
						continue
					res_signed = res.get("denivele_source_reservoir_m")
					if isinstance(res_signed, (int, float)):
						res_signed_candidates.append(float(res_signed))
				if res_signed_candidates:
					best_res_signed = max(res_signed_candidates, key=lambda x: abs(x))
					if (not isinstance(signed, (int, float))) or float(signed) == 0.0:
						signed = best_res_signed
			if isinstance(signed, (int, float)):
				out["denivele_source_reservoir_m"] = float(signed)
				out["denivele_estime_m"] = abs(float(signed))
				out["hauteur_chute_estimee_m"] = float(signed)
				out["potentiel_hydraulique"] = bool(float(signed) > 0)
			if isinstance(selected_site.get("volume_reservoir_m3"), (int, float)):
				out["volume_reservoir_m3"] = float(selected_site.get("volume_reservoir_m3"))

	reservoirs = out.get("reservoirs_udi") or []
	if isinstance(reservoirs, list):
		filtered_reservoirs = []
		for res in reservoirs:
			if not isinstance(res, dict):
				continue
			res_site = str(res.get("site_udi") or "")
			if forced_nom is None:
				forced_nom = _extract_forced_udi_label(res_site, forced)
			if re.search(rf"\bUDI\s*{re.escape(forced)}\b", res_site, re.IGNORECASE):
				filtered_reservoirs.append(res)
		if filtered_reservoirs:
			has_forced_reservoir_match = True
			out["reservoirs_udi"] = filtered_reservoirs
			out["description_reservoirs"] = _filter_description_reservoirs_for_site(
				out.get("description_reservoirs") or [],
				str(out.get("nom_udi") or f"UDI {forced}"),
				filtered_reservoirs,
			)
			vols = [r.get("volume_reservoir_m3") for r in filtered_reservoirs if isinstance(r.get("volume_reservoir_m3"), (int, float))]
			if vols:
				float_vols = [float(v) for v in vols]
				if isinstance(selected_site_volume, (int, float)):
					out["volume_reservoir_m3"] = min(float_vols, key=lambda v: abs(v - float(selected_site_volume)))
				else:
					out["volume_reservoir_m3"] = max(float_vols)

	if (not has_forced_site_match) and (not has_forced_reservoir_match):
		nom = str(out.get("nom_udi") or "")
		many_udi_in_name = len(re.findall(r"\bUDI\s*[0-9]{1,3}\b", nom, flags=re.IGNORECASE)) >= 2
		many_sites = isinstance(original_sites, list) and len(original_sites) >= 2
		if many_udi_in_name or many_sites:
			# Avoid assigning a wrong volume when forced UDI filtering found no explicit match.
			out["volume_reservoir_m3"] = None

	if forced_nom is None:
		forced_nom = _extract_forced_udi_label(str(out.get("nom_udi") or ""), forced)
	if forced_nom is None:
		forced_nom = f"UDI {forced}"
	out["nom_udi"] = forced_nom

	# Fallback narrowing for segmented files when OCR labels omit explicit "UDI <n>".
	target_tail = _extract_udi_name_tail(forced_nom)
	target_tokens = [tok for tok in re.split(r"[^a-z0-9]+", target_tail) if len(tok) >= 4]
	if target_tokens:
		sites_now = out.get("sites_udi") or []
		if isinstance(sites_now, list) and len(sites_now) > 1:
			narrowed_sites = []
			for site in sites_now:
				if not isinstance(site, dict):
					continue
				site_label_norm = normalize_sort_key(str(site.get("site") or ""))
				if any(tok in site_label_norm for tok in target_tokens):
					narrowed_sites.append(site)
			if narrowed_sites:
				out["sites_udi"] = narrowed_sites

	res_now = out.get("reservoirs_udi") or []
	if isinstance(res_now, list) and res_now:
		site_keys = {
			_normalize_udi_identifier(str(site.get("site") or ""))
			for site in (out.get("sites_udi") or [])
			if isinstance(site, dict) and str(site.get("site") or "").strip()
		}
		narrowed_res = []
		for res in res_now:
			if not isinstance(res, dict):
				continue
			res_site_label = str(res.get("site_udi") or "")
			res_site_key = _normalize_udi_identifier(res_site_label)
			res_norm = normalize_sort_key(f"{res.get('site_udi') or ''} {res.get('reservoir') or ''}")
			if site_keys and res_site_key in site_keys:
				narrowed_res.append(res)
				continue
			if target_tokens and any(tok in res_norm for tok in target_tokens):
				narrowed_res.append(res)
		if narrowed_res:
			out["reservoirs_udi"] = narrowed_res

	if isinstance(out.get("reservoirs_udi"), list):
		out["description_reservoirs"] = _filter_description_reservoirs_for_site(
			out.get("description_reservoirs") or [],
			str(out.get("nom_udi") or forced_nom),
			out.get("reservoirs_udi") or [],
		)

	target_tail = _extract_udi_name_tail(str(out.get("nom_udi") or forced_nom))
	target_tokens = [tok for tok in re.split(r"[^a-z0-9]+", target_tail) if len(tok) >= 4]
	points = out.get("points_pression_reduction") or []
	if target_tokens and isinstance(points, list) and points:
		narrowed_points = []
		for item in points:
			item_norm = normalize_sort_key(str(item))
			if any(tok in item_norm for tok in target_tokens):
				narrowed_points.append(item)
		if narrowed_points:
			out["points_pression_reduction"] = narrowed_points

	return out


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
	st.set_page_config(page_title="Energy AI Tool", page_icon="⚡", layout="wide")
	inject_brand_theme()
	col_logo, col_title = st.columns([1, 6])
	with col_logo:
		if LOGO_PATH.exists():
			st.image(str(LOGO_PATH), width=90)
	with col_title:
		st.markdown(
			"<h1 style='margin-bottom:0.1rem;'>⚡ Energy AI Tool</h1>"
			"<p style='color:#8bb8d4; font-size:0.9rem; letter-spacing:0.06em; text-transform:uppercase; margin-top:0;'>"
			"Analyse intelligente · Fiches STEU / UDI · Potentiel ENR</p>",
			unsafe_allow_html=True,
		)
	st.markdown(
		"""<div class="larzac-hero">
		<span style="font-size:0.95rem; color:#cce8ff; line-height:1.7;">
		🔍 &nbsp;<b style="color:#00d4ff;">Extraction IA</b> de documents techniques STEU/UDI &nbsp;·&nbsp;
		☀️ &nbsp;Potentiel <b style="color:#00ff9d;">photovoltaïque</b> &nbsp;·&nbsp;
		💧 &nbsp;Potentiel <b style="color:#00d4ff;">micro-hydro</b> &nbsp;·&nbsp;
		📊 &nbsp;Comparaison multi-sites &amp; priorisation ENR
		</span>
		</div>""",
		unsafe_allow_html=True,
	)
	with st.expander("⚡ Guide rapide (30 secondes)", expanded=False):
		st.markdown(
			"1. 📂 Importe un ou plusieurs PDF techniques.\n"
			"2. 🚀 Clique sur **Analyser les PDF** pour lancer l'extraction IA.\n"
			"3. 📊 Consulte les onglets **Comparaison** et **Sites**, puis exporte le **rapport PDF**."
		)


def render_priority_badge(score: float, channel: str) -> None:
	icon = "☀️" if channel == "pv" else "💧"
	label = "PV" if channel == "pv" else "Hydro"
	if score >= 4:
		color, level_label, glow = "#00ff9d", "ÉLEVÉE", "0 0 12px rgba(0,255,157,0.7)"
	elif score >= 2:
		color, level_label, glow = "#ffd700", "MOYENNE", "0 0 12px rgba(255,215,0,0.6)"
	else:
		color, level_label, glow = "#4a6d88", "FAIBLE", "none"
	st.markdown(
		f"""<div style="
			display:inline-flex; align-items:center; gap:0.5rem;
			padding:0.4rem 0.85rem; border-radius:8px;
			border:1px solid {color}; background:rgba(0,0,0,0.3);
			box-shadow:{glow}; font-size:0.82rem; font-weight:700;
			color:{color}; letter-spacing:0.06em; text-transform:uppercase;">
			{icon} &nbsp;Priorité {label} : {level_label} ({int(score)})
		</div>""",
		unsafe_allow_html=True,
	)


def render_end_of_run_summary(run_record: dict) -> None:
	success = run_record.get("success_count", 0)
	total = run_record.get("total_files", 0)
	errors = run_record.get("error_count", 0)
	st.markdown(
		f"""<div style="
			padding:1.2rem 1.5rem; border-radius:14px; margin:1rem 0;
			background:linear-gradient(135deg,rgba(0,212,255,0.10) 0%,rgba(0,255,157,0.07) 100%);
			border:1px solid rgba(0,255,157,0.4);
			box-shadow:0 0 24px rgba(0,255,157,0.15);
		">
		<div style="font-size:1.1rem; font-weight:700; color:#00ff9d; letter-spacing:0.04em; margin-bottom:0.75rem;">
			✅ &nbsp;Analyse terminée
		</div>
		<div style="display:flex; gap:2rem; flex-wrap:wrap;">
			<div style="text-align:center;">
				<div style="font-size:2rem; font-weight:800; color:#00d4ff;">{success}</div>
				<div style="font-size:0.72rem; text-transform:uppercase; letter-spacing:0.06em; color:#8bb8d4;">Sites traités</div>
			</div>
			<div style="text-align:center;">
				<div style="font-size:2rem; font-weight:800; color:#00d4ff;">{total}</div>
				<div style="font-size:0.72rem; text-transform:uppercase; letter-spacing:0.06em; color:#8bb8d4;">Fichiers total</div>
			</div>
			<div style="text-align:center;">
				<div style="font-size:2rem; font-weight:800; color:{'#ff4d6d' if errors else '#00ff9d'};">{errors}</div>
				<div style="font-size:0.72rem; text-transform:uppercase; letter-spacing:0.06em; color:#8bb8d4;">Erreurs</div>
			</div>
		</div>
		<div style="margin-top:0.75rem; font-size:0.8rem; color:#4a6d88;">
			→ Onglets disponibles : <b style="color:#00d4ff;">Comparaison</b> · <b style="color:#00d4ff;">Sites</b> · <b style="color:#00d4ff;">Rapport PDF</b>
		</div>
		</div>""",
		unsafe_allow_html=True,
	)


def compute_hydro_score(result_json: dict) -> int:
	score = 0
	head = result_json.get("hauteur_chute_estimee_m")
	denivele_sr = result_json.get("denivele_source_reservoir_m")
	no_head_available = (
		(isinstance(denivele_sr, (int, float)) and denivele_sr <= 0)
		or (head is None)
		or (isinstance(head, (int, float)) and head <= 0)
	)
	if no_head_available:
		# No exploitable head means hydro priority must stay very low.
		return 0

	if result_json.get("potentiel_hydraulique") is True:
		score += 2
	flow = result_json.get("debit_m3_j")
	if isinstance(flow, (int, float)) and flow >= 50:
		score += 1
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
		return "Non documentée"
	if surface_m2 >= 1000:
		return "Très élevée"
	if surface_m2 >= 500:
		return "Élevée"
	if surface_m2 >= 200:
		return "Moyenne"
	if surface_m2 >= 80:
		return "Faible"
	return "Très faible"


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


def _udi_sort_key(site_label: str) -> tuple[int, str]:
	label = str(site_label or "")
	m = re.search(r"\bUDI\s*([0-9]{1,3})\b", label, re.IGNORECASE)
	if m:
		return int(m.group(1)), normalize_sort_key(label)
	return 10**9, normalize_sort_key(label)


def _format_udi_sites_head_details(result_json: dict) -> str:
	sites = result_json.get("sites_udi") or []
	if not isinstance(sites, list) or not sites:
		return "N/D"

	parts: list[str] = []
	for site in sites:
		if not isinstance(site, dict):
			continue
		site_name = str(site.get("site") or "Site UDI").strip()
		signed = site.get("denivele_source_reservoir_m")
		if isinstance(signed, (int, float)):
			status = "dispo" if signed > 0 else "non"
			parts.append(f"{site_name}: {signed} m ({status})")
		else:
			parts.append(f"{site_name}: N/D")

	return " | ".join(parts) if parts else "N/D"


def _dedupe_udi_reservoirs(reservoirs: list) -> list[dict]:
	if not isinstance(reservoirs, list):
		return []

	seen: set[str] = set()
	cleaned: list[dict] = []
	for res in reservoirs:
		if not isinstance(res, dict):
			continue
		site = normalize_sort_key(str(res.get("site_udi") or ""))
		name = normalize_sort_key(str(res.get("reservoir") or ""))
		alt = res.get("reservoir_altitude_ngf_m")
		key = f"{site}|{name}|{alt}"
		if key in seen:
			continue
		seen.add(key)
		cleaned.append(res)

	return cleaned


def _format_udi_reservoir_head_details(result_json: dict) -> str:
	reservoirs = _dedupe_udi_reservoirs(result_json.get("reservoirs_udi") or [])
	if not isinstance(reservoirs, list) or not reservoirs:
		return "N/D"

	parts: list[str] = []
	for res in reservoirs:
		if not isinstance(res, dict):
			continue
		name = str(res.get("reservoir") or "Réservoir").strip()
		signed = res.get("denivele_source_reservoir_m")
		head = res.get("hauteur_chute_disponible_m")
		if isinstance(signed, (int, float)):
			status = "dispo" if signed > 0 else "non"
			head_label = f", chute {head} m" if isinstance(head, (int, float)) else ""
			parts.append(f"{name}: Δ {signed} m{head_label} ({status})")
		else:
			parts.append(f"{name}: N/D")

	return " | ".join(parts) if parts else "N/D"


def _build_udi_hydro_site_rows(result_json: dict) -> list[dict[str, object]]:
	sites = result_json.get("sites_udi") or []
	reservoirs = _dedupe_udi_reservoirs(result_json.get("reservoirs_udi") or [])
	rows: list[dict[str, object]] = []

	for site in sites:
		if not isinstance(site, dict):
			continue
		site_name = str(site.get("site") or "Site UDI").strip() or "Site UDI"
		site_signed = site.get("denivele_source_reservoir_m")
		site_status = "✓ Oui" if isinstance(site_signed, (int, float)) and site_signed > 0 else "✖ Non" if isinstance(site_signed, (int, float)) else "N/D"
		res_count = 0
		site_key = _normalize_udi_identifier(site_name)
		for res in reservoirs:
			if not isinstance(res, dict):
				continue
			res_site = str(res.get("site_udi") or "").strip()
			if res_site and _normalize_udi_identifier(res_site) == site_key:
				res_count += 1

		rows.append(
			{
				"Site UDI": site_name,
				"Source NGF (m)": site.get("source_altitude_ngf_m"),
				"Réservoir NGF (m)": site.get("reservoir_altitude_ngf_m"),
				"Dénivelé S->R (m)": site_signed,
				"Chute dispo": site_status,
				"Nb réservoirs": res_count if res_count > 0 else "N/D",
			}
		)

	return rows


def _build_udi_hydro_reservoir_rows(result_json: dict) -> list[dict[str, object]]:
	reservoirs = _dedupe_udi_reservoirs(result_json.get("reservoirs_udi") or [])
	reducers_present = result_json.get("presence_reducteurs_pression")
	reducers_count = result_json.get("nombre_reducteurs_pression")
	if reducers_present is True:
		reducers_label = f"Oui ({reducers_count})" if isinstance(reducers_count, (int, float)) else "Oui"
	elif reducers_present is False:
		reducers_label = "Non"
	else:
		reducers_label = "N/D"

	rows: list[dict[str, object]] = []
	for res in reservoirs:
		if not isinstance(res, dict):
			continue
		signed = res.get("denivele_source_reservoir_m")
		head = res.get("hauteur_chute_disponible_m")
		status = "✓ Oui" if isinstance(signed, (int, float)) and signed > 0 else "✖ Non" if isinstance(signed, (int, float)) else "N/D"
		rows.append(
			{
				"Site UDI": res.get("site_udi"),
				"Réservoir": res.get("reservoir"),
				"Source NGF (m)": res.get("source_altitude_ngf_m"),
				"Réservoir NGF (m)": res.get("reservoir_altitude_ngf_m"),
				"Dénivelé S->R (m)": signed,
				"Hauteur chute dispo (m)": head,
				"Chute dispo": status,
				"Réducteurs pression": reducers_label,
				"Volume réservoir (m3)": res.get("volume_reservoir_m3"),
			}
		)

	return rows


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
				"Surface PV (m²)": pv_surface,
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
		if is_udi_infrastructure_attachment_entry(entry):
			continue
		result_json = entry.get("result_json", {})
		hydro_status = result_json.get("potentiel_hydraulique")
		points = result_json.get("points_pression_reduction") or []
		flow_m3_j = result_json.get("debit_m3_j")
		head_m = result_json.get("hauteur_chute_estimee_m")
		denivele_sr = result_json.get("denivele_source_reservoir_m")
		reducers_count = result_json.get("nombre_reducteurs_pression")
		reservoirs_count = len(result_json.get("reservoirs_udi") or [])
		completeness_pct, _ = compute_data_completeness(result_json, "udi")

		if completeness_pct < min_completeness_pct:
			continue
		if isinstance(flow_m3_j, (int, float)) and flow_m3_j < min_flow_m3j:
			continue
		if isinstance(head_m, (int, float)) and head_m > 0 and head_m < min_head_m:
			continue

		weighted_priority = round(
			(weight_hydro * compute_hydro_score(result_json))
			+ (weight_flow * _flow_score_from_m3j(flow_m3_j))
			+ (weight_head * _head_score_from_m(head_m))
			+ (weight_points * min(len(points), 3))
			+ (weight_completeness * (completeness_pct / 25)),
			2,
		)
		if not isinstance(head_m, (int, float)) or head_m <= 0:
			# Penalize UDI sites without available head in ranking.
			weighted_priority = round(weighted_priority * 0.25, 2)
		rows.append(
			{
				"Site réservoir": entry.get("site_name", "Site"),
				"Localisation": result_json.get("localisation"),
				"Sites UDI (Δ S->R)": _format_udi_sites_head_details(result_json),
				"Réservoirs (détail chute)": _format_udi_reservoir_head_details(result_json),
				"Complétude (%)": completeness_pct,
				"Débit (m³/j)": flow_m3_j,
				"Volume réservoir (m³)": result_json.get("volume_reservoir_m3"),
				"Hauteur chute (m)": head_m,
				"Chute dispo": "✖ Non"
				if (isinstance(denivele_sr, (int, float)) and denivele_sr <= 0) or (isinstance(head_m, (int, float)) and head_m <= 0)
				else "✓ Oui"
				if isinstance(head_m, (int, float)) and head_m > 0
				else "N/D",
				"Réducteurs pression": reducers_count if isinstance(reducers_count, (int, float)) else "N/D",
				"Réservoirs détectés": reservoirs_count if reservoirs_count > 0 else "N/D",
				"Points pression": len(points),
				"Potentiel hydro": "Oui" if hydro_status is True else "Non" if hydro_status is False else "N/D",
				"Score Hydro": compute_hydro_score(result_json),
				"Priorité Hydro": weighted_priority,
			}
		)
	return sorted(
		rows,
		key=lambda row: (
			_udi_sort_key(row.get("Site réservoir", "")),
			-float(row.get("Priorité Hydro", 0)),
		),
	)


def _format_number(value) -> str:
	if isinstance(value, (int, float)):
		if float(value).is_integer():
			return str(int(value))
		return f"{float(value):.2f}"
	return "N/D"


def build_unified_comparison_rows(ranked_steu: list[dict], ranked_udi: list[dict]) -> list[dict]:
	rows: list[dict] = []

	for idx, row in enumerate(ranked_steu, start=1):
		rows.append(
			{
				"Type": "STEU",
				"Rang": idx,
				"Site": row.get("Station", "Site"),
				"Localisation": row.get("Commune") or "N/D",
				"Réducteurs pression": "N/D",
				"Complétude (%)": row.get("Complétude (%)", "N/D"),
				"Indicateur principal": f"Surface PV : {_format_number(row.get('Surface PV (m²)'))} m²",
				"Score principal": row.get("Score PV", 0),
				"Priorité": row.get("Priorité PV", 0),
			}
		)

	for idx, row in enumerate(ranked_udi, start=1):
		reducers_value = row.get("Réducteurs pression")
		if isinstance(reducers_value, (int, float)):
			reducers_label = f"Oui ({int(reducers_value)})" if int(reducers_value) > 0 else "Oui"
		elif isinstance(reducers_value, str) and reducers_value.strip().lower() in {"non", "n/d"}:
			reducers_label = reducers_value
		else:
			reducers_label = "N/D"

		rows.append(
			{
				"Type": "UDI",
				"Rang": idx,
				"Site": row.get("Site réservoir", "Site"),
				"Localisation": row.get("Localisation") or "N/D",
				"Réducteurs pression": reducers_label,
				"Complétude (%)": row.get("Complétude (%)", "N/D"),
				"Indicateur principal": (
					f"Débit : {_format_number(row.get('Débit (m³/j)'))} m³/j | "
					f"Chute : {_format_number(row.get('Hauteur chute (m)'))} m"
				),
				"Score principal": row.get("Score Hydro", 0),
				"Priorité": row.get("Priorité Hydro", 0),
			}
		)

	return sorted(rows, key=lambda item: float(item.get("Priorité", 0)), reverse=True)


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

	unified_rows = build_unified_comparison_rows(ranked_steu, ranked_udi)
	if unified_rows:
		st.markdown("### Tableau comparatif unifié")
		st.dataframe(unified_rows, use_container_width=True, hide_index=True)

	if ranked_steu:
		st.success(
			f"STEU prioritaire pour étude PV : {ranked_steu[0]['Station']} (score {ranked_steu[0]['Priorité PV']})."
		)

	if ranked_udi:
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
			min_surface_m2 = st.slider("STEU - Surface PV minimale (m²)", min_value=0, max_value=2000, value=0, step=50)
			min_flow_m3j = st.slider("UDI - Débit minimal (m³/j)", min_value=0, max_value=500, value=0, step=10)
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
	lines.append(f"Modèle IA : {run_data.get('model', '-')}")
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
				f"{idx}. {row['station']} ({row['commune']}) - Surface PV : {surface_label}, "
				f"classe : {row['classe']}, score PV : {row['score']}"
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
			debit_label = f"{row['debit']} m³/j" if isinstance(row["debit"], (int, float)) else "N/D"
			chute_label = f"{row['chute']} m" if isinstance(row["chute"], (int, float)) else "N/D"
			lines.append(
				f"{idx}. {row['site']} - Débit : {debit_label}, Chute : {chute_label}, "
				f"Points pression : {row['points']}, Hydro : {hydro_label}, score Hydro : {row['score']}"
			)
		lines.append("")
		lines.append(f"Recommandation UDI Hydro : {ranked_udi[0]['site']}")
		lines.append("")

	if run_data.get("error_count", 0):
		lines.append("## Fichiers en erreur")
		for err in run_data.get("errors", []):
			lines.append(f"- {err.get('filename', 'fichier')} : {err.get('error', 'Erreur inconnue')}")

	return "\n".join(lines).strip() + "\n"


def render_site_detail(entry: dict, show_debug: bool, all_results: list[dict] | None = None) -> None:
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
	pv_priority = compute_steu_priority_score(result_json) if document_type == "steu" else compute_pv_score(result_json)
	hydro_priority = compute_udi_priority_score(result_json)

	st.markdown(
		f"""<div style="
			padding:1rem 1.4rem; border-radius:14px; margin-bottom:0.8rem;
			background:linear-gradient(135deg,rgba(0,212,255,0.08) 0%,rgba(0,255,157,0.05) 100%);
			border:1px solid rgba(0,212,255,0.25);
		">
		<div style="font-size:1.15rem; font-weight:700; color:#e8f4ff; margin-bottom:0.3rem;">{site_name}</div>
		<div style="font-size:0.78rem; color:#4a6d88; font-family:'JetBrains Mono',monospace;">
			📄 {filename} &nbsp;|&nbsp; 
			<span style="color:{'#00d4ff' if document_type=='udi' else '#00ff9d'}; font-weight:600; text-transform:uppercase;">
			{document_type}
			</span>
		</div>
		</div>""",
		unsafe_allow_html=True,
	)
	col1, col2, col3 = st.columns(3)
	col1.metric("Référence", main_name)
	col2.metric("Localisation", localisation)
	col3.metric(third_title, third_label)
	st.markdown(
		f"<span style='color:#4a6d88; font-size:0.8rem;'>📊 Complétude extraction : "
		f"<b style='color:#{'00ff9d' if completeness_pct>=80 else 'ffd700' if completeness_pct>=50 else 'ff6b6b'};'>"
		f"{completeness_pct}%</b> &nbsp;({completeness_label})</span>",
		unsafe_allow_html=True,
	)
	colp, colh = st.columns(2)
	with colp:
		render_priority_badge(float(pv_priority), "pv")
	with colh:
		render_priority_badge(float(hydro_priority), "hydro")

	tab_desc, tab_hydro, tab_infra, tab_pv, tab_sim, tab_loc, tab_json, tab_debug = st.tabs(
		["Description", "Hydro", "Infrastructure site", "PV", "Simulation", "Localisation", "JSON", "Debug"]
	)

	with tab_desc:
		if document_type == "udi":
			reducers_present = result_json.get("presence_reducteurs_pression")
			reducers_count = result_json.get("nombre_reducteurs_pression")
			if reducers_present is True:
				label = f"Réducteurs de pression détectés ({reducers_count})" if isinstance(reducers_count, (int, float)) else "Réducteurs de pression détectés"
				st.success(label)
			elif reducers_present is False:
				st.info("Aucun réducteur de pression indiqué")

		if description:
			with st.container(border=True):
				st.markdown(format_description_text(description))
		else:
			st.info("Aucune description détaillée n'a été renvoyée par le modèle.")

	with tab_hydro:
		with st.container(border=True):
			for line in build_hydro_summary(result_json, document_type):
				if line == "NO_HEAD_WARNING":
					st.markdown("<span style='color:#c62828; font-weight:700;'>✖ pas de hauteur de chute</span>", unsafe_allow_html=True)
					continue
				if line.startswith("NO_HEAD_SITE:"):
					site_label = line.split(":", 1)[1]
					st.markdown(
						f"<span style='color:#c62828; font-weight:700;'>✖ {site_label}: pas de hauteur de chute</span>",
						unsafe_allow_html=True,
					)
					continue
				st.write(f"- {line}")
			if document_type == "udi":
				site_rows = _build_udi_hydro_site_rows(result_json)
				if site_rows:
					st.markdown("**Tableau récapitulatif - Sites UDI**")
					st.dataframe(site_rows, use_container_width=True, hide_index=True)

				reservoir_rows = _build_udi_hydro_reservoir_rows(result_json)
				if reservoir_rows:
					st.markdown("**Tableau récapitulatif - Réservoirs par site**")
					st.dataframe(reservoir_rows, use_container_width=True, hide_index=True)

	with tab_pv:
		with st.container(border=True):
			for line in build_pv_summary(result_json):
				st.write(f"- {line}")

	with tab_sim:
		with st.container(border=True):
			render_simulation_tab(
				result_json=result_json,
				document_type=document_type,
				key_prefix=f"{document_type}_{normalize_sort_key(site_name)}",
			)

	with tab_infra:
		with st.container(border=True):
			render_infrastructure_site_tab(entry, all_results)

	with tab_loc:
		with st.container(border=True):
			render_location_tab(site_name=site_name, result_json=result_json)

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
	unified_rows = build_unified_comparison_rows(ranked_steu, ranked_udi)

	story = []
	meta_block = (
		"Rapport complet de comparaison multi-sites"
		f"<br/><font size='9'>Date du run : {run_data.get('timestamp', '-')}</font>"
		f"<br/><font size='9'>Modèle IA : {run_data.get('model', '-')}</font>"
		f"<br/><font size='9'>Fichiers analyses : {run_data.get('success_count', 0)}/{run_data.get('total_files', 0)} | Erreurs : {run_data.get('error_count', 0)}</font>"
	)
	if LOGO_PATH.exists():
		logo = RLImage(str(LOGO_PATH), width=56, height=56)
		header_table = Table([[logo, Paragraph(meta_block, title_style)]], colWidths=[64, 450])
		header_table.setStyle(
			TableStyle(
				[
					("VALIGN", (0, 0), (-1, -1), "TOP"),
					("LEFTPADDING", (0, 0), (-1, -1), 0),
					("RIGHTPADDING", (0, 0), (-1, -1), 0),
					("TOPPADDING", (0, 0), (-1, -1), 0),
					("BOTTOMPADDING", (0, 0), (-1, -1), 0),
				]
			)
		)
		story.extend([header_table, Spacer(1, 10)])
	else:
		story.extend([
			Paragraph("Rapport complet de comparaison multi-sites", title_style),
			Spacer(1, 8),
			Paragraph(f"Date du run : {run_data.get('timestamp', '-')}", body_style),
			Paragraph(f"Modèle IA : {run_data.get('model', '-')}", body_style),
			Paragraph(
				f"Fichiers analyses : {run_data.get('success_count', 0)}/{run_data.get('total_files', 0)} | Erreurs : {run_data.get('error_count', 0)}",
				body_style,
			),
			Spacer(1, 10),
		])

	if unified_rows:
		story.append(Paragraph("Comparatif multi-sites (tableau unifié)", subtitle_style))
		header = ["Type", "Rang", "Site", "Localisation", "Complétude", "Indicateur", "Score", "Priorité"]
		table_data = [header]
		for row in unified_rows:
			table_data.append(
				[
					Paragraph(str(row.get("Type", "N/D")), body_style),
					Paragraph(str(row.get("Rang", "N/D")), body_style),
					Paragraph(str(row.get("Site", "N/D")), body_style),
					Paragraph(str(row.get("Localisation", "N/D")), body_style),
					Paragraph(str(row.get("Complétude (%)", "N/D")), body_style),
					Paragraph(str(row.get("Indicateur principal", "N/D")), body_style),
					Paragraph(str(row.get("Score principal", "N/D")), body_style),
					Paragraph(str(row.get("Priorité", "N/D")), body_style),
				]
			)

		table = Table(
			table_data,
			repeatRows=1,
			colWidths=[38, 28, 95, 88, 55, 138, 44, 44],
		)
		table.setStyle(
			TableStyle(
				[
					("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e7eef5")),
					("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#0f3b57")),
					("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
					("VALIGN", (0, 0), (-1, -1), "TOP"),
					("FONTSIZE", (0, 0), (-1, -1), 7.4),
				]
			)
		)
		story.extend([table, Spacer(1, 10)])

	story.append(Paragraph("Analyse détaillée par site", subtitle_style))
	for entry in results:
		if is_udi_infrastructure_attachment_entry(entry):
			continue
		result_json = entry.get("result_json", {})
		site_name = entry.get("site_name", "Site")
		doc_type = entry.get("document_type", "-").upper()
		description = entry.get("description", "") or "Description non disponible."
		story.append(Paragraph(f"<b>{site_name}</b> ({doc_type})", body_style))
		completeness_pct, _ = compute_data_completeness(result_json, entry.get("document_type", "steu"))
		story.append(Paragraph(f"- Complétude : {completeness_pct}%", body_style))
		story.append(Paragraph(f"- Débit (m³/j) : {result_json.get('debit_m3_j', 'N/D')}", body_style))
		story.append(Paragraph(f"- Surface PV (m²) : {result_json.get('surface_potentielle_solaire_m2', 'N/D')}", body_style))
		story.append(Paragraph(f"- Potentiel hydro : {result_json.get('potentiel_hydraulique', 'N/D')}", body_style))
		story.append(Paragraph(f"- Description : {description[:900]}", body_style))
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
		st.markdown(
			"<div style='font-size:1rem; font-weight:700; color:#00d4ff; "
			"letter-spacing:0.06em; text-transform:uppercase; margin-bottom:0.5rem;'>"
			"⚙️ &nbsp;Configuration</div>",
			unsafe_allow_html=True,
		)
		selected_model = st.selectbox("🤖 Modèle IA", options=ALLOWED_MODELS, index=0)
		api_url = st.text_input("🔗 URL API", value=API_URL_DEFAULT)
		show_debug = st.toggle("🔍 Afficher debug extraction", value=True)
		st.markdown("<hr style='border-color:rgba(0,212,255,0.15); margin:0.75rem 0;'>", unsafe_allow_html=True)
		if st.button("🗑 Vider l'historique", use_container_width=True):
			st.session_state.analysis_history = []
			st.session_state.selected_history_run_id = None
			st.session_state.last_completed_run_id = None
			RUN_HISTORY_STORE.clear()
			if RUNS_DIR.exists():
				for run_file in RUNS_DIR.glob("run_*.json"):
					try:
						run_file.unlink()
					except OSError:
						pass
			st.success("Historique vidé")
		if st.button("🧹 Vider le cache d'analyse", use_container_width=True):
			st.session_state.analysis_cache = {}
			st.session_state.geocode_cache = {}
			st.success("Cache d'analyse vidé")

	uploaded_files = st.file_uploader(
		"📂 Dépose un ou plusieurs PDF techniques (STEU / UDI)",
		type=["pdf"],
		accept_multiple_files=True,
	)

	with st.expander("📋 Champs extraits par l'IA", expanded=False):
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

	if st.button(
		"⚡ ANALYSER LES PDF",
		type="primary",
		disabled=not uploaded_files,
		use_container_width=True,
	):
		if not uploaded_files:
			st.warning("Ajoute au moins un PDF avant l'analyse.")
			return

		if len(uploaded_files) > MAX_FILES_PER_ANALYSIS:
			st.error(
				f"Nombre maximal de fichiers par analyse : {MAX_FILES_PER_ANALYSIS}. "
				"Reduis le lot pour eviter les erreurs de timeout."
			)
			return

		analysis_jobs: list[tuple[str, bytes]] = []
		for uploaded_file in uploaded_files:
			original_bytes = uploaded_file.getvalue()
			analysis_jobs.extend(split_udi_pdf_halves_if_needed(uploaded_file.name, original_bytes))

		success_results: list[dict] = []
		error_results: list[dict] = []
		reused_count = 0
		fresh_count = 0
		progress = st.progress(0, text="⚡ Initialisation de l'analyse batch...")
		status_box = st.empty()
		eta_box = st.empty()
		counter_box = st.empty()
		batch_started_at = time.time()
		# Reuse a single HTTP session for the full batch.
		session = requests.Session()

		total_jobs = len(analysis_jobs)
		for index, (job_filename, file_bytes) in enumerate(analysis_jobs, start=1):
			status_box.markdown(
				f"""<div style="
					padding:0.6rem 1rem; border-radius:8px; margin:0.25rem 0;
					background:rgba(0,212,255,0.07); border:1px solid rgba(0,212,255,0.3);
					color:#00d4ff; font-size:0.85rem; font-weight:600; font-family:'JetBrains Mono',monospace;
				">▶ &nbsp;{job_filename} &nbsp;<span style="color:#4a6d88;">({index}/{total_jobs})</span></div>""",
				unsafe_allow_html=True,
			)
			elapsed = max(0.001, time.time() - batch_started_at)
			avg_per_file = elapsed / max(1, index - 1) if index > 1 else 0.0
			remaining_sec = int(avg_per_file * max(0, total_jobs - (index - 1)))
			if index > 1:
				mins, secs = divmod(remaining_sec, 60)
				eta_label = f"{mins}m {secs:02d}s" if mins else f"{secs}s"
				eta_box.markdown(
					f"<span style='color:#4a6d88; font-size:0.78rem;'>⏱ Temps restant estimé : "
					f"<b style='color:#8bb8d4;'>~{eta_label}</b></span>",
					unsafe_allow_html=True,
				)
			counter_box.markdown(
				f"<span style='color:#4a6d88; font-size:0.78rem;'>📦 Cache : "
				f"<b style='color:#00ff9d;'>{reused_count}</b> &nbsp;|&nbsp; 🔄 API : "
				f"<b style='color:#00d4ff;'>{fresh_count}</b></span>",
				unsafe_allow_html=True,
			)

			cache_key = build_cache_key(file_bytes, selected_model)
			cached_entry = st.session_state.analysis_cache.get(cache_key)

			if cached_entry:
				reused_count += 1
				success_results.append(
					{
						"filename": job_filename,
						"site_name": cached_entry.get("site_name", job_filename),
						"document_type": cached_entry.get("document_type", "steu"),
						"result_json": cached_entry.get("result_json", {}),
						"description": cached_entry.get("description", ""),
						"debug": cached_entry.get("debug", {}),
					}
				)
				progress.progress(index / total_jobs, text=f"⚡ Analyse {index}/{total_jobs} (cache)")
				counter_box.markdown(
					f"<span style='color:#4a6d88; font-size:0.78rem;'>📦 Cache : "
					f"<b style='color:#00ff9d;'>{reused_count}</b> &nbsp;|&nbsp; 🔄 API : "
					f"<b style='color:#00d4ff;'>{fresh_count}</b></span>",
					unsafe_allow_html=True,
				)
				continue

			payload, api_error = request_extract_with_retry(
				session=session,
				api_url=api_url,
				filename=job_filename,
				file_bytes=file_bytes,
				model_name=selected_model,
			)
			if api_error or not payload:
				error_results.append({"filename": job_filename, "error": api_error or "Erreur API inconnue"})
				progress.progress(index / total_jobs, text=f"⚡ Analyse {index}/{total_jobs}")
				counter_box.markdown(
					f"<span style='color:#4a6d88; font-size:0.78rem;'>📦 Cache : "
					f"<b style='color:#00ff9d;'>{reused_count}</b> &nbsp;|&nbsp; 🔄 API : "
					f"<b style='color:#00d4ff;'>{fresh_count}</b></span>",
					unsafe_allow_html=True,
				)
				continue

			result_json = payload.get("result_json") or payload.get("result", {})
			document_type = payload.get("document_type", "steu")
			description_text = payload.get("description", "")
			if document_type == "udi":
				result_json = _apply_forced_udi_context(result_json, job_filename)
			site_name = get_site_name(result_json, document_type, job_filename)
			if document_type == "udi":
				description_text = _filter_udi_description_for_site(description_text, site_name)
			fresh_count += 1

			cache_payload = {
				"site_name": site_name,
				"document_type": document_type,
				"result_json": result_json,
				"description": description_text,
				"debug": payload.get("debug", {}),
			}
			st.session_state.analysis_cache[cache_key] = cache_payload

			success_results.append(
				{
					"filename": job_filename,
					"site_name": site_name,
					"document_type": document_type,
					"result_json": result_json,
					"description": cache_payload["description"],
					"debug": cache_payload["debug"],
				}
			)
			progress.progress(index / total_jobs, text=f"⚡ Analyse {index}/{total_jobs}")
			counter_box.markdown(
				f"<span style='color:#4a6d88; font-size:0.78rem;'>📦 Cache : "
				f"<b style='color:#00ff9d;'>{reused_count}</b> &nbsp;|&nbsp; 🔄 API : "
				f"<b style='color:#00d4ff;'>{fresh_count}</b></span>",
				unsafe_allow_html=True,
			)

		if reused_count:
			st.info(f"📦 Réutilisation cache : {reused_count} site(s). 🔄 Nouveaux calculs : {fresh_count} site(s).")
		status_box.markdown(
			"<div style='padding:0.5rem 1rem; border-radius:8px; background:rgba(0,255,157,0.08); "
			"border:1px solid rgba(0,255,157,0.4); color:#00ff9d; font-weight:700; font-size:0.85rem;'>"
			"✅ &nbsp;Analyse terminée</div>",
			unsafe_allow_html=True,
		)
		eta_box.empty()

		sorted_results = sorted(
			success_results,
			key=lambda item: (normalize_sort_key(item.get("site_name", "")), normalize_sort_key(item.get("filename", ""))),
		)
		sorted_results = expand_udi_results_by_sites(sorted_results)
		sorted_results = link_udi_entries_by_site(sorted_results)

		run_record = {
			"run_id": uuid.uuid4().hex,
			"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
			"model": selected_model,
			"api_url": api_url,
			"total_files": total_jobs,
			"success_count": len(sorted_results),
			"error_count": len(error_results),
			"results": sorted_results,
			"errors": error_results,
			"udi_split_done": True,
			"udi_linking_done": True,
		}
		st.session_state.analysis_history.insert(0, run_record)
		st.session_state.selected_history_run_id = run_record["run_id"]
		st.session_state.last_completed_run_id = run_record["run_id"]
		persist_run_record(run_record)
		render_end_of_run_summary(run_record)

	if st.session_state.analysis_history:
		selected_run = render_history_selector()
		if selected_run:
			if not selected_run.get("udi_split_done"):
				selected_run["results"] = expand_udi_results_by_sites(selected_run.get("results", []))
				selected_run["udi_split_done"] = True

			if not selected_run.get("udi_linking_done"):
				selected_run["results"] = link_udi_entries_by_site(selected_run.get("results", []))
				selected_run["udi_linking_done"] = True

			st.markdown(
				f"<div style='font-size:0.82rem; color:#4a6d88; font-family:\"JetBrains Mono\",monospace; "
				f"margin-bottom:0.4rem;'>📁 Run du {selected_run['timestamp']} &nbsp;·&nbsp; "
				f"<b style='color:#00d4ff;'>{selected_run['success_count']}/{selected_run['total_files']}</b> fichiers analysés</div>",
				unsafe_allow_html=True,
			)

			with st.expander("Mettre à jour les données d'un site", expanded=False):
				render_run_data_editor(selected_run)

			tab_overview, tab_compare, tab_sites, tab_report = st.tabs(
				["Vue générale", "Comparaison", "Sites", "Rapport PDF"]
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
				col_b.metric("Succès", selected_run.get("success_count", 0))
				col_c.metric("Erreurs", selected_run.get("error_count", 0))

				st.markdown("### Description du run")
				st.markdown('<div class="larzac-soft-panel">', unsafe_allow_html=True)
				st.info(
					f"Ce run contient **{selected_run.get('total_files', 0)}** fichier(s) "
					f"dont **{selected_run.get('success_count', 0)}** analyse(s) exploitable(s). "
					f"Types détectés : **{steu_count} STEU** et **{udi_count} UDI**."
				)
				st.markdown(
					"\n".join(
						[
							"- **Sites inclus** : " + site_list_label,
							"- **Comparaison réalisée** : tableau STEU orienté PV (surface disponible) et tableau UDI orienté Hydro (débit, chute, points de pression).",
							"- **Objectif** : prioriser les sites à instruire en premier pour les études ENR (photovoltaïque et micro-hydraulique).",
						]
					)
				)
				st.markdown('</div>', unsafe_allow_html=True)

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
					st.markdown('<div class="larzac-soft-panel">', unsafe_allow_html=True)
					if st.session_state.selected_site_idx >= len(site_results):
						st.session_state.selected_site_idx = 0
					nav_prev, nav_info, nav_next = st.columns([1, 2, 1])
					with nav_prev:
						if st.button(
							"◀ Précédent",
							help="Aller au site précédent",
							use_container_width=True,
						):
							st.session_state.selected_site_idx = (st.session_state.selected_site_idx - 1) % len(site_results)
					with nav_info:
						current_idx = st.session_state.selected_site_idx + 1
						total_sites = len(site_results)
						st.markdown(
							f"<div style='text-align:center; padding:0.4rem 0; color:#00d4ff; "
							f"font-weight:700; font-size:0.9rem; letter-spacing:0.04em;'>"
							f"<span style='color:#4a6d88;'>Site</span> {current_idx} "
							f"<span style='color:#4a6d88;'>/</span> {total_sites}</div>",
							unsafe_allow_html=True,
						)
					with nav_next:
						if st.button(
							"Suivant ▶",
							help="Aller au site suivant",
							use_container_width=True,
						):
							st.session_state.selected_site_idx = (st.session_state.selected_site_idx + 1) % len(site_results)
					selected_index = st.session_state.selected_site_idx
					selected_site_name = st.selectbox(
						"Sélectionner un site",
						options=[entry.get("site_name", "Site") for entry in site_results],
						index=selected_index,
					)
					selected_names = [entry.get("site_name", "Site") for entry in site_results]
					if selected_site_name in selected_names:
						st.session_state.selected_site_idx = selected_names.index(selected_site_name)
					selected_entry = next(
						(entry for entry in site_results if entry.get("site_name", "Site") == selected_site_name),
						site_results[0],
					)
					st.markdown('</div>', unsafe_allow_html=True)
					render_site_detail(selected_entry, show_debug=show_debug, all_results=site_results)

			with tab_report:
				st.markdown("### Rapport complet et détaillé")
				if not REPORTLAB_AVAILABLE:
					st.error("Le package 'reportlab' est requis pour générer le PDF. Installe-le avec: pip install reportlab")
				else:
					pdf_data = generate_pdf_report(selected_run)
					if pdf_data:
						st.success("Rapport PDF prêt.")
						st.download_button(
							label="Télécharger le rapport comparatif (.pdf)",
							data=pdf_data,
							file_name=f"rapport_comparatif_{selected_run.get('timestamp', 'run').replace(':', '-').replace(' ', '_')}.pdf",
							mime="application/pdf",
							use_container_width=True,
						)

				st.download_button(
					label="Télécharger le résultat brut (.json)",
					data=json.dumps(selected_run, ensure_ascii=False, indent=2),
					file_name="station_extraction_historique_run.json",
					mime="application/json",
					use_container_width=True,
				)


if __name__ == "__main__":
	main()
