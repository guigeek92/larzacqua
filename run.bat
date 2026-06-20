@echo off
REM Lancer l'interface SimuWatter sur Windows
REM Assurez-vous d'avoir exécuté setup.bat avant

if not exist ".venv\" (
    echo.
    echo ERREUR: Environnement virtuel non trouvé !
    echo Veuillez d'abord executer setup.bat
    echo.
    pause
    exit /b 1
)

REM Activer l'environnement virtuel
call .venv\Scripts\activate.bat

REM Lancer Streamlit
echo.
echo Demarrage de SimuWatter sur http://localhost:8501 (hydro)
echo Demarrage de SimuWatter PV sur http://localhost:8502 (photovoltaique)
echo Appuyez sur Ctrl+C pour arreter les applications
echo.
start "SimuWatter PV" cmd /c "python -m streamlit run app/streamlit_pv.py --server.port 8502"
python -m streamlit run app/streamlit_resume.py --server.port 8501

pause
