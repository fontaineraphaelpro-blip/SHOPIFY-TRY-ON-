import os
import time
import replicate
from flask import Flask, render_template, request, jsonify, abort
from werkzeug.utils import secure_filename

# --- CONFIGURATION STRUCTURE PLATE (RENDER) ---
# template_folder='.' : Cherche index.html à la racine
# static_folder='.'   : Cherche styles.css et app.js à la racine
# static_url_path=''  : Permet d'appeler /styles.css directement
app = Flask(__name__, template_folder='.', static_folder='.', static_url_path='')

# Configuration des uploads
# Render a un disque éphémère, ce dossier sera vidé à chaque redémarrage (ce qui est bien pour la privacy)
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Max 16MB

# Création du dossier au lancement
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Base de données simulée (en mémoire)
db = {
    "credits": 15,
    "settings": {
        "button_text": "Try It On Now ✨",
        "button_color": "#000000",
        "text_color": "#ffffff",
        "limit": 5
    }
}

# --- SÉCURITÉ ---
# Empêche le téléchargement de tes fichiers sensibles via le navigateur
@app.route('/main.py')
@app.route('/requirements.txt')
@app.route('/shopify.app.toml')
@app.route('/.env')
def block_sensitive_files():
    abort(403)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- ROUTES ---

@app.route('/')
def index():
    # On sert le fichier index.html qui est à la racine
    return render_template('index.html', api_key="demo_key_123")

@app.route('/api/stats', methods=['GET'])
def get_stats():
    return jsonify(db)

@app.route('/api/save-settings', methods=['POST'])
def save_settings():
    data = request.json
    db['settings'] = data
    return jsonify({"status": "success", "message": "Settings saved!"})

@app.route('/api/buy-credits', methods=['POST'])
def buy_credits():
    amount = request.json.get('amount', 0)
    db['credits'] += int(amount)
    return jsonify({"status": "success", "new_balance": db['credits']})

@app.route('/generate', methods=['POST'])
def generate_vton():
    # 1. Vérification des crédits
    if db['credits'] <= 0:
        return jsonify({"error": "No credits left. Please recharge."}), 402

    # 2. Vérification de la configuration API
    if not os.environ.get("REPLICATE_API_TOKEN"):
        # Log pour le dashboard Render
        print("ERREUR CRITIQUE: La variable REPLICATE_API_TOKEN est absente.")
        return jsonify({"error": "Server configuration error (API Token missing)"}), 500

    # 3. Vérification des images
    if 'human_img' not in request.files or 'cloth_img' not in request.files:
        return jsonify({"error": "Missing images"}), 400

    u_file = request.files['human_img']
    c_file = request.files['cloth_img']

    if u_file and c_file:
        try:
            # A. Sauvegarde temporaire sur le serveur Render
            u_filename = secure_filename(f"human_{int(time.time())}.jpg")
            c_filename = secure_filename(f"cloth_{int(time.time())}.jpg")
            
            u_path = os.path.join(app.config['UPLOAD_FOLDER'], u_filename)
            c_path = os.path.join(app.config['UPLOAD_FOLDER'], c_filename)
            
            u_file.save(u_path)
            c_file.save(c_path)

            print(f"🚀 Envoi vers Replicate (IDM-VTON)...")

            # B. Appel à l'IA via la librairie officielle replicate
            # Note: On ouvre les fichiers en mode 'rb' (read binary)
            output = replicate.run(
                "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985",
                input={
                    "human_img": open(u_path, "rb"),
                    "garm_img": open(c_path, "rb"),
                    "garment_des": "fashion garment", # Description facultative mais aide parfois
                    "category": "upper_body",         # Force le haut du corps pour de meilleurs résultats
                    "crop": False,
                    "seed": 42,
                    "steps": 30
                }
            )

            print(f"✅ Succès Replicate: {output}")

            # Replicate renvoie l'URL de l'image hébergée chez eux
            result_url = str(output)
            
            # C. Déduction crédit
            db['credits'] -= 1
            
            # D. Nettoyage (Optionnel, Render le fait au redémarrage, mais c'est propre de le faire)
            try:
                os.remove(u_path)
                os.remove(c_path)
            except:
                pass

            return jsonify({
                "status": "success",
                "result_url": result_url,
                "credits_remaining": db['credits']
            })

        except replicate.exceptions.ReplicateError as e:
            print(f"❌ Erreur API Replicate: {e}")
            return jsonify({"error": "AI Processing failed (NSFW content or API error)"}), 500
        except Exception as e:
            print(f"❌ Erreur Serveur: {e}")
            return jsonify({"error": str(e)}), 500

    return jsonify({"error": "Upload failed"}), 500

if __name__ == '__main__':
    # Le debug est True pour tes tests locaux, mais Gunicorn l'ignorera sur Render (c'est normal)
    app.run(debug=True, port=5000)
