@echo off
REM Script d'installation pour SimuWatter sur Windows

echo.
echo =====================================
echo Installation de SimuWatter
echo =====================================
echo.

REM Verifier Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERREUR: Python n'est pas installe ou n'est pas dans le PATH
    echo Veuillez installer Python 3.10 ou superieur depuis https://www.python.org
    echo.
    pause
    exit /b 1
)

echo [OK] Python detecte

REM Creer l'environnement virtuel
if not exist ".venv" (
    echo Création de l'environnement virtuel...
    python -m venv .venv
    echo [OK] Environnement virtuel cree
) else (
    echo [OK] Environnement virtuel existe deja
)

REM Activer l'environnement virtuel
call .venv\Scripts\activate.bat
echo [OK] Environnement virtuel active

REM Mettre a jour pip
echo Mise a jour de pip...
python -m pip install --upgrade pip >nul 2>&1
echo [OK] pip mis a jour

REM Installer les dependances
echo Installation des dependances...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERREUR lors de l'installation des dependances
    echo.
    pause
    exit /b 1
)
echo [OK] Dependances installes

REM Verifier et copier .env.example si .env n'existe pas
if not exist ".env" (
    echo.
    echo ATTENTION: Fichier .env non trouve !
    echo Copie de .env.example en .env
    copy .env.example .env
    echo.
    echo [!] Veuillez editer le fichier .env et ajouter vos cles API :
    echo     - GROQ_API_KEY (obligatoire pour les analyses IA)
    echo     - HF_TOKEN (optionnel)
    echo.
) else (
    echo [OK] Fichier .env existe
)

echo.
echo =====================================
echo Installation terminee !
echo =====================================
echo.
echo Pour demarrer l'application, executez :
echo   run.bat
echo.
pause
