# scraper.py
import time, csv, json, os
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import ElementClickInterceptedException
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

def scrape_product(product_url, output_csv_path, log_func=print, driver=None):
    REVIEW_BUFFER = []
    BUFFER_SIZE = 6

    if driver is None:
        options = Options()
        options.add_argument("--start-maximized")
        
        # path lokal ke chromedriver
        path = os.path.join(os.path.dirname(__file__), "chromedriver.exe")
        service = Service(executable_path=path)

        driver = webdriver.Chrome(service=service, options=options)


    try:
        log_func("✅ Lanjut scraping... menggunakan session yang sudah login manual.")
        driver.get(product_url)
        log_func(f"🔗 Membuka: {product_url}")

        # ⬇️ Scroll agar review section terlihat
        try:
            review_section = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "product-ratings__list"))
            )
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'})", review_section)
            time.sleep(2)
            log_func("👀 Review section berhasil discroll agar terlihat.")
        except:
            log_func("⚠️ Gagal menemukan section review di awal.")

        # ⬇️ Klik tombol filter 'dengan komentar'
        try:
            filter_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH,
                    '//div[contains(@class, "product-rating-overview__filter") and contains(text(), "komentar")]'))
            )
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", filter_button)
            time.sleep(1)
            try:
                filter_button.click()
            except ElementClickInterceptedException:
                driver.execute_script("arguments[0].click();", filter_button)
            log_func("✅ Klik filter 'dengan komentar' berhasil.")
            time.sleep(2)
        except Exception as e:
            log_func(f"⚠️ Gagal klik filter komentar: {e}")

        def scroll_review_section():
            try:
                section = driver.find_element(By.CLASS_NAME, "product-ratings__list")
                last_height = driver.execute_script("return arguments[0].scrollHeight", section)
                for _ in range(5):
                    driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight", section)
                    time.sleep(1)
                    new_height = driver.execute_script("return arguments[0].scrollHeight", section)
                    if new_height == last_height:
                        break
                    last_height = new_height
                log_func("🔃 Scrolling review section penuh.")
            except:
                log_func("⚠️ Gagal scroll review section.")

        def wait_reviews():
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "shopee-product-rating__main"))
                )
                scroll_review_section()
                return True
            except:
                return False

        def scrape_reviews(page_number):
            reviews = driver.find_elements(By.CLASS_NAME, "shopee-product-rating__main")
            data = []

            for review in reviews:
                try:
                    reviewer = review.find_element(By.CSS_SELECTOR, ".shopee-product-rating__author-name").text.strip()
                except:
                    reviewer = "Nama tidak ditemukan"

                try:
                    rating = len(review.find_elements(By.CSS_SELECTOR, ".shopee-product-rating__rating svg.icon-rating-solid--active"))
                except:
                    rating = "-"

                try:
                    date = review.find_element(By.CLASS_NAME, "shopee-product-rating__time").text.strip()
                except:
                    date = "-"

                attributes = {}
                free_text_lines = []

                try:
                    desc_container = review.find_element(By.XPATH, './/div[contains(@style, "white-space: pre-wrap")]')
                    raw_lines = desc_container.text.strip().split("\n")

                    for line in raw_lines:
                        if ":" in line:
                            label, value = line.split(":", 1)
                            attributes[label.strip()] = value.strip()
                        else:
                            free_text_lines.append(line.strip())

                    text = " ".join(free_text_lines).strip()
                except:
                    text = "-"
                    attributes = {}

                data.append({
                    "Page": page_number,
                    "Nama Reviewer": reviewer,
                    "Rating": rating,
                    "Tanggal Review": date,
                    "Isi Review": text,
                    "Atribut Review": json.dumps(attributes, ensure_ascii=False)
                })

            return data

        def klik_next(last_hash):
            try:
                if len(driver.window_handles) == 0:
                    log_func("🛑 Jendela Chrome ditutup.")
                    return False

                next_btn = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "button.shopee-icon-button.shopee-icon-button--right"))
                )

                # ⛔ Cek apakah tombol tidak aktif (dengan class)
                if "shopee-icon-button--disabled" in next_btn.get_attribute("class") or not next_btn.is_enabled():
                    log_func("🚫 Tombol Next terdeteksi nonaktif berdasarkan class.")
                    return False

                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_btn)
                time.sleep(0.5)

                try:
                    next_btn.click()
                except ElementClickInterceptedException:
                    driver.execute_script("arguments[0].click();", next_btn)

                log_func("➡️ Klik tombol Next berhasil")
                time.sleep(2)
                scroll_review_section()
                time.sleep(1)

                reviews = driver.find_elements(By.CLASS_NAME, "shopee-product-rating__main")
                if not reviews:
                    log_func("⚠️ Tidak ada review setelah klik Next. Stop.")
                    return False

                new_hash = hash("".join([r.text for r in reviews[:2]])[:300])
                if new_hash == last_hash:
                    log_func("🛑 Review tetap sama setelah klik Next. Halaman terakhir.")
                    return False

                return new_hash

            except Exception as e:
                log_func(f"⚠️ Gagal klik Next: {e}")
                return False

        # ========== MAIN LOOP ========== #
        page = 1
        last_hash = 0
        all_reviews = []
        all_attribute_keys = set()

        while True:
            try:
                from app import SESSION
                if SESSION.get("stop"):
                    log_func("🛑 Scraping dihentikan manual dari UI.")
                    break
            except:
                pass

            log_func(f"📄 Scraping halaman {page}...")
            if not wait_reviews():
                break

            reviews = scrape_reviews(page)
            reviews = scrape_reviews(page)
            if not reviews:
                log_func("⚠️ Tidak ada review ditemukan.")
                break

            # 🚨 Deteksi duplikat berdasarkan isi review
            review_texts = ["|".join([r.get("Isi Review", ""), r.get("Nama Reviewer", "")]) for r in reviews]

            if review_texts in REVIEW_BUFFER:
                log_func("🛑 Deteksi data duplikat (review tidak berubah). Stop scraping.")
                break

            REVIEW_BUFFER.append(review_texts)
            if len(REVIEW_BUFFER) > BUFFER_SIZE:
                REVIEW_BUFFER.pop(0)


            for review in reviews:
                attr_dict = json.loads(review.pop("Atribut Review", "{}"))
                all_attribute_keys.update(attr_dict.keys())
                review["__attributes__"] = attr_dict
            all_reviews.extend(reviews)

            review_hash = hash("".join([r["Isi Review"] for r in reviews[:2]])[:300])
            next_result = klik_next(review_hash)
            if not next_result:
                break
            last_hash = next_result
            page += 1

        # ✅ Tulis ke CSV
        final_rows = []
        for r in all_reviews:
            row = {k: r[k] for k in r if k != "__attributes__"}
            for key in all_attribute_keys:
                row[key] = r["__attributes__"].get(key, "-")
            final_rows.append(row)

        if final_rows:
            with open(output_csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, final_rows[0].keys())
                writer.writeheader()
                writer.writerows(final_rows)

        log_func(f"✅ Selesai! Total review tersimpan: {len(final_rows)}")

    finally:
        try:
            driver.quit()
        except Exception as e:
            log_func(f"⚠️ Gagal menutup browser: {e}")
