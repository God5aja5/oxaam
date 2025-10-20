from flask import Flask, jsonify, request
import asyncio
import random
import string
import json
import subprocess
import re
import os
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
import threading
import time

app = Flask(__name__)

# Ensure Chromium is installed on startup
def ensure_browser_installed():
    """Install Chromium browser if not already installed"""
    try:
        print("🔍 Checking for Chromium installation...")
        result = subprocess.run(
            ["python", "-m", "playwright", "install", "chromium"],
            capture_output=True,
            text=True,
            timeout=300,
            env={**os.environ, "PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS": "true"}
        )
        if "downloaded" in result.stdout.lower() or "installed" in result.stdout.lower():
            print("✅ Chromium installed successfully")
        else:
            print("✅ Chromium already installed")
    except Exception as e:
        print(f"⚠️ Browser check failed: {e}")

# Install browser on startup
ensure_browser_installed()

# Global state for tracking scraping status
scraping_state = {
    "is_running": False,
    "last_run": None,
    "status": "idle",
    "accounts": [],
    "error": None,
    "session_id": None
}

class OxaamAutomation:
    def __init__(self, headless=True, save_results=False):
        self.base_url = "https://www.oxaam.com/"
        self.headless = headless
        self.save_results = save_results
        self.account_credentials = {
            "oxaam_email": "",
            "oxaam_password": "",
            "oxaam_phone": "",
            "created_at": ""
        }
        self.free_accounts = []
        self.session_id = self.generate_session_id()
        self.catbox_url = ""
    
    def generate_session_id(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        return f"session_{timestamp}_{random_suffix}"
    
    def generate_random_phone(self):
        random_digits = ''.join([str(random.randint(0, 9)) for _ in range(9)])
        return f"869{random_digits}"
    
    def generate_random_email(self):
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        random_string = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
        return f"user_{timestamp}_{random_string}@gmail.com"
    
    def generate_random_name(self):
        first_names = ["John", "Jane", "Mike", "Sarah", "David", "Emma", "Chris", "Lisa", 
                       "Alex", "Maria", "Ryan", "Sophie", "Tom", "Anna", "Jack", "Emily"]
        last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", 
                      "Davis", "Rodriguez", "Martinez", "Wilson", "Anderson", "Taylor"]
        return f"{random.choice(first_names)} {random.choice(last_names)}"
    
    def generate_strong_password(self):
        length = random.randint(12, 16)
        chars = string.ascii_letters + string.digits + "!@#$%^&*"
        password = ''.join(random.choices(chars, k=length))
        if not any(c.isupper() for c in password):
            password = password[:-1] + random.choice(string.ascii_uppercase)
        if not any(c.isdigit() for c in password):
            password = password[:-1] + random.choice(string.digits)
        return password
    
    def upload_to_catbox(self, html_content, description="debug"):
        try:
            print(f"📤 Uploading {description} HTML to catbox.moe...")
            temp_filename = f"oxaam_{description}_{self.session_id}.html"
            temp_path = Path(temp_filename)
            
            with open(temp_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            result = subprocess.run(
                [
                    'curl', '-s', '-F', 'reqtype=fileupload',
                    '-F', f'fileToUpload=@{temp_filename}',
                    'https://catbox.moe/user/api.php'
                ],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            temp_path.unlink(missing_ok=True)
            
            if result.returncode == 0 and result.stdout:
                url = result.stdout.strip()
                if url.startswith('http'):
                    print(f"✅ Upload successful: {url}")
                    return url
            return None
                
        except Exception as e:
            print(f"❌ Upload error: {str(e)}")
            return None
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except:
                pass
    
    def extract_credentials_from_html(self, html_content):
        print("🔍 Extracting credentials from HTML...")
        accounts = []
        
        details_pattern = r'<details[^>]*>(.*?)</details>'
        details_blocks = re.findall(details_pattern, html_content, re.DOTALL | re.IGNORECASE)
        
        print(f"📦 Found {len(details_blocks)} service blocks")
        
        for idx, block in enumerate(details_blocks, 1):
            try:
                service_name_match = re.search(r'<strong>([^<]+?(?:Premium|PREMIUM|PRO|Plus|AI|TV\+|Music|Games)?[^<]*?)</strong>', block)
                service_name = service_name_match.group(1).strip() if service_name_match else f"Service_{idx}"
                
                email = ""
                email_patterns = [
                    r'Email\s*➜\s*<span>([^<]+)</span>',
                    r'Email\s*➜\s*([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
                    r'data-copy="([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})"'
                ]
                
                for pattern in email_patterns:
                    match = re.search(pattern, block)
                    if match:
                        email = match.group(1).strip()
                        break
                
                password = ""
                password_patterns = [
                    r'Password\s*➜\s*<span>([^<]+)</span>',
                    r'Password\s*➜\s*([^\s<]+)',
                    r'data-copy="([^"]+)"[^>]*>📋</button>\s*</div>\s*<div[^>]*>.*?Password'
                ]
                
                for pattern in password_patterns:
                    matches = re.findall(pattern, block)
                    if matches:
                        for match in matches:
                            if '@' not in match and match != email:
                                password = match.strip()
                                break
                    if password:
                        break
                
                official_link = ""
                link_match = re.search(r'href="([^"]*official\.php[^"]*)"', block)
                if link_match:
                    official_link = link_match.group(1)
                    if not official_link.startswith('http'):
                        official_link = f"https://www.oxaam.com/{official_link}"
                
                is_cookie_service = 'cookie' in block.lower() or 'cookiejson' in block.lower()
                
                if email or password or is_cookie_service:
                    account_info = {
                        "service": service_name,
                        "email": email if email else "Cookie-based login",
                        "password": password if password else "N/A",
                        "official_website": official_link if official_link else "N/A",
                        "type": "Cookie-based" if is_cookie_service else "Email/Password",
                        "retrieved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    accounts.append(account_info)
            
            except Exception as e:
                print(f"❌ Error processing block: {str(e)}")
                continue
        
        return accounts
    
    async def register_account(self, page):
        print("🆕 Starting registration...")
        
        try:
            await page.goto(self.base_url, wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(3000)
        except Exception as e:
            print(f"❌ Failed to load page: {str(e)}")
            return False
        
        name = self.generate_random_name()
        email = self.generate_random_email()
        phone = self.generate_random_phone()
        password = self.generate_strong_password()
        
        self.account_credentials["oxaam_email"] = email
        self.account_credentials["oxaam_password"] = password
        self.account_credentials["oxaam_phone"] = phone
        self.account_credentials["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        print(f"📝 Registering: {email}")
        
        try:
            name_selectors = ['input[placeholder="Name"]', 'input[name="name"]', '#name']
            email_selectors = ['input[placeholder="Email"]', 'input[name="email"]', 'input[type="email"]']
            phone_selectors = ['input[placeholder="Contact No."]', 'input[name="contact"]', 'input[name="phone"]']
            password_selectors = ['input[placeholder="Password"]', 'input[name="password"]', 'input[type="password"]']
            
            for selector in name_selectors:
                try:
                    await page.fill(selector, name, timeout=5000)
                    break
                except:
                    continue
            
            for selector in email_selectors:
                try:
                    await page.fill(selector, email, timeout=5000)
                    break
                except:
                    continue
            
            for selector in phone_selectors:
                try:
                    await page.fill(selector, phone, timeout=5000)
                    break
                except:
                    continue
            
            for selector in password_selectors:
                try:
                    await page.fill(selector, password, timeout=5000)
                    break
                except:
                    continue
            
            await page.wait_for_timeout(1000)
            
            register_selectors = ['button:has-text("Register")', 'button[type="submit"]']
            for selector in register_selectors:
                try:
                    await page.click(selector, timeout=5000)
                    break
                except:
                    continue
            
            await page.wait_for_timeout(4000)
            print("✅ Registration successful")
            return True
            
        except Exception as e:
            print(f"❌ Registration error: {str(e)}")
            return False
    
    async def browse_free_services(self, page):
        print("🔄 Navigating to Free Services...")
        
        try:
            link_selectors = [
                'a:has-text("Browse Free Services")',
                'a:has-text("Free Services")',
                '[href*="free"]'
            ]
            
            for selector in link_selectors:
                try:
                    await page.click(selector, timeout=5000)
                    await page.wait_for_timeout(3000)
                    print("✅ Navigated to Free Services")
                    return True
                except:
                    continue
            
            await page.goto(f"{self.base_url}freeservice.php", wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)
            return True
            
        except Exception as e:
            print(f"❌ Navigation error: {str(e)}")
            return False
    
    async def extract_all_accounts(self, page):
        print("🎬 Extracting accounts...")
        
        try:
            html_content = await page.content()
            catbox_url = self.upload_to_catbox(html_content, "free_services_page")
            if catbox_url:
                self.catbox_url = catbox_url
            
            accounts = self.extract_credentials_from_html(html_content)
            
            if accounts:
                print(f"✅ Extracted {len(accounts)} accounts")
                self.free_accounts.extend(accounts)
                for account in self.free_accounts:
                    account['debug_html_url'] = catbox_url if catbox_url else "N/A"
            
            return len(accounts) > 0
            
        except Exception as e:
            print(f"❌ Extraction error: {str(e)}")
            return False
    
    async def run(self):
        async with async_playwright() as p:
            print("🚀 Starting automation...")
            
            browser = await p.chromium.launch(
                headless=self.headless,
                args=['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-dev-shm-usage']
            )
            
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            
            page = await context.new_page()
            
            try:
                if not await self.register_account(page):
                    raise Exception("Registration failed")
                
                if not await self.browse_free_services(page):
                    raise Exception("Navigation failed")
                
                await self.extract_all_accounts(page)
                
            finally:
                await browser.close()

def run_scraper():
    global scraping_state
    
    try:
        scraping_state["is_running"] = True
        scraping_state["status"] = "running"
        scraping_state["error"] = None
        
        automation = OxaamAutomation(headless=True, save_results=False)
        asyncio.run(automation.run())
        
        scraping_state["accounts"] = automation.free_accounts
        scraping_state["session_id"] = automation.session_id
        scraping_state["status"] = "completed"
        scraping_state["last_run"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
    except Exception as e:
        scraping_state["status"] = "error"
        scraping_state["error"] = str(e)
        print(f"❌ Scraper error: {str(e)}")
    
    finally:
        scraping_state["is_running"] = False

@app.route('/')
def index():
    return jsonify({
        "service": "Oxaam Account Scraper API",
        "version": "1.0.0",
        "endpoints": {
            "/": "API documentation (this page)",
            "/accounts": "Scrape and return all free accounts (GET)",
            "/status": "Check scraping status (GET)",
            "/health": "Health check endpoint (GET)"
        },
        "usage": {
            "accounts": "GET /accounts - Triggers scraping and returns accounts in JSON",
            "status": "GET /status - Returns current scraping status and last run info",
            "health": "GET /health - Returns service health status"
        },
        "note": "Each /accounts request triggers a new scrape. Please wait for completion."
    })

@app.route('/accounts', methods=['GET'])
def get_accounts():
    global scraping_state
    
    if scraping_state["is_running"]:
        return jsonify({
            "status": "running",
            "message": "Scraping already in progress. Please check /status endpoint.",
            "current_status": scraping_state["status"]
        }), 202
    
    # Start scraping in background thread
    thread = threading.Thread(target=run_scraper)
    thread.start()
    
    # Wait for completion (max 120 seconds)
    timeout = 120
    start_time = time.time()
    
    while scraping_state["is_running"] and (time.time() - start_time) < timeout:
        time.sleep(2)
    
    if scraping_state["status"] == "completed":
        return jsonify({
            "status": "success",
            "session_id": scraping_state["session_id"],
            "timestamp": scraping_state["last_run"],
            "total_accounts": len(scraping_state["accounts"]),
            "accounts": scraping_state["accounts"]
        })
    elif scraping_state["status"] == "error":
        return jsonify({
            "status": "error",
            "message": scraping_state["error"]
        }), 500
    else:
        return jsonify({
            "status": "timeout",
            "message": "Scraping is taking longer than expected. Check /status endpoint."
        }), 408

@app.route('/status', methods=['GET'])
def get_status():
    return jsonify({
        "is_running": scraping_state["is_running"],
        "status": scraping_state["status"],
        "last_run": scraping_state["last_run"],
        "total_accounts": len(scraping_state["accounts"]),
        "session_id": scraping_state["session_id"],
        "error": scraping_state["error"]
    })

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "service": "oxaam-scraper",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
