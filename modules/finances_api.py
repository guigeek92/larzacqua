"""
Module de récupération automatique des données financières pour la simulation de rentabilité d'une turbine hydroélectrique.

Ce module fournit des fonctions pour obtenir :
- Prix de l'électricité (€/kWh)
- Subventions publiques disponibles
- CAPEX et OPEX moyens sectoriels
- Taux d'intérêt ou coût du capital

Les données sont récupérées via des API publiques ou simulées si indisponibles.
"""
import requests
from typing import Dict, Any, Optional

class FinanceDataError(Exception):
    pass

def get_electricity_price(country_code: str = "FR") -> float:
    """
    Récupère le prix spot de l'électricité (€/kWh) via l'API ENTSO-E (exemple public, nécessite inscription pour clé API).
    Pour l'exemple, on utilise l'API EPEX Spot (prix day-ahead) via entsoe-py ou une valeur fictive.
    """
    # Exemple fictif (remplacer par appel API réel si clé disponible)
    try:
        # url = f"https://api.epexspot.com/marketdata/price?country={country_code}"
        # response = requests.get(url)
        # response.raise_for_status()
        # data = response.json()
        # return float(data["price_eur_per_kwh"])
        return 0.12  # Valeur fictive €/kWh
    except Exception as e:
        raise FinanceDataError(f"Erreur lors de la récupération du prix de l'électricité : {e}")

def get_public_subsidies(region: str = "FR") -> Dict[str, Any]:
    """
    Récupère les subventions publiques disponibles via une API (exemple fictif).
    """
    try:
        # url = f"https://api.banquedesterritoires.fr/subsidies?region={region}"
        # response = requests.get(url)
        # response.raise_for_status()
        # data = response.json()
        # return data
        return {
            "montant_max": 50000,
            "conditions": "Projet < 500 kW, dossier complet, région FR",
            "organisme": "Agence de l'eau"
        }
    except Exception as e:
        raise FinanceDataError(f"Erreur lors de la récupération des subventions : {e}")

def get_capex_opex_means(technology: str = "hydro") -> Dict[str, float]:
    """
    Récupère les CAPEX et OPEX moyens sectoriels via une API ou base de données (exemple fictif).
    """
    try:
        # url = f"https://api.energydata.org/capex_opex?tech={technology}"
        # response = requests.get(url)
        # response.raise_for_status()
        # data = response.json()
        # return {"capex": data["capex"], "opex": data["opex"]}
        return {"capex": 2500, "opex": 80}  # €/kW installé, €/kW/an
    except Exception as e:
        raise FinanceDataError(f"Erreur lors de la récupération des CAPEX/OPEX : {e}")

def get_interest_rate() -> float:
    """
    Récupère le taux d'intérêt ou coût du capital via une API bancaire (exemple fictif).
    """
    try:
        # url = "https://api.banque.fr/interest_rate"
        # response = requests.get(url)
        # response.raise_for_status()
        # data = response.json()
        # return float(data["interest_rate"])
        return 0.045  # 4.5% taux fictif
    except Exception as e:
        raise FinanceDataError(f"Erreur lors de la récupération du taux d'intérêt : {e}")

def get_financial_data(region: str = "FR", technology: str = "hydro") -> Dict[str, Any]:
    """
    Récupère toutes les données financières nécessaires à la simulation.
    """
    try:
        return {
            "electricity_price_eur_kwh": get_electricity_price(region),
            "public_subsidies": get_public_subsidies(region),
            "capex_opex": get_capex_opex_means(technology),
            "interest_rate": get_interest_rate(),
        }
    except FinanceDataError as e:
        return {"error": str(e)}

# Exemple d'usage
if __name__ == "__main__":
    data = get_financial_data(region="FR", technology="hydro")
    print("Données financières pour la simulation :")
    for k, v in data.items():
        print(f"{k}: {v}")
