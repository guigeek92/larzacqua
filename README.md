# energy-ai-tool

Projet d'IA pour l'analyse energetique d'infrastructures d'eau (STEU/UDI) a partir de documents PDF techniques.

## Vue d'ensemble du site

Le site permet de charger des PDF metiers (fiches station, synoptiques AEP, schemas hydrauliques), d'en extraire automatiquement les donnees utiles, puis de produire une aide a la decision energetique.

Objectifs principaux :
- extraire des caracteristiques techniques fiables depuis des documents heterogenes
- estimer des potentiels energetiques (hydraulique, solaire, mix ENR)
- comparer plusieurs sites avec des filtres metiers
- generer un rapport synthese exploitable

## Infrastructure technique

### Architecture applicative

- `app/streamlit_app.py` : interface web Streamlit (upload, analyse, comparaison, export)
- `backend/main.py` : API FastAPI (endpoint `/extract`, contrat de sortie versionne)
- `src/ai_extraction.py` : pipeline d'extraction type RAG (`RAGPipeline`) avec modele IA
- `src/pdf_parser.py` : parsing PDF/OCR pour documents complexes
- `src/hydro_model.py`, `src/solar_model.py`, `src/energy_mix_optimizer.py` : calculs energetiques et optimisation de mix
- `data/runs/` : traces JSON des analyses realisees + base SQLite `history.sqlite3` pour historique persistant

### Flux de traitement

1. L'utilisateur depose un ou plusieurs PDF dans l'interface.
2. Streamlit envoie les fichiers a l'API FastAPI.
3. Le backend detecte le type de document (STEU ou UDI/synoptique AEP).
4. Le pipeline applique l'extraction adaptee (texte natif + OCR si necessaire).
5. Les donnees structurees sont consolidees en JSON.
6. L'interface affiche les resultats, scores de completude, classements, et rapport.

### Infrastructure d'execution locale

- Environnement Python virtuel (`.venv`)
- Serveur API local FastAPI/Uvicorn (port `8010`)
- Interface Streamlit locale (port `8501`)
- OCR local via Tesseract pour PDF peu lisibles ou scannes
- Variables de configuration via fichier `.env`

## Interfaces utilisateur

### Interface Streamlit

L'interface est organisee autour d'un parcours d'analyse metier :

- import de PDF et lancement d'analyse
- vue **Comparaison** : tableau unifie STEU/UDI avec filtres et ponderations
- vue **Sites > Infrastructure site** : regroupement des fichiers UDI lies
- vue **Sites > Localisation** : geolocalisation directe ou geocodage assiste
- vue **Rapport PDF** : export des resultats consolides
- historique permanent des runs (charge automatiquement entre sessions)
- edition manuelle des donnees extraites par site, avec sauvegarde persistante

### API FastAPI

- endpoint principal : `/extract`
- reponse normalisee avec `schema_version`
- `result_json` est le champ canonique de sortie
- `result` est conserve pour compatibilite temporaire

## Outils et technologies utilises

### Stack principale

- Python
- Streamlit (frontend applicatif)
- FastAPI + Uvicorn (backend API)
- Pydantic (contrats de donnees)
- PyMuPDF / pypdf (lecture PDF)
- Tesseract + pytesseract (OCR)
- Pillow (traitement image)
- Groq API (composant IA du pipeline)
- pytest (tests)

### Extraction metier STEU/UDI

Le moteur prend en charge :
- documents STEU (station d'epuration)
- documents UDI (reseau eau potable, ouvrages hydrauliques)
- synoptiques AEP et schemas hydrauliques

Exemples de champs extraits :
- presence de reducteur/brise-charge
- hauteur de chute estimee
- debit
- surfaces mobilisables (toiture/sol)
- elements d'infrastructure (reservoir, source, forage, pompe, etc.)
- localisation

### Detection de pictogrammes sur synoptiques

Pipeline hybride vision + OCR :
1. conversion du PDF en image haute resolution
2. detection des symboles (approche type YOLO)
3. extraction OCR autour du symbole
4. reconstruction d'objets techniques avec attributs

Implementation actuelle (modulaire) :
- `src/symbol_detection.py` : detecteurs OpenCV (template matching) et YOLO (inference standardisee)
- `src/infrastructure_mapper.py` : mapping `symboles -> entites metier` + relations (`infrastructure_graph`)
- `src/ai_extraction.py` : enrichissement UDI avec `symbol_detections` et retro-compatibilite des champs existants

References de legendes utilisees pour la calibration OCR symbole :
- `legende 1.JPG`
- `legende 2.JPG`

Mode sans dataset YOLO (template bank) :
- Script de bootstrap : `scripts/bootstrap_symbol_templates.py`
- Le script extrait des candidats de symboles depuis `legende 1.JPG` et `legende 2.JPG`
- Pour `legende 1`, le bootstrap guide est limite a 1 template par ligne OCR et 15 templates max
- Les templates valides doivent ensuite etre ranges dans `data/templates_symbols/<symbol>/`
- Le pipeline UDI charge automatiquement ces templates et ajoute les detections dans `result_json["symbol_detections"]`

Commande de bootstrap :

```bash
$env:PYTHONPATH='.'
& ".venv/Scripts/python.exe" scripts/bootstrap_symbol_templates.py --legend1 "legende 1.JPG" --legend2 "legende 2.JPG"
```

Format de sortie standardise ajoute dans `result_json` :

```json
[
	{
		"symbol": "pressure_reducer",
		"confidence": 0.92,
		"bounding_box": [112.4, 284.1, 156.9, 321.0],
		"page": 5,
		"site": "Site_A",
		"method": "yolo"
	}
]
```

Classes principales detectees :
- `SOURCE`
- `FORAGE`
- `RESERVOIR`
- `POMPE`
- `VANNE`
- `COMPTEUR`
- `TRAITEMENT_UV`
- `TRAITEMENT_CHLORE`
- `FILTRATION`

### Robustesse et qualite deja integrees

- logs structures backend pour le suivi d'execution
- instanciation du pipeline par requete (evite les conflits en concurrence)
- retry/backoff cote interface pour les erreurs transitoires
- indicateur de completude des donnees extraites
- filtres et ponderations metier pour ajuster le classement

## Installation et lancement

### Prerequis

- Python 3.10+
- Tesseract OCR installe localement (recommande pour UDI/synoptiques)

### Installation

```bash
python -m venv .venv
```

```bash
\.venv\Scripts\Activate.ps1
```

```bash
pip install -r requirements.txt
```

Configurer `.env` a la racine :

```env
GROQ_API_KEY=ta_cle_api_groq
HYDRO_MIN_FLOW_M3_J=50
# Optionnel (Windows)
# TESSERACT_CMD=C:\\Program Files\\Tesseract-OCR\\tesseract.exe
```

### Execution

Terminal 1 (API) :

```bash
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8010
```

Terminal 2 (interface) :

```bash
python -m streamlit run app/streamlit_app.py --server.port 8501
```

Limite recommandee pour eviter les erreurs de timeout : **10 fichiers PDF max par analyse**.

URLs locales :
- API : `http://127.0.0.1:8010`
- Interface : `http://127.0.0.1:8501`

## Problemes actuels et limites

- Qualite variable des PDF : scans bruites, rotation, faible resolution, tableaux non structures.
- OCR sensible a la qualite image : erreurs possibles sur abreviations techniques et unites.
- Donnees metier parfois absentes : certains synoptiques ne donnent pas explicitement le debit.
- Heterogeneite de vocabulaire entre territoires/exploitants (noms d'ouvrages, conventions locales).
- Couplage fort a des heuristiques metier : necessite un recalibrage si la typologie des documents evolue.
- Dependance a des services externes IA : latence/cout/disponibilite a surveiller.

## Perspectives d'amelioration

- Ajouter un systeme de score de confiance par champ extrait (pas seulement global).
- Mettre en place une validation humaine assistee avec correction rapide des champs incertains.
- Enrichir les jeux de tests reels UDI/STEU et automatiser des benchmarks de precision.
- Industrialiser la detection de pictogrammes (dataset annote, versionning modele, metriques mAP/F1).
- Ajouter une persistance base de donnees pour historiser les analyses (au-dela de `data/runs/`).
- Exposer une API de consultation des runs et un mode batch planifiable.
- Ajouter observabilite avancee (traces, metriques de latence, taux d'erreur par type de PDF).
- Renforcer la gestion multi-utilisateur (authentification, quotas, journalisation d'audit).

## Tests

Le projet contient une base de tests dans `tests/`, notamment sur :
- extraction UDI comparee a un referentiel expert
- parsing PDF de cas reels
- detection d'ouvrages et robustesse des heuristiques

Execution type :

```bash
$env:PYTHONPATH='.'
python -m pytest -q
```