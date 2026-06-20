# 📦 Checklist Livrable - SimuWatter

Date de livraison : `___________`  
Client : `___________`  
Version : `___________`

---

## ✅ Fichiers Inclus

### Documentation
- [ ] README.md - Guide principal
- [ ] QUICKSTART.md - Démarrage rapide (à lire d'abord)
- [ ] INSTALLATION.md - Installation complète et dépannage
- [ ] DATA_INTEGRATION.md - Comment charger vos données
- [ ] MAINTENANCE.md - Maintenance et mises à jour
- [ ] EXPORT.md - Préparation d'export
- [ ] Cette checklist

### Code Source
- [ ] Dossier `app/` - Interface Streamlit
- [ ] Dossier `modules/` - Modules d'analyse
- [ ] Dossier `src/` - Code source supplémentaire
- [ ] Dossier `CSV/` - Données d'exemple
- [ ] Dossier `data/` - Répertoire de données
- [ ] Dossier `templates/` - Templates rapports

### Scripts et Configuration
- [ ] setup.bat - Installation Windows
- [ ] setup.sh - Installation Linux/Mac
- [ ] run.bat - Lancement Windows
- [ ] run.sh - Lancement Linux/Mac
- [ ] requirements.txt - Dépendances Python
- [ ] .env.example - Template variables d'environnement
- [ ] .streamlit/config.toml - Configuration Streamlit
- [ ] .gitignore - Fichiers ignorés Git

### Tests
- [ ] Dossier `tests/` - Tests unitaires

---

## ⚠️ Fichiers NON Inclus (Confidentiel)

- ❌ `.env` avec vraies clés API
- ❌ `.git/` et `.github/`
- ❌ `.venv/` (environnement virtuel)
- ❌ `__pycache__/` et autres caches
- ❌ Fichiers temporaires

---

## 🚀 Étapes de Démarrage du Client

### 1️⃣ Installation (5-10 min)

```bash
# Windows
setup.bat

# Linux/Mac
./setup.sh
```

### 2️⃣ Configuration (2-3 min)

1. Ouvrir `.env` avec un éditeur de texte
2. Obtenir une clé API depuis https://console.groq.com
3. Remplir : `GROQ_API_KEY=votre_clé_ici`
4. Sauvegarder

### 3️⃣ Lancement (1 min)

```bash
# Windows
run.bat

# Linux/Mac
./run.sh
```

Interface : http://localhost:8501

---

## 📋 Vérification Post-Installation

Avant de considérer l'installation comme réussie, vérifier :

- [ ] Application lancée sur http://localhost:8501
- [ ] Interface Streamlit chargée
- [ ] Pas d'erreurs rouges dans le terminal
- [ ] Données d'exemple chargées
- [ ] Les analyses IA fonctionnent (avec clé API)

---

## 📚 Documentation à Consulter

| Pour... | Lire... |
|---------|---------|
| Démarrer rapidement | [QUICKSTART.md](QUICKSTART.md) |
| Installer l'app | [INSTALLATION.md](INSTALLATION.md) |
| Importer vos données | [DATA_INTEGRATION.md](DATA_INTEGRATION.md) |
| Maintenir l'app | [MAINTENANCE.md](MAINTENANCE.md) |
| Problèmes courants | [INSTALLATION.md](INSTALLATION.md#-dépannage) |

---

## 🔑 Clés API Requises

### Obligatoire : Groq API

- **Pourquoi** : Analyses IA et synthèses
- **Coût** : Vérifier les tarifs sur https://console.groq.com
- **Obtenir** : https://console.groq.com/keys
- **Où mettre** : `.env` → `GROQ_API_KEY=...`

### Optionnel : Hugging Face

- **Pourquoi** : Certains modèles avancés
- **Obtenir** : https://huggingface.co/settings/tokens
- **Où mettre** : `.env` → `HF_TOKEN=...`

---

## 💻 Configuration Système Requise

| Élément | Minimum | Recommandé |
|---------|---------|-----------|
| Python | 3.10 | 3.11+ |
| RAM | 4 GB | 8 GB+ |
| Disque | 500 MB | 2 GB+ |
| OS | Windows/Linux/Mac | Récent |
| Connexion | Internet | Haut débit |

---

## 🎯 Fonctionnalités Clés

### Analyse Hydraulique
- ✅ Calcul des pressions et débits
- ✅ Analyse de viabilité
- ✅ Estimation des hauteurs de chute

### Analyse Énergétique
- ✅ Évaluation du potentiel hydroélectrique
- ✅ Sélection de turbines compatibles
- ✅ Estimation de la production d'énergie

### Analyses Financières
- ✅ Calcul OPEX
- ✅ Estimation des revenus
- ✅ Analyse de rentabilité
- ✅ Analyse de sensibilité

### Synthèses IA
- ✅ Génération de rapports pédagogiques
- ✅ Analyse contextuelle des sites
- ✅ Recommandations personnalisées

### Exports
- ✅ Rapports PDF
- ✅ Tableaux Excel/CSV
- ✅ Visualisations interactives

---

## 🐛 Dépannage Rapide

| Problème | Solution | Plus d'info |
|----------|----------|-----------|
| "Python not found" | Installer Python 3.10+ | [python.org](https://www.python.org) |
| Erreur installation | Vérifier internet et permissions | [INSTALLATION.md](INSTALLATION.md) |
| Port 8501 en usage | Modifier le port dans `run.bat` | [MAINTENANCE.md](MAINTENANCE.md) |
| API Groq invalide | Regénérer la clé | https://console.groq.com |

Pour plus : Voir [INSTALLATION.md](INSTALLATION.md)

---

## 📞 Support Client

### Ressources Fournies
- Documentation complète (5 fichiers)
- Scripts d'installation automatisés
- Code source commenté
- Exemples de données

### Avant de Contacter
1. Lire [QUICKSTART.md](QUICKSTART.md)
2. Essayer [INSTALLATION.md](INSTALLATION.md)
3. Vérifier les logs du terminal
4. Consulter [MAINTENANCE.md](MAINTENANCE.md)

### Informations Utiles pour le Support
- `python --version`
- Système d'exploitation
- Message d'erreur exact
- Étapes pour reproduire

---

## 🔐 Sécurité

### Points Importants

⚠️ **Ne JAMAIS** :
- Partager le fichier `.env` avec les vraies clés
- Commiter `.env` sur Git
- Publier les clés API

✅ **À FAIRE** :
- Garder `.env` local et sécurisé
- Utiliser `.env.example` comme template
- Créer une nouvelle clé API pour chaque client/environnement
- Rotater les clés régulièrement

---

## ✨ Après Installation

Conseils d'utilisation :

1. **Charger les données** : Voir [DATA_INTEGRATION.md](DATA_INTEGRATION.md)
2. **Tester les analyses** : Utiliser les données d'exemple
3. **Explorer les fonctionnalités** : Interface intuitive
4. **Exporter les résultats** : Générer des rapports
5. **Consulter la doc** : En cas de besoin

---

## 📅 Maintenance Recommandée

- **Mensuel** : Vérifier les mises à jour
- **Trimestriel** : Nettoyer les données
- **Semestriel** : Renouveler les clés API
- **Annuel** : Audit complet

Voir [MAINTENANCE.md](MAINTENANCE.md) pour plus.

---

## ✅ Signature de Livraison

- **Date** : _______________
- **Livreur** : _______________
- **Client** : _______________
- **Signature** : _______________

---

**Bon usage de SimuWatter !** 💧

Pour toute question : Consultez la documentation fournie.
