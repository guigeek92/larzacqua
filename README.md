# energy-ai-tool
Projet : IA d’analyse énergétique pour station d’eau

Objectif :
Créer un outil qui lit automatiquement les documents techniques d’une station (PDF) et qui :

extrait les caractéristiques techniques

estime la consommation énergétique

propose un mix ENR pour alimenter la station

## Module extraction PDF (style ancien projet chatbot)

Le moteur détecte automatiquement le type de document :
- **STEU** (fiche station d'épuration)
- **UDI** (réseau/ouvrages hydrauliques, utile pour présélection micro-turbines)
	- inclut aussi les PDF de type **synoptique AEP / schéma hydraulique / réseau eau potable**

Puis applique un schéma d'extraction adapté à chaque type.

Architecture inspirée de ton ancien projet :
- `src/ai_extraction.py` : pipeline type RAG (`RAGPipeline`) avec sélection de modèle Groq
- `backend/main.py` : API FastAPI (`/extract`) pour traiter un PDF
- `app/streamlit_app.py` : interface utilisateur Streamlit

## Améliorations implémentées (étapes guidées)

Pour ne pas te perdre, les changements de code sont balisés avec des commentaires `STEP ...`.

Étape 1 - Observabilité backend
- Fichier : `backend/main.py`
- Ajout de logs structurés (`logging`) pour tracer succès/erreurs d'extraction.

Étape 2 - Contrat API explicite
- Fichier : `backend/main.py`
- Réponse API versionnée (`schema_version`) et modèle de réponse Pydantic.
- `result_json` devient le champ canonique, `result` reste conservé temporairement pour compatibilité.

Étape 3 - Sécurité concurrence backend
- Fichier : `backend/main.py`
- Suppression du pipeline global mutable.
- Instanciation d'un `RAGPipeline` par requête pour éviter les conflits de modèle entre utilisateurs/requêtes.

Étape 4 - Robustesse des appels API côté interface
- Fichier : `app/streamlit_app.py`
- Ajout d'une fonction centralisée avec retry/backoff : `request_extract_with_retry(...)`.
- Réduction des erreurs transitoires réseau/API lors des analyses en batch.

### Données extraites

Le système extrait les champs suivants depuis une fiche technique STEP :
- presence of pressure reducing valve (brise-charge)
- estimated head height
- flow rate
- available roof or land surface
- geographic location

Sortie : JSON structuré.

### Installation

Depuis la racine du projet :

```bash
python -m venv .venv
```

Activer l'environnement virtuel (PowerShell) :

```bash
.\.venv\Scripts\Activate.ps1
```

Installer les dépendances :

```bash
pip install -r requirements.txt
```

Alternative sans fichier requirements :

```bash
pip install streamlit fastapi uvicorn python-multipart requests pypdf groq python-dotenv pymupdf pytesseract pillow
```

Créer un fichier `.env` à la racine :

```env
GROQ_API_KEY=ta_cle_api_groq
HYDRO_MIN_FLOW_M3_J=50
# optionnel (Windows): chemin vers tesseract.exe
# TESSERACT_CMD=C:\\Program Files\\Tesseract-OCR\\tesseract.exe
```

`HYDRO_MIN_FLOW_M3_J` est utilisé pour un premier filtrage hydro :
- si `debit_m3_j` < seuil, alors `potentiel_hydraulique = false`
- si `debit_m3_j` n'est pas trouvé, le potentiel reste non documenté

Pour les PDF synoptiques/rotés (souvent UDI), le parser tente aussi une extraction OCR.
Prérequis OCR local :
- installer Tesseract OCR sur la machine
- définir `TESSERACT_CMD` dans `.env` si nécessaire (Windows)

Remarque UDI : certains synoptiques n'exposent pas explicitement le débit.
Dans ce cas, l'extraction remonte les données techniques disponibles (altitudes NGF, dénivelé estimé, ouvrages/points hydrauliques).

Mode multi-fichiers UDI :
- quand plusieurs PDF UDI d'un même domaine/site sont analysés dans le même run,
- l'application relie automatiquement les fichiers proches (nom UDI, localisation, communes, nom de fichier),
- puis complète les champs hydro manquants avec les informations pertinentes trouvées dans les autres fichiers liés.

### Lancer le backend

Terminal 1 :

```bash
python -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8010
```

### Lancer l'interface

Terminal 2 :

```bash
python -m streamlit run app/streamlit_app.py --server.port 8501
```

Puis charger un PDF dans l'interface et cliquer sur **Analyser le PDF**.

URLs utiles :
- API backend : `http://127.0.0.1:8010`
- Interface Streamlit : `http://127.0.0.1:8501`