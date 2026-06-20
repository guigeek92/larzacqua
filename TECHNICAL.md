# Documentation Technique - SimuWatter

## 🏗️ Architecture Globale

```
┌─────────────────────────────────────────────────────────┐
│                  Interface Streamlit (app/)              │
│              (streamlit_resume.py, acteurs.py)            │
└──────────────────┬──────────────────────────────────────┘
                   │
        ┌──────────┴──────────┐
        │                     │
        ▼                     ▼
   ┌─────────────┐    ┌──────────────┐
   │  Modules    │    │   FastAPI    │
   │ (modules/)  │    │ (backend/)   │
   └──────┬──────┘    └──────────────┘
          │
   ┌──────┴──────────────┐
   │                     │
   ▼                     ▼
┌─────────────┐    ┌──────────────┐
│  Données    │    │ Sources CSV  │
│ (CSV/, DB)  │    │  (CSV/)      │
└─────────────┘    └──────────────┘
```

---

## 📂 Structure des Dossiers

### `app/`
Interface utilisateur Streamlit
```
app/
├── streamlit_resume.py    # Application principale
└── streamlit_ancien.py    # Version précédente (archive)
```

**Technologie** : Streamlit (framework web Python)

### `modules/`
Cœur métier de l'analyse
```
modules/
├── loader.py              # Chargement des données
├── hydraulics.py          # Calculs hydrauliques
├── power.py               # Calculs énergétiques
├── turbine.py             # Sélection de turbines
├── scoring.py             # Évaluation des sites
├── pdf_report.py          # Génération de rapports PDF
├── pdf_report2.py         # Alternative rapport PDF
├── finances.py            # Analyses financières
├── capex.py               # Calculs CAPEX
├── productible.py         # Estimation production
└── streamlit_financial_views.py  # Vues financières
```

**Technologie** : Python pur (NumPy, Pandas, ReportLab)

### `src/`
Code source complémentaire
```
src/
├── infrastructure_mapper.py    # Cartographie infrastructure
├── solar_model.py              # Modèle solaire
├── run_history_store.py        # Historique exécution
└── _archive_old_version/       # Archives anciennes
```

### `backend/`
API FastAPI (optionnel)
```
backend/
└── main.py                # Serveur API FastAPI
```

**Technologie** : FastAPI (framework API moderne)

### `CSV/`
Données pré-chargées
```
CSV/
├── aep_*.csv              # Données AEP (adduction eau potable)
├── turbine_db.csv         # Base de données turbines
└── reducteurs_debit_reel.csv  # Données réducteurs
```

### `data/`
Données générées et persistantes
```
data/
├── runs/                  # Historique des exécutions
├── templates_symbols/     # Templates symboles
└── _backup_old_version/   # Sauvegardes anciennes
```

### `templates/`
Templates HTML pour rapports
```
templates/
└── report_template.html   # Template rapport HTML
```

### `tests/`
Tests unitaires
```
tests/
├── test_hydraulics.py
├── test_power.py
├── test_turbine_selection.py
└── ...
```

### `scripts/`
Scripts utilitaires
```
scripts/
├── convert_coords_to_wgs84.py  # Conversion coordonnées
├── csv_to_json.py              # Conversion CSV→JSON
├── generate_maquette.py        # Génération maquette
└── generate_weasy_pdf.py       # Génération PDF WeasyPrint
```

---

## 🔄 Flux de Données Simplifié

```
1. Utilisateur sélectionne un site
   ↓
2. Données chargées (CSV) → modules/loader.py
   ↓
3. Analyses hydrauliques → modules/hydraulics.py
   ↓
4. Calcul puissance → modules/power.py
   ↓
5. Sélection turbines → modules/turbine.py
   ↓
6. Évaluation financière → modules/finances.py
   ↓
7. Synthèse IA → API Groq (si API key)
   ↓
8. Affichage résultats + export PDF/CSV
```

---

## 🔑 Points d'Entrée Principaux

### Interface Web
- **Fichier** : `app/streamlit_resume.py`
- **Lancement** : `streamlit run app/streamlit_resume.py`
- **Port** : 8501 (configurable dans `.streamlit/config.toml`)

### API Backend
- **Fichier** : `backend/main.py`
- **Lancement** : `cd backend && python main.py`
- **Port** : 8000 (par défaut)

---

## 📦 Dépendances Principales

Voir `requirements.txt` pour la liste complète.

### Critiques
- **streamlit** : Interface web
- **pandas** : Manipulation données
- **numpy** : Calculs numériques
- **reportlab** : Génération PDF

### Analyses
- **scipy** : Calculs scientifiques
- **scikit-learn** : Machine Learning (optionnel)

### API & Communication
- **fastapi** : API REST
- **uvicorn** : Serveur ASGI
- **requests** : Requêtes HTTP
- **python-dotenv** : Variables d'environnement

### Extraction Documents
- **pypdf** : Extraction PDF
- **pytesseract** : OCR
- **pymupdf** : Lecture PDF avancée

### IA
- **groq** : API Groq (synthèses IA)
- **openai** : Client OpenAI compatible

---

## 🔌 Variables d'Environnement

Définies dans `.env` (voir `.env.example`) :

```python
GROQ_API_KEY=...      # Clé API Groq (obligatoire pour IA)
HF_TOKEN=...          # Token Hugging Face (optionnel)
```

Chargé au démarrage avec `python-dotenv`.

---

## 🗄️ Modèle de Données Principal

### Site (Ressource)
```python
{
    'id': int,
    'NOM': str,
    'latitude': float,      # WGS84
    'longitude': float,     # WGS84
    'altitude': float,      # mètres
    'debit': float,         # l/s
    'debit_min': float,
    'debit_max': float,
}
```

### Hauteur de Chute
```python
{
    'hauteur_statique': float,   # mètres
    'pertes_charge': float,       # mètres
    'hauteur_nette': float,       # = statique - pertes
}
```

### Turbine Compatible
```python
{
    'modele': str,
    'type': str,            # Pelton, Turgo, Crossflow, etc.
    'debit_min': float,
    'debit_max': float,
    'hauteur_min': float,
    'hauteur_max': float,
    'puissance': float,     # kW
    'rendement': float,     # %
}
```

---

## 🔐 Gestion Sécurité

### Secrets
- Clés API **stockées en `.env`** (jamais en dur)
- `.env` **exclu de Git** (voir `.gitignore`)
- `.env.example` fourni comme template

### Chemins
- Chemins **relatifs** (pas d'absolus)
- Accès fichiers via `pathlib.Path`

### Données Utilisateur
- Pas de stockage par défaut (données dans CSV)
- Historique dans `data/runs/` (local)

---

## 🧪 Tests

### Exécuter les tests
```bash
python -m pytest tests/ -v
```

### Fichiers tests
```
tests/
├── test_hydraulics.py     # Hydraulique
├── test_power.py          # Puissance
├── test_turbine_selection.py  # Sélection turbines
├── test_preprocessing.py   # Prétraitement
└── ...
```

---

## 🚀 Déploiement

### Local
```bash
./run.bat              # Windows
./run.sh               # Linux/Mac
```

### Production
Voir `backend/main.py` pour configuration serveur.

### Docker (optionnel)
Structure compatible Docker :
```dockerfile
FROM python:3.10
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["streamlit", "run", "app/streamlit_resume.py"]
```

---

## 📊 Performance

### Optimisations en Place
- Cache Streamlit (`@st.cache_data`)
- Lectures CSV une seule fois
- Calculs vectorisés (NumPy)

### Points à Monitor
- Temps chargement CSV volumineux
- Requêtes API Groq (délai réseau)
- Génération PDF (CPU intensif)

---

## 🔧 Maintenance Code

### Style
- Python 3.10+
- Imports explicites
- Docstrings où nécessaire

### Conventions
- Noms français pour domaine (hydraulique, turbine)
- Noms anglais pour technique (variables, fonctions)

### Logs
```python
import logging
logger = logging.getLogger(__name__)
logger.info("Message")
logger.error("Erreur")
```

---

## 📈 Extension / Customisation

### Ajouter une Nouvelle Analyse

1. Créer module dans `modules/`
2. Implémenter logique métier
3. Intégrer dans `app/streamlit_resume.py`
4. Ajouter tests dans `tests/`

### Ajouter un Endpoint API

1. Ajouter route dans `backend/main.py`
2. Implémenter logique
3. Tester avec `/docs` (Swagger automatique)

### Ajouter un Template de Rapport

1. Créer HTML dans `templates/`
2. Implémenter génération dans `modules/pdf_report.py`
3. Intégrer dans interface

---

## 🐛 Debug

### Logs Streamlit
Affichés dans le terminal lors du lancement.

### Print Debugging
```python
print(f"DEBUG: variable={value}")  # Visible dans terminal
```

### Debugger Python
```python
import pdb; pdb.set_trace()  # Breakpoint
```

### VS Code
Configuration `.vscode/launch.json` pour debug.

---

## 📚 Ressources Techniques

- [Streamlit Docs](https://docs.streamlit.io/)
- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [Pandas Docs](https://pandas.pydata.org/)
- [Groq API Docs](https://console.groq.com/docs)
- [Python Official](https://python.org/)

---

## 📞 Questions Techniques

Pour questions de développement, voir :
1. Docstrings dans le code
2. Commentaires inline
3. Cette documentation
4. Les tests comme exemples
