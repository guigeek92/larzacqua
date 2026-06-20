#!/usr/bin/env python3
"""
Script de Création d'Archive Livrable - SimuWatter

Crée une archive ZIP du projet, en excluant tous les fichiers sensibles
et les répertoires non nécessaires pour le client.

Usage:
    python create_delivery_archive.py
"""

import os
import shutil
import sys
from pathlib import Path
from datetime import datetime

def should_exclude(path):
    """Déterminer si un chemin doit être exclu."""
    # Fichiers et dossiers à exclure
    exclude_patterns = [
        '.env',
        '.git',
        '.venv',
        'venv',
        '__pycache__',
        '.pytest_cache',
        '.vscode',
        '.idea',
        '*.pyc',
        '*.pyo',
        '*.egg-info',
        '.coverage',
        '*.swp',
        '*.swo',
        '.DS_Store',
        'Thumbs.db',
        '.streamlit/secrets.toml',
        'data/runs',
        'outputs',
    ]
    
    # Convertir en objet Path pour comparer
    p = Path(path)
    
    for pattern in exclude_patterns:
        if '*' in pattern:
            # Patterns avec wildcards
            import fnmatch
            if fnmatch.fnmatch(str(p), pattern):
                return True
        else:
            # Comparaison de fichier/dossier exact
            if p.name == pattern or str(p).endswith(pattern):
                return True
    
    return False

def create_archive():
    """Créer l'archive du livrable."""
    print("\n" + "="*60)
    print("CRÉATION ARCHIVE LIVRABLE - SimuWatter")
    print("="*60 + "\n")
    
    # Générer le nom de l'archive
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive_name = f"SimuWatter_Livrable_{timestamp}"
    archive_path = f"{archive_name}.zip"
    
    # Vérifier les fichiers sensibles
    if Path(".env").exists():
        with open(".env") as f:
            content = f.read()
            if 'gsk_' in content or 'hf_' in content:
                print("❌ ERREUR: Fichier .env contient des clés réelles!")
                print("   Supprimez .env ou utilisez un template avant l'archive")
                return False
    
    if Path(".git").exists():
        print("⚠️  Dossier .git détecté - sera exclu")
    
    if Path(".venv").exists():
        print("⚠️  Dossier .venv détecté - sera exclu")
    
    print(f"\nCréation de l'archive: {archive_path}")
    print("(Cela peut prendre quelques secondes...)\n")
    
    try:
        # Créer l'archive
        shutil.make_archive(
            archive_name,
            'zip',
            root_dir='.',
            ignore=lambda dir, files: [
                f for f in files 
                if should_exclude(os.path.join(dir, f))
            ]
        )
        
        # Vérifier la taille
        size_mb = Path(archive_path).stat().st_size / (1024 * 1024)
        
        print(f"✅ Archive créée avec succès!")
        print(f"   Fichier: {archive_path}")
        print(f"   Taille: {size_mb:.1f} MB")
        
        print("\n📋 Contenu de l'archive:")
        print("   ✓ Code source (app/, modules/, src/)")
        print("   ✓ Données (CSV/)")
        print("   ✓ Documentation (README.md, guides...)")
        print("   ✓ Scripts (setup.bat, setup.sh, run.bat, run.sh)")
        print("   ✓ Configuration (.env.example, .streamlit/)")
        print("   ✓ Tests (tests/)")
        
        print("\n❌ Exclu de l'archive:")
        print("   ✗ .env (clés API)")
        print("   ✗ .git/ (historique git)")
        print("   ✗ .venv/ (environnement virtuel)")
        print("   ✗ __pycache__/ (cache Python)")
        print("   ✗ .pytest_cache/ (cache tests)")
        print("   ✗ Fichiers temporaires")
        
        print("\n" + "="*60)
        print("PROCHAINES ÉTAPES:")
        print("="*60)
        print(f"1. Vérifier l'archive: {archive_path}")
        print("2. Transmettre au client")
        print("3. Le client extrait et exécute setup.bat/setup.sh")
        print("="*60 + "\n")
        
        return True
        
    except Exception as e:
        print(f"❌ Erreur lors de la création de l'archive: {e}")
        return False

def verify_before_archive():
    """Vérifier les conditions avant création de l'archive."""
    print("\n📋 Vérification pré-archive...\n")
    
    checks = {
        "README.md": "Documentation principale",
        "INSTALLATION.md": "Guide installation",
        "QUICKSTART.md": "Démarrage rapide",
        ".env.example": "Template variables",
        "setup.bat": "Script installation Windows",
        "setup.sh": "Script installation Linux",
        "run.bat": "Script lancement Windows",
        "run.sh": "Script lancement Linux",
        "requirements.txt": "Dépendances Python",
    }
    
    all_ok = True
    for file, desc in checks.items():
        if Path(file).exists():
            print(f"✓ {file:30} ({desc})")
        else:
            print(f"✗ {file:30} - MANQUANT!")
            all_ok = False
    
    return all_ok

def main():
    """Exécuter le script."""
    # Vérifications préalables
    if not verify_before_archive():
        print("\n❌ Des fichiers essentiels manquent!")
        print("Assurez-vous que tous les fichiers de documentation existent.")
        return 1
    
    # Créer l'archive
    if create_archive():
        return 0
    else:
        return 1

if __name__ == "__main__":
    sys.exit(main())
