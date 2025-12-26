import os
import time
import replicate
from flask import Flask, render_template, request, jsonify, abort
from werkzeug.utils import secure_filename

# --- CONFIGURATION STRUCTURE PLATE ---
app = Flask(__name__, template_folder='.', static_folder='.', static_url_path='')

# Configuration des uploads
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Base de données simulée
db = {
    "credits": 15,
    "settings": {
        "button_text": "Try It On Now ✨",
        "button_color": "#000000",
        "text_color": "#ffffff",
        "limit": 5
    }
}

# --- SÉCURITÉ FICHIERS ---
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

    # 2. Vérification de la clé API Replicate
    if not os.environ.get("REPLICATE_API_TOKEN"):
        print("ERREUR: La variable d'environnement REPLICATE_API_TOKEN est manquante.")
        return jsonify({"error": "Server configuration error (API Token missing)"}), 500

    # 3. Vérification des fichiers
    if 'human_img' not in request.files or 'cloth_img' not in request.files:
        return jsonify({"error": "Missing images"}), 400

    u_file = request.files['human_img']
    c_file = request.files['cloth_img']

    if u_file and c_file:
        try:
            # A. Sauvegarde locale temporaire
            u_filename = secure_filename(f"human_{int(time.time())}.jpg")
            c_filename = secure_filename(f"cloth_{int(time.time())}.jpg")
            
            u_path = os.path.join(app.config['UPLOAD_FOLDER'], u_filename)
            c_path = os.path.join(app.config['UPLOAD_FOLDER'], c_filename)
            
            u_file.save(u_path)
            c_file.save(c_path)

            # B. Appel à Replicate (IDM-VTON)
            # On ouvre les fichiers en mode binaire pour les envoyer
            print(f"🚀 Envoi à Replicate: {u_filename} + {c_filename}...")
            
            output = replicate.run(
                "cuuupid/idm-vton:0513734a452173b8173e907e3a59d19a36266e55b48528559432bd21c7d7e985",
                input={
                    "human_img": open(u_path, "rb"),
                    "garm_img": open(c_path, "rb"),
                    "garment_des": "fashion garment", # Description générique, le modèle gère bien sans
                    "category": "upper_body",         # Par défaut "upper_body", peut être "lower_body" ou "dresses"
                    "crop": False,
                    "seed": 42,
                    "steps": 30
                }
            )

            print(f"✅ Résultat reçu: {output}")

            # Le modèle renvoie généralement l'URL de l'image (parfois dans une liste)
            # L'URL est hébergée chez Replicate, on peut l'utiliser directement.
            result_url = str(output)
            
            # C. Mise à jour des crédits
            db['credits'] -= 1
            
            return jsonify({
                "status": "success",
                "result_url": result_url,
                "credits_remaining": db['credits']
            })

        except replicate.exceptions.ReplicateError as e:
            print(f"❌ Erreur Replicate: {e}")
            return jsonify({"error": "AI Processing failed (NSFW filter or timeout)"}), 500
        except Exception as e:
            print(f"❌ Erreur Serveur: {e}")
            return jsonify({"error": str(e)}), 500

    return jsonify({"error": "Upload failed"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
