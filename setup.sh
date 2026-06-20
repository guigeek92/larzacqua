#!/bin/bash
# Script d'installation pour SimuWatter sur Linux/Mac

echo ""
echo "====================================="
echo "Installation de SimuWatter"
echo "====================================="
echo ""

# Vérifier Python
if ! command -v python3 &> /dev/null; then
    echo "ERREUR: Python 3 n'est pas installé"
    echo "Veuillez installer Python 3.10 ou supérieur"
    echo ""
    exit 1
fi

echo "[OK] Python détecté"

# Créer l'environnement virtuel
if [ ! -d ".venv" ]; then
    echo "Création de l'environnement virtuel..."
    python3 -m venv .venv
    echo "[OK] Environnement virtuel créé"
else
    echo "[OK] Environnement virtuel existe déjà"
fi

# Activer l'environnement virtuel
source .venv/bin/activate
echo "[OK] Environnement virtuel activé"

# Mettre à jour pip
echo "Mise à jour de pip..."
python -m pip install --upgrade pip > /dev/null 2>&1
echo "[OK] pip mis à jour"

# Installer les dépendances
echo "Installation des dépendances..."
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "ERREUR lors de l'installation des dépendances"
    echo ""
    exit 1
fi
echo "[OK] Dépendances installées"

# Vérifier et copier .env.example si .env n'existe pas
if [ ! -f ".env" ]; then
    echo ""
    echo "ATTENTION: Fichier .env non trouvé !"
    echo "Copie de .env.example en .env"
    cp .env.example .env
    echo ""
    echo "[!] Veuillez éditer le fichier .env et ajouter vos clés API :"
    echo "    - GROQ_API_KEY (obligatoire pour les analyses IA)"
    echo "    - HF_TOKEN (optionnel)"
    echo ""
else
    echo "[OK] Fichier .env existe"
fi

echo ""
echo "====================================="
echo "Installation terminée !"
echo "====================================="
echo ""
echo "Pour démarrer l'application, exécutez :"
echo "  ./run.sh"
echo ""
