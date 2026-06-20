#!/usr/bin/env python3
"""
Script de Vérification Pré-Livraison - SimuWatter

Vérifie que tous les fichiers nécessaires sont présents et corrects
avant la livraison au client.

Usage:
    python verify_delivery.py
"""

import os
import sys
from pathlib import Path

def check_file_exists(path, name):
    """Vérifier qu'un fichier existe."""
    if Path(path).exists():
        print(f"✓ {name}")
        return True
    else:
        print(f"✗ {name} - MANQUANT")
        return False

def check_file_not_exists(path, name):
    """Vérifier qu'un fichier N'existe PAS (sensibilité)."""
    if not Path(path).exists():
        print(f"✓ {name} (non inclus)")
        return True
    else:
        print(f"✗ {name} - PRÉSENT (PROBLÈME DE SÉCURITÉ!)")
        return False

def check_directory_exists(path, name):
    """Vérifier qu'un dossier existe."""
    if Path(path).is_dir():
        print(f"✓ {name}/")
        return True
    else:
        print(f"✗ {name}/ - MANQUANT")
        return False

def verify_env_file():
    """Vérifier le fichier .env."""
    env_path = Path(".env")
    env_example_path = Path(".env.example")
    
    # .env ne doit PAS exister (ou doit être vide/template)
    if env_path.exists():
        with open(env_path, 'r') as f:
            content = f.read()
            if 'your_' in content or 'example' in content.lower():
                print("⚠ .env existe mais semble être un template (OK)")
                return True
            elif 'gsk_' in content or 'hf_' in content:
                print("✗ .env contient des clés réelles - DANGER DE SÉCURITÉ!")
                return False
    
    # .env.example doit exister
    if env_example_path.exists():
        print("✓ .env.example (template)")
        return True
    else:
        print("✗ .env.example - MANQUANT")
        return False

def main():
    """Exécuter la vérification."""
    print("\n" + "="*50)
    print("VÉRIFICATION PRÉ-LIVRAISON - SimuWatter")
    print("="*50 + "\n")
    
    checks = []
    
    # Documentation
    print("📚 Documentation:")
    checks.append(check_file_exists("README.md", "README.md"))
    checks.append(check_file_exists("QUICKSTART.md", "QUICKSTART.md"))
    checks.append(check_file_exists("INSTALLATION.md", "INSTALLATION.md"))
    checks.append(check_file_exists("DATA_INTEGRATION.md", "DATA_INTEGRATION.md"))
    checks.append(check_file_exists("MAINTENANCE.md", "MAINTENANCE.md"))
    checks.append(check_file_exists("EXPORT.md", "EXPORT.md"))
    checks.append(check_file_exists("DELIVERY_CHECKLIST.md", "DELIVERY_CHECKLIST.md"))
    
    # Scripts
    print("\n🔧 Scripts de Lancement:")
    checks.append(check_file_exists("setup.bat", "setup.bat"))
    checks.append(check_file_exists("setup.sh", "setup.sh"))
    checks.append(check_file_exists("run.bat", "run.bat"))
    checks.append(check_file_exists("run.sh", "run.sh"))
    
    # Configuration
    print("\n⚙️ Configuration:")
    checks.append(check_file_exists("requirements.txt", "requirements.txt"))
    checks.append(check_file_exists(".env.example", ".env.example"))
    checks.append(check_file_exists(".streamlit/config.toml", ".streamlit/config.toml"))
    checks.append(check_file_exists(".gitignore", ".gitignore"))
    
    # Répertoires
    print("\n📂 Répertoires Essentiels:")
    checks.append(check_directory_exists("app", "app"))
    checks.append(check_directory_exists("modules", "modules"))
    checks.append(check_directory_exists("CSV", "CSV"))
    checks.append(check_directory_exists("templates", "templates"))
    checks.append(check_directory_exists("tests", "tests"))
    
    # Sécurité
    print("\n🔐 Vérification Sécurité:")
    checks.append(check_file_not_exists(".env", ".env (vrai fichier)"))
    checks.append(check_file_not_exists(".git", ".git"))
    checks.append(check_file_not_exists(".venv", ".venv"))
    checks.append(verify_env_file())
    
    # Résumé
    print("\n" + "="*50)
    passed = sum(checks)
    total = len(checks)
    percentage = (passed / total * 100) if total > 0 else 0
    
    print(f"Résultat: {passed}/{total} vérifications ✓ ({percentage:.0f}%)")
    
    if passed == total:
        print("\n✅ PRÊT POUR LA LIVRAISON!")
        print("="*50 + "\n")
        return 0
    else:
        print("\n❌ PROBLÈMES DÉTECTÉS - À CORRIGER AVANT LIVRAISON")
        print("="*50 + "\n")
        return 1

if __name__ == "__main__":
    sys.exit(main())
