# Intégration des Données - SimuWatter

## 📂 Structure des Données

### Dossier CSV/

Contient les données d'infrastructure pré-chargées :

```
CSV/
├── aep_canalisation.csv          # Canalisations
├── aep_hydrant.csv               # Hydrants
├── aep_organe_pression.csv       # Organes de pression
├── aep_reservoir.csv             # Réservoirs
├── aep_ressource.csv             # Sources d'eau
├── reducteurs_debit_reel.csv     # Réducteurs de débit
└── turbine_db.csv                # Base de données turbines
```

---

## 🔄 Importer Vos Propres Données

### Format Requis

Les fichiers CSV doivent être en **UTF-8** avec séparateur **virgule (,)** ou **point-virgule (;)**.

### Colonnes Essentielles par Type

#### 1. **Canalisations** (aep_canalisation.csv)
```
id, NOM, diametre, longueur, materiau, etat, ...
```

#### 2. **Hydrants** (aep_hydrant.csv)
```
id, NOM, latitude, longitude, altitude, debit, pression, ...
```

#### 3. **Réservoirs** (aep_reservoir.csv)
```
id, NOM, latitude, longitude, volume, altitude, ...
```

#### 4. **Ressources** (aep_ressource.csv)
```
id, NOM, latitude, longitude, debit, altitude, ...
```

### Étapes d'Intégration

1. **Préparer vos fichiers CSV**
   - Format UTF-8
   - Séparateur : virgule ou point-virgule
   - Colonnes en minuscules

2. **Placer les fichiers** dans le dossier `CSV/`
   - Nommer selon les conventions du projet
   - Garder les noms de colonnes cohérents

3. **Redémarrer l'application**
   - Fermer et relancer `run.bat` ou `./run.sh`
   - L'app recharge automatiquement les données

4. **Valider les données**
   - Vérifier l'interface Streamlit
   - Chercher les erreurs de chargement

---

## 📊 Système de Coordonnées

### Système par Défaut

- **WGS84** (EPSG:4326) : Latitude/Longitude standard
  - Format : `43.123456, 3.456789`

### Conversion des Coordonnées

Si vos données sont en **Lambert 93** (EPSG:2154) ou **Lambert II étendu** (EPSG:3943) :

1. Utiliser le script de conversion :
   ```bash
   python scripts/convert_coords_to_wgs84.py
   ```

2. Ou convertir manuellement :
   ```python
   from pyproj import Transformer
   transformer = Transformer.from_crs("EPSG:3943", "EPSG:4326", always_xy=True)
   lon_wgs84, lat_wgs84 = transformer.transform(lon, lat)
   ```

---

## 🎯 Utilisation dans l'Interface

### 1. Charger un Hydrant ou Réservoir

1. Ouvrir l'application Streamlit
2. Sélectionner le site dans la liste déroulante
3. Les données associées se chargent automatiquement

### 2. Analyser Hydrauliquement

1. Cliquer sur "Analyser" ou onglet "Hydraulique"
2. Les paramètres de pression, débit, altitude sont calculés
3. Résultats affichés en temps réel

### 3. Évaluer le Potentiel Énergétique

1. Accéder à l'onglet "Potentiel Énergétique"
2. Voir les turbines compatibles
3. Estimer les revenus potentiels

### 4. Exporter les Résultats

1. Générer un rapport PDF
2. Exporter les données en CSV
3. Créer des visualisations

---

## ✅ Validation des Données

### Points de Contrôle

- ✓ Tous les fichiers CSV existent
- ✓ Colonnes essentielles présentes
- ✓ Pas de valeurs manquantes critiques
- ✓ Coordonnées en WGS84
- ✓ Altitudes en mètres
- ✓ Débits en l/s ou m³/s (cohérent)

### Dépannage des Données

#### "Erreur de chargement"
- Vérifier le format du CSV
- Vérifier l'encodage (UTF-8)
- Vérifier les noms de colonnes

#### "Valeurs manquantes"
- Remplir les champs critiques
- Utiliser des valeurs par défaut si approprié
- Documenter les approximations

#### "Mauvaises coordonnées"
- Vérifier le système de coordonnées (WGS84)
- Convertir si nécessaire
- Valider avec une carte

---

## 📝 Exemple d'Intégration Complète

### Scénario : Ajouter un Nouveau Site

1. **Collecter les données** :
   ```
   Nom : Usine de Traitement X
   Latitude : 43.7123
   Longitude : 3.4567
   Altitude : 250 m
   Débit disponible : 150 l/s
   Hauteur de chute : 45 m
   ```

2. **Créer un CSV** `nouveau_site.csv` :
   ```csv
   id,NOM,latitude,longitude,altitude,debit,hauteur_chute
   1,Usine X,43.7123,3.4567,250,150,45
   ```

3. **Placer dans** `CSV/aep_ressource.csv` (ou nouveau fichier)

4. **Redémarrer** l'application

5. **Valider** dans l'interface Streamlit

---

## 🔗 Intégration API

### Charger les Données par API (FastAPI)

Voir `backend/main.py` pour les endpoints disponibles :

```bash
# Lancer le serveur API
cd backend
python main.py
```

API disponible sur : `http://localhost:8000`

Documentation interactive : `http://localhost:8000/docs`

---

## 📞 Support d'Intégration

### Questions Courantes

**Q: Quel format de coordonnées utiliser ?**
A: WGS84 (Latitude/Longitude standard)

**Q: Mon CSV n'est pas trouvé**
A: Vérifier le dossier `CSV/` et le nom du fichier

**Q: Comment importer des données externes ?**
A: Voir section "Importer Vos Propres Données"

**Q: Les analyses sont lentes**
A: Réduire le nombre de lignes ou d'analyses simultanées

---

## 📂 Fichiers d'Exemple

Le dossier `CSV/` contient des exemples prêts à l'emploi.

Pour tester :
1. Utiliser les fichiers existants
2. L'interface les charge automatiquement
3. Vérifier le bon fonctionnement

Pour vos données :
1. Adapter votre CSV au format
2. Placer dans `CSV/`
3. Redémarrer l'application
