# Guide d'Empaquetage et d'Export - SimuWatter

## 📦 Avant d'Exporter

Avant de remettre le projet au client, assurez-vous que :

### 1. ✅ Fichiers Sensibles

- [ ] `.env` n'est **PAS** inclus (doit rester SECRET)
- [ ] `.env.example` est présent avec les variables nécessaires
- [ ] `.git/` et `.github/` peuvent être supprimés
- [ ] Fichiers de développement supprimés (`.pytest_cache/`, `__pycache__/`, etc.)

### 2. ✅ Documentation

- [ ] [README.md](README.md) est à jour
- [ ] [QUICKSTART.md](QUICKSTART.md) est présent
- [ ] [INSTALLATION.md](INSTALLATION.md) est présent
- [ ] Tous les liens sont valides

### 3. ✅ Scripts de Démarrage

- [ ] `setup.bat` et `setup.sh` sont exécutables
- [ ] `run.bat` et `run.sh` sont exécutables
- [ ] Chemins sont relatifs (pas d'absolus)

### 4. ✅ Configuration

- [ ] [.env.example](.env.example) contient tous les paramètres
- [ ] [.streamlit/config.toml](.streamlit/config.toml) est optimisé
- [ ] `requirements.txt` est à jour

---

## 🗂️ Structure d'Export Recommandée

```
SimuWatter-Livrable/
├── app/
├── modules/
├── CSV/
├── data/
├── scripts/
├── templates/
├── tests/
├── src/
├── .streamlit/
│   └── config.toml
├── .gitignore
├── .env.example
├── README.md
├── QUICKSTART.md
├── INSTALLATION.md
├── requirements.txt
├── setup.bat
├── run.bat
├── setup.sh
├── run.sh
└── [autres fichiers nécessaires]
```

---

## 📋 Checklist d'Exportation

### À INCLURE
- [x] Code source (`app/`, `modules/`, `src/`, etc.)
- [x] Données (`CSV/`)
- [x] Documentation (`README.md`, `INSTALLATION.md`, `QUICKSTART.md`)
- [x] Scripts de lancement (`run.bat`, `run.sh`, `setup.bat`, `setup.sh`)
- [x] Configuration (`.env.example`, `.streamlit/config.toml`)
- [x] Dépendances (`requirements.txt`)
- [x] Tests (`tests/`)

### À EXCLURE
- [ ] `.env` (clés API secrètes)
- [ ] `.git/` et `.github/`
- [ ] `.venv/` et autres environnements virtuels
- [ ] `__pycache__/` et `.pytest_cache/`
- [ ] `*.pyc`, `*.pyo`
- [ ] Fichiers temporaires (`.swp`, `~`, etc.)
- [ ] IDE settings (`.vscode/`, `.idea/`)
- [ ] OS files (`Thumbs.db`, `.DS_Store`)

---

## 🔧 Préparation de l'Export

### Option 1: Archive ZIP (Recommandé)

```bash
# Créer une archive en excluant les fichiers sensibles
# Windows PowerShell :
Compress-Archive -Path SimuWatter -DestinationPath SimuWatter-Livrable.zip -Exclude .env,.git,.venv,__pycache__,.pytest_cache,*.pyc

# Linux/Mac :
zip -r SimuWatter-Livrable.zip SimuWatter -x ".env" ".git/*" ".venv/*" "__pycache__/*" "*.pyc"
```

### Option 2: Dossier Propre

1. Copier le dossier projet
2. Supprimer manuellement les éléments de la section "À EXCLURE"
3. Vérifier la documentation
4. Compresser ou livrer directement

---

## ✅ Validation Finale

Avant livraison, tester l'installation sur un PC vierge :

1. Extraire l'archive
2. Exécuter `setup.bat` ou `./setup.sh`
3. Vérifier que toutes les dépendances s'installent
4. Ajouter une clé API Groq de test
5. Exécuter `run.bat` ou `./run.sh`
6. Vérifier que l'interface se charge correctement

---

## 📝 Notes de Livraison

Inclure avec le livrable :

```
Bienvenue dans SimuWatter !

Pour commencer :
1. Lire QUICKSTART.md
2. Exécuter setup.bat (Windows) ou ./setup.sh (Linux/Mac)
3. Ajouter votre clé API Groq dans .env
4. Exécuter run.bat ou ./run.sh

En cas de problème, consultez INSTALLATION.md

Bon usage !
```

---

## 🚨 Sécurité

⚠️ **IMPORTANT** : Ne JAMAIS partager votre `.env` contenant les vraies clés API

- Chaque client doit avoir son propre `.env` avec ses propres clés
- Utilisez `.env.example` comme template
- Conservez les clés API en toute sécurité

---

## 📞 Support Client

Fournir au client :
1. [QUICKSTART.md](QUICKSTART.md) pour démarrer
2. [INSTALLATION.md](INSTALLATION.md) pour les problèmes
3. Lien vers [Groq Console](https://console.groq.com) pour la clé API
