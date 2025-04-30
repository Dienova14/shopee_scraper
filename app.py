from flask import Flask, render_template, request, send_file, redirect, url_for
from shopee_scraper import scrape_product
import threading, os
from datetime import datetime

app = Flask(__name__)
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

SESSION = {
    "driver": None,
    "product_url": None,
    "output_csv": None,
    "status_log": []
}

def log_to_session(msg):
    SESSION["status_log"].append(msg)
    print(msg)

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        product_url = request.form["product_url"]
        filename = f"shopee_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        output_path = os.path.join(OUTPUT_DIR, filename)

        SESSION["product_url"] = product_url
        SESSION["output_csv"] = output_path
        SESSION["status_log"].clear()

        from selenium import webdriver
        import undetected_chromedriver as uc
        options = uc.ChromeOptions()
        options.add_argument("--start-maximized")
        SESSION["driver"] = uc.Chrome(options=options)

        SESSION["driver"].get("https://shopee.co.id/")
        log_to_session("🌐 Buka Shopee - Silakan login manual dulu")
        return redirect(url_for("wait_login"))

    return render_template("index.html")

@app.route("/wait-login")
def wait_login():
    return render_template("wait_login.html", log=SESSION["status_log"])

@app.route("/start-scraping", methods = ["POST"])
def start_scraping():
    def scraping_thread():
        try:
            scrape_product(
                SESSION["product_url"],
                SESSION["output_csv"],
                log_func=log_to_session,
                driver=SESSION["driver"]
            )
        except Exception as e:
            log_to_session(f"❌ Error saat scraping: {str(e)}")

    t = threading.Thread(target=scraping_thread)
    t.start()
    return redirect(url_for("wait_result"))

@app.route("/wait-result")
def wait_result():
    return render_template("result.html", log=SESSION["status_log"])

@app.route("/download")
def download():
    filepath = os.path.abspath(SESSION["output_csv"])
    if not os.path.exists(filepath):
        return "❌ File belum tersedia atau gagal dibuat.", 404
    return send_file(filepath, as_attachment=True)

