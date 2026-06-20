# Maintenance et Mise à Jour - SimuWatter

## 🔄 Mise à Jour des Dépendances

### Vérifier les dépendances obsolètes

```bash
# Activer l'environnement virtuel
# Windows:
.venv\Scripts\activate.bat
# Linux/Mac:
source .venv/bin/activate

# Lister les packages obsolètes
pip list --outdated
```

### Mettre à jour les dépendances

```bash
# Mettre à jour pip d'abord
python -m pip install --upgrade pip

# Mettre à jour tous les packages
pip install --upgrade -r requirements.txt

# Exporter les versions actuelles (optionnel)
pip freeze > requirements-frozen.txt
```

---

## 🧪 Tests

### Exécuter les tests

```bash
# Activer l'environnement virtuel d'abord
python -m pytest tests/ -v
```

### Tester manuellement l'application

1. Lancer `run.bat` ou `./run.sh`
2. Tester les fonctionnalités principales
3. Vérifier les rapports PDF générés
4. Valider les exports financiers

---

## 📊 Nettoyage des Données

### Vider le cache Streamlit

```bash
# Windows:
rmdir /S .streamlit

# Linux/Mac:
rm -rf .streamlit
```

### Vider les données générées

```bash
# Windows:
rmdir /S data\runs

# Linux/Mac:
rm -rf data/runs
```

---

## 📝 Gestion des Logs

### Localisation des logs

- Logs Streamlit : Affichés dans le terminal
- Logs application : Dossier `data/logs/` (si créé)

### Archiver les anciens logs

```bash
# Créer un dossier archive
mkdir data/logs_archive
# Déplacer les anciens logs
mv data/logs/*.log data/logs_archive/
```

---

## 🔐 Gestion des Clés API

### Rotation des clés API

**Important** : Effectuer régulièrement une rotation des clés pour la sécurité.

1. Accéder à [console.groq.com](https://console.groq.com)
2. Générer une nouvelle clé API
3. Mettre à jour le `.env`
4. Supprimer l'ancienne clé

### Audit des clés

```bash
# Vérifier que .env n'est pas dans git
git log --all -p -- .env | head

# Vérifier le .gitignore
cat .gitignore | grep env
```

---

## 🐛 Dépannage Courant

### L'application plante au démarrage

1. Vérifier les logs du terminal
2. Vérifier que `.env` contient une clé API valide
3. Vérifier que toutes les dépendances sont installées
4. Supprimer le cache Streamlit
5. Réinstaller les dépendances

### Les analyses IA ne fonctionnent pas

1. Vérifier la clé API Groq
2. Vérifier la connexion internet
3. Vérifier les quotas API sur [console.groq.com](https://console.groq.com)
4. Voir les logs d'erreur dans le terminal

### Erreurs lors de l'export PDF

1. Vérifier que WeasyPrint est installé
2. Vérifier que le dossier `outputs/` existe et est accessible
3. Vérifier l'espace disque disponible

---

## 📋 Checklist de Maintenance Mensuelle

- [ ] Vérifier les mises à jour de dépendances
- [ ] Exécuter les tests
- [ ] Nettoyer les old data/logs
- [ ] Vérifier les quotas API Groq
- [ ] Tester l'export PDF
- [ ] Vérifier la documentation

---

## 💾 Sauvegarde et Récupération

### Sauvegarder les données

```bash
# Compresser le dossier data/
# Windows:
powershell Compress-Archive -Path data -DestinationPath data_backup.zip

# Linux/Mac:
tar -czf data_backup.tar.gz data/
```

### Restaurer les données

```bash
# Windows:
powershell Expand-Archive -Path data_backup.zip

# Linux/Mac:
tar -xzf data_backup.tar.gz
```

---

## 📞 Support et Escalade

### Avant de contacter le support

1. ✅ Vérifier les logs
2. ✅ Exécuter les étapes du dépannage
3. ✅ Vérifier la connexion internet
4. ✅ Vérifier les quotas API

### Informations à fournir

- Version Python : `python --version`
- Système d'exploitation
- Message d'erreur exact
- Étapes pour reproduire le problème
