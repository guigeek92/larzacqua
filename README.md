#  SimuWatter - Analyse Potentiel Hydroélectrique

**Outil d'analyse énergétique pour infrastructures d'eau à partir de données CSV**

---

##  Démarrage Rapide

Voir le guide rapide : **[QUICKSTART.md](QUICKSTART.md)**

En résumé :
1. Exécutez `setup.bat` (Windows) ou `./setup.sh` (Linux/Mac)
2. Configurez votre clé API Groq dans `.env`
3. Lancez `run.bat` (Windows) ou `./run.sh` (Linux/Mac)

---

## 📚 Installation Détaillée

Pour une installation complète : **[INSTALLATION.md](INSTALLATION.md)**

---

## 📋 Fonctionnalités

- ✅ Analyse hydraulique des sites
- ✅ Évaluation du potentiel hydroélectrique
- ✅ Sélection de turbines adaptées
- ✅ Analyses financières
- ✅ Génération de synthèses IA
- ✅ Rapports PDF exportables

---

## 📁 Structure

```
SimuWatter/
├── app/                    # Interface Streamlit
├── modules/                # Modules d'analyse
├── CSV/                    # Données sources
├── requirements.txt        # Dépendances
└── .env                    # Configuration
```

---

## ⚙️ Configuration

Clé API obligatoire :
- **GROQ_API_KEY** : https://console.groq.com

Voir [.env.example](.env.example)

## ☁️ Déploiement sur Streamlit Community Cloud avec GitHub

1. Poussez le projet sur un dépôt GitHub public ou privé accessible à votre compte Streamlit.
2. Connectez ce dépôt dans Streamlit Community Cloud et choisissez `streamlit_app.py` comme fichier principal.
3. Ajoutez `GROQ_API_KEY` dans les secrets de l'application Streamlit, pas dans le dépôt.
4. Vérifiez que `requirements.txt` et `runtime.txt` sont bien présents à la racine avant le déploiement.

Configuration locale utile :
- `.streamlit/config.toml` contient les réglages UI et serveur pour Streamlit.
- `.streamlit/secrets.toml` reste ignoré par Git pour éviter toute fuite de clé.

Si vous devez exposer aussi l'API FastAPI du dossier `backend/`, déployez-la sur un service séparé. Streamlit Community Cloud héberge l'interface Streamlit, pas le serveur FastAPI.

---

## 📖 Documentation

- [Installation Complète](INSTALLATION.md)
- [Démarrage Rapide](QUICKSTART.md)

---

## 📞 Support

Consultez la documentation ou les logs de l'application.

## Lancer l'interface de résumé Streamlit

### Prérequis

- Python 3.10 ou supérieur
- Installer les dépendances :

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Lancer les deux interfaces reliées

Dans un terminal, à la racine du projet, exécutez :

```bash
python -m streamlit run app/streamlit_resume.py --server.port 8501
```

Puis ouvrez aussi l’interface PV sur [http://localhost:8502](http://localhost:8502) si vous la lancez séparément.

Pour démarrer les deux interfaces avec le pont activé, utilisez plutôt :

```bash

run.bat
```

ou

```bash
./run.sh
```

L'interface hydro sera accessible à l'adresse : [http://localhost:8501](http://localhost:8501)

---
Pour toute question ou problème, consultez le code source ou la documentation.
