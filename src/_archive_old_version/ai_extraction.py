# ================= IMPORTS ================= #

import os
import io
import json
from typing import List, Dict, Optional

import pandas as pd
from dotenv import load_dotenv
from groq import Groq

# ================= INIT ================= #

load_dotenv()

CSV_DIR = os.path.join(os.path.dirname(__file__), "..", "CSV")

# ================= RAG PIPELINE ================= #

class RAGPipeline:

    def __init__(self, model: str = "llama-3.1-8b-instant"):
        self.api_key = os.getenv("GROQ_API_KEY")

        if not self.api_key:
            raise RuntimeError("❌ GROQ_API_KEY manquante dans .env")

        self.client = Groq(api_key=self.api_key)
        self.model = model

        print(f"[INIT] Modèle Groq utilisé : {self.model}")

    # ================= PROMPT ================= #

    def build_prompt(
        self,
        question: str,
        data: dict,
        description: str = "",
        document_type: Optional[str] = None,
        conversation: Optional[List[Dict[str, str]]] = None,
    ) -> str:

        prompt = f"""
Tu es un expert en énergie.

Contexte :
Analyse de réseaux d'eau pour évaluer le potentiel hydroélectrique et photovoltaïque.

Description : {description}
Type : {document_type}

Données :
{json.dumps(data, ensure_ascii=False)[:3000]}

Question :
{question}
"""

        if conversation:
            prompt += "\n\nHistorique :"
            for turn in conversation:
                prompt += f"\nUtilisateur : {turn.get('user','')}"
                prompt += f"\nAssistant : {turn.get('assistant','')}"

        return prompt

    # ================= GROQ CALL ================= #

    def ask_groq(self, prompt: str) -> str:
        """
        Appel Groq avec streaming (openai/gpt-oss-120b)
        Compatible terminal et facilement adaptable Streamlit
        """

        full_response = ""

        try:
            completion = self.client.chat.completions.create(
                model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": "Tu es un expert en énergie."},
                {"role": "user", "content": prompt}
            ],
            temperature=1,
            max_completion_tokens=8192,
            top_p=1,
            reasoning_effort="medium",
            stream=True,
        )

        for chunk in completion:
            content = chunk.choices[0].delta.content

            if content:
                print(content, end="", flush=True)  # affichage live terminal
                full_response += content

        print()  # retour ligne propre

        return full_response.strip()

    except Exception as e:
        return f"❌ Erreur Groq : {e}"

    # ================= QA ================= #

    def answer_question_from_extracted_data(
        self,
        question: str,
        result_json: dict,
        description: str = "",
        document_type: Optional[str] = None,
        conversation: Optional[List[Dict[str, str]]] = None,
    ) -> str:

        print(f"[Chatbot] Question : {question}")
        print(f"[Chatbot] Taille JSON : {len(result_json) if result_json else 0}")

        prompt = self.build_prompt(
            question,
            result_json,
            description,
            document_type,
            conversation,
        )

        response = self.ask_groq(prompt)

        print(f"[Chatbot] Réponse générée")

        return response

    # ================= CSV ================= #

    def extract_from_csv(self, csv_bytes, filename=None):
        try:
            df = pd.read_csv(io.BytesIO(csv_bytes))

            document_type = (
                "udi" if "udi" in df.columns else
                "steu" if "steu" in df.columns else
                "unknown"
            )

            print(f"[CSV] Chargé : {filename} | shape={df.shape}")

            return {
                "document_type": document_type,
                "description": "CSV analysé",
                "json": df.to_dict(orient="records"),
                "debug": {
                    "filename": filename,
                    "shape": df.shape,
                    "columns": list(df.columns),
                },
            }

        except Exception as e:
            return {"error": str(e)}


# ================= DATA EXTRACTION ================= #

def extract_pressure_organs_with_scores() -> List[Dict]:
    path = os.path.join(CSV_DIR, "aep_organe_pression.csv")
    df = pd.read_csv(path)

    results = []

    for row in df.to_dict(orient="records"):

        debit = float(row.get("DEBIT_MOYEN") or 0)
        pres_amont = float(row.get("PRES_AMONT") or 0)
        pres_aval = float(row.get("PRESS_AVAL") or 0)

        delta_p = pres_amont - pres_aval
        volume = float(row.get("VOLUME") or 0)
        diametre = float(row.get("DIAMETRE") or 0)

        if debit > 0:
            score = 0.35 * delta_p + 0.25 * debit + 0.2 * volume + 0.2 * diametre
        else:
            score = 0.45 * delta_p + 0.25 * volume + 0.3 * diametre

        enriched = dict(row)
        enriched["score_hydro"] = round(score, 2)

        results.append(enriched)

    print(f"[DATA] Nombre d'organes extraits : {len(results)}")

    return results


# ================= TEST LOCAL ================= #

if __name__ == "__main__":

    # Initialisation
    pipeline = RAGPipeline()

    # Extraction données
    data = extract_pressure_organs_with_scores()

    # Question test
    question = "Quels sont les meilleurs sites pour produire de l'hydroélectricité ?"

    # Appel IA
    response = pipeline.answer_question_from_extracted_data(
        question=question,
        result_json=data
    )

    print("\n===== RÉPONSE =====\n")
    print(response)
    