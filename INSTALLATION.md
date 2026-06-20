# Guide d'Installation - SimuWatter

## 📋 Prérequis

- **Python 3.10 ou supérieur** : Télécharger depuis [python.org](https://www.python.org/downloads/)
- **Clés API** (optionnel mais recommandé) :
  - Clé API Groq pour les analyses IA : https://console.groq.com

## Installation Rapide

### Windows

1. **Extraire l'archive** dans un dossier de votre choix
2. **Ouvrir PowerShell ou CMD** dans le dossier du projet
3. **Exécuter le script d'installation** :
   ```bash
   setup.bat
   ```
4. **Éditer le fichier `.env`** avec vos clés API
5. **Lancer l'application** :
   ```bash
   run.bat
   ```

### Linux / Mac

1. **Extraire l'archive** dans un dossier de votre choix
2. **Ouvrir un terminal** dans le dossier du projet
3. **Rendre les scripts exécutables** :
   ```bash
   chmod +x setup.sh run.sh
   ```
4. **Exécuter le script d'installation** :
   ```bash
   ./setup.sh
   ```
5. **Éditer le fichier `.env`** avec vos clés API
6. **Lancer l'application** :
   ```bash
   ./run.sh
   ```

## Configuration des Clés API

### Obtenir une clé API Groq (obligatoire pour les analyses IA)

1. Aller sur https://console.groq.com
2. Créer un compte ou se connecter
3. Générer une nouvelle clé API
4. Copier la clé dans le fichier `.env` :
   ```
   GROQ_API_KEY=votre_clé_ici
   ```

### Optionnel : Token Hugging Face

1. Aller sur https://huggingface.co/settings/tokens
2. Créer un nouveau token
3. Copier le token dans le fichier `.env` :
   ```
   HF_TOKEN=votre_token_ici
   ```

## Lancement de l'Application

Après l'installation, lancez l'application avec :

- **Windows** : `run.bat`
- **Linux/Mac** : `./run.sh`

L'interface sera accessible à l'adresse : **http://localhost:8501**

## Dépannage

### "Python n'est pas trouvé"
- Vérifiez que Python est installé : `python --version`
- Assurez-vous que Python est ajouté au PATH

### "Erreur lors de l'installation des dépendances"
- Essayez de mettre à jour pip : `python -m pip install --upgrade pip`
- Vérifiez votre connexion internet
- Vérifiez que vous avez les permissions d'écriture dans le dossier

### "Clé API Groq invalide"
- Vérifiez que la clé est correctement copiée dans `.env`
- Assurez-vous qu'il n'y a pas d'espaces supplémentaires
- Regénérez la clé sur https://console.groq.com si nécessaire

### "Le port 8501 est déjà utilisé"
- Changez le port dans le script `run.bat` ou `run.sh`
- Cherchez la ligne avec `--server.port 8501` et remplacez `8501` par un autre numéro

## Structure du Projet

```
SimuWatter/
├── app/                    # Application Streamlit
│   └── streamlit_resume.py # Interface principale
├── modules/                # Modules d'analyse
├── CSV/                    # Données sources
├── data/                   # Données générées
├── requirements.txt        # Dépendances Python
├── .env                    # Configuration des clés API
├── .env.example            # Template des clés API
├── setup.bat               # Installation (Windows)
├── setup.sh                # Installation (Linux/Mac)
├── run.bat                 # Lancement (Windows)
└── run.sh                  # Lancement (Linux/Mac)
```

## Support

Pour toute question ou problème, consultez :
- [Documentation Streamlit](https://docs.streamlit.io/)
- [Documentation Groq API](https://console.groq.com/docs)
- Les logs de l'application dans le terminal
