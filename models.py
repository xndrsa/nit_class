from flask_sqlalchemy import SQLAlchemy
import requests
db = SQLAlchemy()

class NitClassification(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nit = db.Column(db.String(15), unique=True, nullable=False)
    nombre_emisor = db.Column(db.String(255), nullable=False)
    nombre_establecimiento = db.Column(db.String(255), nullable=False)
    categoria = db.Column(db.String(100), nullable=True)




HUGGINGFACE_API_URL = "https://api-inference.huggingface.co/models/facebook/bart-large-cnn"
HUGGINGFACE_API_KEY = "your_huggingface_api_key"

def search_online(nit, nombre_emisor, nombre_establecimiento):
    query = f"{nombre_emisor} {nombre_establecimiento} NIT {nit}"
    # Aquí puedes usar una API de búsqueda, como Bing Search API
    search_results = [
        f"Result for {query} from website A",
        f"Details about {query} found on website B",
        "Other information related to this business..."
    ]  # Simulación de resultados
    return search_results

def summarize_results(results):
    headers = {"Authorization": f"Bearer {HUGGINGFACE_API_KEY}"}
    text_to_summarize = " ".join(results)
    payload = {"inputs": text_to_summarize}
    response = requests.post(HUGGINGFACE_API_URL, headers=headers, json=payload)
    if response.status_code == 200:
        return response.json()[0]["summary_text"]
    else:
        return "No se pudo generar un resumen."

def handle_new_nit(nit, nombre_emisor, nombre_establecimiento):
    search_results = search_online(nit, nombre_emisor, nombre_establecimiento)
    summary = summarize_results(search_results)
    return summary
