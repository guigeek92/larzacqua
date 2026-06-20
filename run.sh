#!/bin/bash
# Lancer l'interface SimuWatter sur Linux/Mac

if [ ! -d ".venv" ]; then
    echo ""
    echo "ERREUR: Environnement virtuel non trouvé !"
    echo "Veuillez d'abord exécuter ./setup.sh"
    echo ""
    exit 1
fi

# Activer l'environnement virtuel
source .venv/bin/activate

# Lancer Streamlit
echo ""
echo "Démarrage de SimuWatter sur http://localhost:8501 (hydro)"
echo "Démarrage de SimuWatter PV sur http://localhost:8502 (photovoltaïque)"
echo "Appuyez sur Ctrl+C pour arrêter les applications"
echo ""
python -m streamlit run app/streamlit_pv.py --server.port 8502 >/dev/null 2>&1 &
python -m streamlit run app/streamlit_resume.py --server.port 8501
