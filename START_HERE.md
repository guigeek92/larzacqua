# 🚀 DÉMARRER ICI - SimuWatter

Bienvenue! Ce fichier vous explique comment mettre en place SimuWatter en quelques minutes.

---

## ⚡ Démarrage en 3 Étapes (5-10 minutes)

### 1️⃣ Installation

Double-cliquez sur le fichier correspondant à votre système :

- **Windows** : `setup.bat`
- **Linux/Mac** : Ouvrir un terminal et exécuter `./setup.sh`

Si cela ne fonctionne pas, lire [INSTALLATION.md](INSTALLATION.md).

### 2️⃣ Configuration

1. Ouvrir le fichier `.env` avec un éditeur de texte (Bloc-notes, VSCode, etc.)
2. Aller sur https://console.groq.com
3. Créer un compte gratuit et générer une clé API
4. Copier cette clé dans le fichier `.env` à la ligne :
   ```
   GROQ_API_KEY=votre_clé_ici
   ```
5. Sauvegarder le fichier

### 3️⃣ Lancer l'Application

Double-cliquez sur le fichier correspondant à votre système :

- **Windows** : `run.bat`
- **Linux/Mac** : Ouvrir un terminal et exécuter `./run.sh`

L'interface s'ouvrira automatiquement sur : **http://localhost:8501**

---

## 📚 Besoin d'Aide ?

| Je veux... | Je dois lire... |
|-----------|-----------------|
| Un démarrage super rapide | [QUICKSTART.md](QUICKSTART.md) |
| Des détails d'installation | [INSTALLATION.md](INSTALLATION.md) |
| Importer mes données | [DATA_INTEGRATION.md](DATA_INTEGRATION.md) |
| Dépanner un problème | [INSTALLATION.md](INSTALLATION.md#-dépannage) |
| Maintenir l'application | [MAINTENANCE.md](MAINTENANCE.md) |
| Tout comprendre | [README.md](README.md) |

---

## ✅ Vérification Post-Installation

Après l'installation, vérifiez que :

- [ ] L'interface s'ouvre sur http://localhost:8501
- [ ] La page Streamlit se charge sans erreur
- [ ] Vous pouvez voir les données d'exemple
- [ ] Les boutons répondent au clic

Si quelque chose ne fonctionne pas :
1. Vérifier les messages d'erreur rouges dans le terminal
2. Lire [INSTALLATION.md](INSTALLATION.md)
3. Vérifier votre clé API Groq

---

## 🎯 Prochaines Étapes

1. **Explorer l'interface** : Cliquez sur les différents onglets
2. **Charger vos données** : Voir [DATA_INTEGRATION.md](DATA_INTEGRATION.md)
3. **Générer des rapports** : Utiliser les boutons d'export
4. **Exporter les résultats** : PDF, CSV, etc.

---

## 📞 En Cas de Problème

1. **Installation échoue** → Lire [INSTALLATION.md](INSTALLATION.md)
2. **Clé API invalide** → Aller sur https://console.groq.com
3. **L'app ne démarre pas** → Vérifier les logs du terminal
4. **Je n'ai pas de Python** → Installer Python 3.10+ depuis https://python.org

---

## 💡 Conseils Utiles

✓ Gardez le terminal ouvert pour voir les erreurs  
✓ La clé API est gratuite avec des limites  
✓ Vous pouvez charger vos propres données CSV  
✓ Les rapports PDF s'exportent facilement  

---

## 🔐 Sécurité Important

⚠️ **NE JAMAIS** partager votre fichier `.env` contenant votre clé API  
⚠️ **NE JAMAIS** uploader `.env` sur internet ou Git

---

**Bon usage de SimuWatter!** 💧

[Lire la documentation complète →](README.md)
