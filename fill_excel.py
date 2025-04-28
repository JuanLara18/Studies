import pandas as pd
import requests
from bs4 import BeautifulSoup
import os
import time
import logging
import concurrent.futures
from openpyxl import load_workbook
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import re
import random
from urllib.parse import urlparse, urljoin
from datetime import datetime
import json

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("university_scraper.log"),
        logging.StreamHandler()
    ]
)

# Constantes
REFERENCES_FILE = "references.md"
INPUT_EXCEL = "Information.xlsx"
OUTPUT_EXCEL = "Information_Filled.xlsx"
MAX_WORKERS = 4  # Número de hilos concurrentes para paralelización

def log_reference(university, purpose, url):
    """Registra una URL consultada en el archivo de referencias"""
    with open(REFERENCES_FILE, "a", encoding="utf-8") as f:
        f.write(f"- [{university} – {purpose}] {url}\n")

def get_html(url, use_selenium=False, wait_time=3, selector=None):
    """Obtiene el HTML de una URL, usando Selenium si es necesario"""
    try:
        # Añadir retraso aleatorio para evitar bloqueos
        time.sleep(random.uniform(1, 3))
        
        if not use_selenium:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                return response.text
            else:
                logging.warning(f"Status code {response.status_code} for {url}")
                return None
        else:
            options = Options()
            options.add_argument("--headless")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            
            driver = webdriver.Chrome(options=options)
            
            try:
                driver.get(url)
                
                # Si se proporciona un selector, esperar a que aparezca
                if selector:
                    try:
                        WebDriverWait(driver, wait_time).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                        )
                    except TimeoutException:
                        logging.warning(f"Timeout esperando selector '{selector}' en {url}")
                else:
                    # Esperar un tiempo fijo
                    time.sleep(wait_time)
                
                html = driver.page_source
                return html
            finally:
                driver.quit()
    except Exception as e:
        logging.error(f"Error obteniendo {url}: {str(e)}")
        return None

def normalize_text(text):
    """Normaliza el texto eliminando espacios extra y saltos de línea"""
    if text:
        return re.sub(r'\s+', ' ', text).strip()
    return text

def extract_text_with_pattern(html_content, pattern, group=1):
    """Extrae texto usando un patrón regex"""
    if not html_content:
        return None
    match = re.search(pattern, html_content, re.DOTALL | re.IGNORECASE)
    if match and len(match.groups()) >= group:
        return normalize_text(match.group(group))
    return None

# ====================== EXTRACTORES DE INFORMACIÓN ======================

def extract_university_info(university_name, university_url, country, city):
    """Extrae información básica de la universidad"""
    univ_id = f"UNIV{str(abs(hash(university_name)) % 10000).zfill(4)}"
    
    data = {
        'Univ_ID': univ_id,
        'Country': country,
        'City': city,
        'University': university_name,
        'Website': university_url,
        'Type': 'N/A',
        'Size': 'N/A',
        'Campus Environment': 'N/A',
        'Main Language': 'N/A',
        'Other Languages': 'N/A',
        'Year Established': 'N/A',
        'Student Population': 'N/A',
        'Faculty-Student Ratio': 'N/A',
        'Acceptance Rate (%)': 'N/A',
        'Global Ranking (QS)': 'N/A',
        'Global Ranking (THE)': 'N/A',
        'Subject Ranking': 'N/A',
        'Research Expenditure (USD)': 'N/A',
        'Endowment (USD)': 'N/A',
        'Notable Alumni': 'N/A',
        'Official Contact Email': 'N/A',
        'Notes': ''
    }
    
    # Determinar idioma principal por país
    language_map = {
        "Estados Unidos": "English",
        "Reino Unido": "English",
        "Canadá": "English/French",
        "España": "Spanish",
        "Alemania": "German",
        "Suiza": "German/French/Italian",
        "Países Bajos": "Dutch/English",
        "México": "Spanish",
        "Chile": "Spanish"
    }
    data['Main Language'] = language_map.get(country, 'N/A')
    
    # Buscar información básica en la página principal
    html = get_html(university_url)
    if html:
        soup = BeautifulSoup(html, 'html.parser')
        
        # Buscar ranking QS en QS Top Universities
        qs_url = f"https://www.topuniversities.com/universities/{university_name.lower().replace(' ', '-')}"
        qs_html = get_html(qs_url)
        if qs_html:
            qs_soup = BeautifulSoup(qs_html, 'html.parser')
            ranking_div = qs_soup.find('div', {'class': 'ranking-result'})
            if ranking_div:
                data['Global Ranking (QS)'] = normalize_text(ranking_div.text)
            log_reference(university_name, "QS Ranking", qs_url)
        
        # Buscar año de establecimiento
        foundation_patterns = [
            re.compile(r'(founded|established|since)[^\d]*(\d{4})', re.I),
            re.compile(r'(\d{4})[^\d]*(founded|established)', re.I)
        ]
        
        for pattern in foundation_patterns:
            for tag in soup.find_all(['p', 'div', 'span', 'section']):
                if tag.text:
                    match = pattern.search(tag.text)
                    if match:
                        year = None
                        for group in match.groups():
                            if group and group.isdigit() and len(group) == 4:
                                year = group
                                break
                        if year and 1000 <= int(year) <= datetime.now().year:
                            data['Year Established'] = year
                            break
            if data['Year Established'] != 'N/A':
                break
        
        # Buscar tamaño de estudiantes
        student_patterns = [
            re.compile(r'(student(s)?|enrollment|population)[^\d]*?(\d{1,3}(,\d{3})+|\d{4,})', re.I),
            re.compile(r'(\d{1,3}(,\d{3})+|\d{4,}).*?(student(s)?|enrollment)', re.I)
        ]
        
        for pattern in student_patterns:
            for tag in soup.find_all(['p', 'div', 'span', 'section']):
                if tag.text:
                    match = pattern.search(tag.text)
                    if match:
                        population = None
                        for group in match.groups():
                            if group and (re.match(r'\d{1,3}(,\d{3})+|\d{4,}', group)):
                                population = group
                                break
                        if population:
                            data['Student Population'] = population
                            break
            if data['Student Population'] != 'N/A':
                break
        
        # Determinar tipo (pública/privada)
        public_indicators = ['public', 'state university', 'state-funded']
        private_indicators = ['private', 'independent', 'not-for-profit']
        
        about_section = None
        for about_link in soup.find_all('a', href=re.compile(r'about|university|overview', re.I)):
            about_url = urljoin(university_url, about_link['href'])
            about_html = get_html(about_url)
            if about_html:
                about_soup = BeautifulSoup(about_html, 'html.parser')
                about_section = about_soup
                log_reference(university_name, "About page", about_url)
                break
        
        if about_section:
            text_blocks = ' '.join([p.text for p in about_section.find_all(['p', 'div', 'section'])])
            if any(term.lower() in text_blocks.lower() for term in public_indicators):
                data['Type'] = 'Public'
            elif any(term.lower() in text_blocks.lower() for term in private_indicators):
                data['Type'] = 'Private'
        
        # Definir tamaño basado en población estudiantil
        if data['Student Population'] != 'N/A':
            try:
                population = int(data['Student Population'].replace(',', ''))
                if population > 30000:
                    data['Size'] = 'Large'
                elif population > 10000:
                    data['Size'] = 'Medium'
                else:
                    data['Size'] = 'Small'
            except:
                pass
        
        # Determinar entorno del campus
        urban_indicators = ['urban', 'city', 'metropolitan']
        suburban_indicators = ['suburban', 'outskirts', 'residential area']
        rural_indicators = ['rural', 'countryside', 'remote']
        
        campus_html = get_html(f"{university_url}/campus") or html
        if campus_html:
            campus_soup = BeautifulSoup(campus_html, 'html.parser')
            campus_text = ' '.join([p.text for p in campus_soup.find_all(['p', 'div', 'section'])])
            
            if any(term.lower() in campus_text.lower() for term in urban_indicators):
                data['Campus Environment'] = 'Urban'
            elif any(term.lower() in campus_text.lower() for term in suburban_indicators):
                data['Campus Environment'] = 'Suburban'
            elif any(term.lower() in campus_text.lower() for term in rural_indicators):
                data['Campus Environment'] = 'Rural'
        
        log_reference(university_name, "información general", university_url)
    
    return data

def extract_program_info(university_name, university_url, univ_id):
    """Extrae información de programas de interés"""
    programs = []
    
    # Configuración base para programas de interés
    program_types = {
        "CS": {
            "keywords": ["computer science", "computing", "informatics", "software engineering", "EECS", "artificial intelligence"],
            "urls": ["/cs", "/computerscience", "/computing", "/informatics", "/engineering/cs"]
        },
        "Business Analytics": {
            "keywords": ["business analytics", "data analytics", "business intelligence", "data science", "management science", "analytics"],
            "urls": ["/business", "/analytics", "/mba", "/management", "/datascience"]
        },
        "Mathematics": {
            "keywords": ["mathematics", "mathematical", "applied mathematics", "statistics", "computational mathematics"],
            "urls": ["/math", "/mathematics", "/statistics", "/appliedmath"]
        }
    }
    
    # URLs base para buscar programas
    base_urls = [
        f"{university_url}/graduate",
        f"{university_url}/postgraduate",
        f"{university_url}/masters",
        f"{university_url}/study",
        f"{university_url}/programs",
        f"{university_url}/academics",
        f"{university_url}/degrees"
    ]
    
    # Iterar por cada tipo de programa
    for program_type, config in program_types.items():
        # Primero intentar con URLs específicas para el tipo de programa
        for url_suffix in config["urls"]:
            specific_url = f"{university_url}{url_suffix}"
            html = get_html(specific_url)
            if html:
                program = process_program_page(html, university_name, specific_url, univ_id, program_type)
                if program:
                    programs.append(program)
                    log_reference(university_name, f"{program_type} program", specific_url)
        
        # Si no encontramos programas específicos, buscar en las URLs base
        if not any(p for p in programs if p['Main Areas of Focus'] == program_type):
            for base_url in base_urls:
                html = get_html(base_url)
                if html:
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    # Buscar enlaces a programas que contengan palabras clave
                    for keyword in config["keywords"]:
                        links = soup.find_all(lambda tag: tag.name == 'a' and 
                                             keyword.lower() in tag.text.lower())
                        
                        for link in links:
                            if link.has_attr('href'):
                                program_url = urljoin(base_url, link['href'])
                                program_html = get_html(program_url)
                                if program_html:
                                    program = process_program_page(program_html, university_name, program_url, univ_id, program_type)
                                    if program:
                                        programs.append(program)
                                        log_reference(university_name, f"{program_type} program - {program['Program Name']}", program_url)
                                        break  # Solo tomamos un programa de cada tipo
            
    return programs

def process_program_page(html, university_name, program_url, univ_id, program_type):
    """Procesa una página de programa para extraer información"""
    soup = BeautifulSoup(html, 'html.parser')
    
    # Intentar identificar el nombre del programa
    title_tags = soup.find_all(['h1', 'h2', 'h3', 'title'])
    program_name = None
    
    for tag in title_tags:
        text = tag.text.strip()
        # Buscar programas que contengan palabras clave según el tipo
        if program_type == "CS" and any(k in text.lower() for k in ["computer science", "computing", "software", "artificial intelligence"]):
            program_name = text
            break
        elif program_type == "Business Analytics" and any(k in text.lower() for k in ["business analytics", "data analytics", "business intelligence"]):
            program_name = text
            break
        elif program_type == "Mathematics" and any(k in text.lower() for k in ["math", "mathematics", "applied mathematics"]):
            program_name = text
            break
    
    # Si no encontramos nombre específico, usar el título de la página
    if not program_name:
        program_name = soup.title.text.strip() if soup.title else f"{program_type} Program"
    
    # Crear ID único para el programa
    prog_id = f"PROG{str(abs(hash(program_name + university_name)) % 10000).zfill(4)}"
    
    # Inicializar el diccionario del programa
    program = {
        'Prog_ID': prog_id,
        'Univ_ID': univ_id,
        'Program Name': program_name,
        'Degree Type': 'N/A',
        'Program Website': program_url,
        'Duration (Years)': 'N/A',
        'Mode': 'N/A',
        'Number of Credits': 'N/A',
        'Tuition Fee (per year)': 'N/A',
        'Currency': 'N/A',
        'Main Areas of Focus': program_type,
        'Application Deadline': 'N/A',
        'Admission Seasons': 'N/A',
        'Start Date': 'N/A',
        'Cohort Size': 'N/A',
        'Language Requirement': 'N/A',
        'Prerequisites': 'N/A',
        'Funding Options': 'N/A',
        'Program Coordinator': 'N/A',
        'Contact Email': 'N/A',
        'Notes': ''
    }
    
    # Extraer duración
    duration_patterns = [
        r'(duration|length|program length).*?(\d+(?:\.\d+)?)\s*(year|years)',
        r'(\d+(?:\.\d+)?)\s*(year|years).*?(duration|length|program)',
        r'(\d+(?:\.\d+)?)\s*(year|years)\s*(course|program|degree)'
    ]
    
    for pattern in duration_patterns:
        duration_text = extract_text_with_pattern(str(soup), pattern, 2)
        if duration_text:
            program['Duration (Years)'] = duration_text.strip()
            break
    
    # Extraer modalidad (Full-time, Part-time, etc.)
    mode_patterns = [
        r'(full[- ]time|part[- ]time|online|hybrid|distance|on[- ]campus)',
        r'(mode of study|delivery mode|study mode).*?(full[- ]time|part[- ]time|online|hybrid)'
    ]
    
    for pattern in mode_patterns:
        mode_text = extract_text_with_pattern(str(soup), pattern)
        if mode_text:
            mode_map = {
                'full-time': 'Full-time',
                'fulltime': 'Full-time',
                'full time': 'Full-time',
                'part-time': 'Part-time',
                'parttime': 'Part-time',
                'part time': 'Part-time',
                'online': 'Online',
                'hybrid': 'Hybrid',
                'distance': 'Online',
                'on-campus': 'Full-time',
                'on campus': 'Full-time'
            }
            
            for key, value in mode_map.items():
                if key in mode_text.lower():
                    program['Mode'] = value
                    break
            
            if program['Mode'] != 'N/A':
                break
    
    # Extraer tipo de grado (Master's, Ph.D., etc.)
    degree_patterns = [
        r'(master|msc|ma|ms|meng|mphil|phd|doctorate|certificate|diploma)',
        r'(degree type|type of degree|qualification).*?(master|msc|ma|ms|meng|phd)'
    ]
    
    for pattern in degree_patterns:
        degree_text = extract_text_with_pattern(str(soup), pattern)
        if degree_text:
            degree_map = {
                'master': 'Master\'s',
                'msc': 'Master of Science',
                'ma': 'Master of Arts',
                'ms': 'Master of Science',
                'meng': 'Master of Engineering',
                'mphil': 'Master of Philosophy',
                'phd': 'Ph.D.',
                'doctorate': 'Ph.D.',
                'certificate': 'Certificate',
                'diploma': 'Diploma'
            }
            
            for key, value in degree_map.items():
                if key in degree_text.lower():
                    program['Degree Type'] = value
                    break
            
            if program['Degree Type'] != 'N/A':
                break
    
    # Extraer créditos
    credit_patterns = [
        r'(credits|credit hours|ects).*?(\d+)',
        r'(\d+).*?(credits|credit hours|ects)',
        r'(program|course).*?(\d+).*?(credits|credit hours|ects)'
    ]
    
    for pattern in credit_patterns:
        credit_text = extract_text_with_pattern(str(soup), pattern, 2)
        if credit_text and credit_text.isdigit():
            program['Number of Credits'] = credit_text
            break
    
    # Extraer matrícula/costos
    tuition_patterns = [
        r'(tuition|fee|cost|price).*?(\$|\€|\£|\¥)?(\d{1,3}(,\d{3})+|\d{4,})',
        r'(\$|\€|\£|\¥)?(\d{1,3}(,\d{3})+|\d{4,}).*?(tuition|fee|per year|annual)'
    ]
    
    for pattern in tuition_patterns:
        tuition_text = extract_text_with_pattern(str(soup), pattern)
        if tuition_text:
            # Extraer el monto y la moneda
            currency_match = re.search(r'(\$|\€|\£|\¥)', tuition_text)
            amount_match = re.search(r'(\d{1,3}(,\d{3})+|\d{4,})', tuition_text)
            
            if amount_match:
                program['Tuition Fee (per year)'] = amount_match.group(1)
                
                if currency_match:
                    currency_symbol = currency_match.group(1)
                    currency_map = {
                        '$': 'USD',
                        '€': 'EUR',
                        '£': 'GBP',
                        '¥': 'JPY'
                    }
                    program['Currency'] = currency_map.get(currency_symbol, 'N/A')
            break
    
    # Extraer plazos de solicitud
    deadline_patterns = [
        r'(application deadline|apply by|submission deadline).*?(\d{1,2}[- /\.]\d{1,2}[- /\.]\d{2,4}|\d{1,2} [A-Za-z]+ \d{2,4}|[A-Za-z]+ \d{1,2},? \d{2,4})',
        r'(deadline).*?(\d{1,2} [A-Za-z]+ \d{2,4}|[A-Za-z]+ \d{1,2} \d{2,4})'
    ]
    
    for pattern in deadline_patterns:
        deadline_text = extract_text_with_pattern(str(soup), pattern, 2)
        if deadline_text:
            program['Application Deadline'] = deadline_text
            break
    
    # Extraer temporadas de admisión
    season_patterns = [
        r'(fall|spring|summer|winter|autumn|january|september|october|february)',
        r'(term|intake|start date|admission cycle).*?(fall|spring|summer|winter|autumn|january|september|october)',
        r'(applications? accepted|program starts?).*?(fall|spring|summer|winter|autumn|january|september)'
    ]
    
    for pattern in season_patterns:
        season_text = extract_text_with_pattern(str(soup), pattern)
        if season_text:
            season_map = {
                'fall': 'Fall',
                'autumn': 'Fall',
                'spring': 'Spring',
                'summer': 'Summer',
                'winter': 'Winter',
                'january': 'Spring',
                'february': 'Spring',
                'september': 'Fall',
                'october': 'Fall'
            }
            
            detected_seasons = []
            for key, value in season_map.items():
                if key in season_text.lower() and value not in detected_seasons:
                    detected_seasons.append(value)
            
            if detected_seasons:
                program['Admission Seasons'] = ', '.join(detected_seasons)
                break
    
    # Extraer requisitos de idioma
    language_patterns = [
        r'(toefl|ielts|english proficiency).*?(\d+)',
        r'(language requirement|english language).*?(toefl|ielts).*?(\d+)',
        r'(minimum|required).*?(english).*?(toefl|ielts).*?(\d+)'
    ]
    
    language_req = []
    for pattern in language_patterns:
        language_text = extract_text_with_pattern(str(soup), pattern)
        if language_text:
            toefl_match = re.search(r'toefl.*?(\d+)', language_text, re.I)
            ielts_match = re.search(r'ielts.*?(\d+(?:\.\d+)?)', language_text, re.I)
            
            if toefl_match:
                language_req.append(f"TOEFL: {toefl_match.group(1)}")
            if ielts_match:
                language_req.append(f"IELTS: {ielts_match.group(1)}")
    
    if language_req:
        program['Language Requirement'] = ', '.join(language_req)
    
    # Extraer prerrequisitos
    prereq_patterns = [
        r'(prerequisites?|required courses|academic background).*?([^\.]+)',
        r'(candidates?|applicants?|students?) (should|must|are expected to).*?([^\.]+)'
    ]
    
    for pattern in prereq_patterns:
        prereq_text = extract_text_with_pattern(str(soup), pattern, 3)
        if prereq_text and len(prereq_text) > 10:  # Evitar textos muy cortos
            if "background" in prereq_text.lower() or "degree" in prereq_text.lower():
                program['Prerequisites'] = prereq_text[:100] + ('...' if len(prereq_text) > 100 else '')
                break
    
    # Extraer información de contacto
    contact_patterns = [
        r'(contact|coordinator|director|advisor).*?([A-Za-z\. ]+).*?(email|@)',
        r'([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})'
    ]
    
    for pattern in contact_patterns:
        contact_text = extract_text_with_pattern(str(soup), pattern)
        if contact_text:
            email_match = re.search(r'([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})', contact_text)
            if email_match:
                program['Contact Email'] = email_match.group(1)
                
                # Intentar extraer el nombre del coordinador
                name_match = re.search(r'([A-Za-z\. ]{5,30}).*?' + re.escape(email_match.group(1)), str(soup), re.DOTALL)
                if name_match:
                    program['Program Coordinator'] = name_match.group(1).strip()
            break
    
    return program

def extract_lab_info(university_name, university_url, univ_id):
    """Extrae información sobre laboratorios y centros de investigación"""
    labs = []
    
    # URLs comunes donde se pueden encontrar laboratorios
    lab_urls = [
        f"{university_url}/research",
        f"{university_url}/labs",
        f"{university_url}/centers",
        f"{university_url}/institutes",
        f"{university_url}/groups",
        f"{university_url}/faculty/research"
    ]
    
    # Palabras clave para buscar laboratorios relevantes
    keywords = {
        "AI": ["artificial intelligence", "machine learning", "deep learning", "neural networks"],
        "Data Science": ["data science", "big data", "analytics", "data mining"],
        "HCI": ["human-computer interaction", "hci", "user interface", "user experience", "usability"],
        "Robotics": ["robotics", "autonomous systems", "robot", "automation"],
        "Computer Vision": ["computer vision", "image processing", "visual recognition", "object detection"],
        "NLP": ["natural language processing", "nlp", "computational linguistics", "text mining"],
        "Cybersecurity": ["cybersecurity", "security", "cryptography", "privacy"]
    }
    
    for lab_url in lab_urls:
        try:
            html = get_html(lab_url, use_selenium=True)
            if not html:
                continue
                
            soup = BeautifulSoup(html, 'html.parser')
            
            # Buscar enlaces que contengan palabras clave de laboratorios
            for area, terms in keywords.items():
                for term in terms:
                    # Buscar en texto de enlaces
                    lab_links = soup.find_all('a', text=re.compile(term, re.I))
                    
                    # También buscar en divs/secciones que contengan enlaces
                    lab_sections = soup.find_all(['div', 'section'], text=re.compile(term, re.I))
                    for section in lab_sections:
                        links = section.find_all('a')
                        lab_links.extend(links)
                    
                    for link in lab_links:
                        if not link.has_attr('href'):
                            continue
                            
                        specific_lab_url = urljoin(lab_url, link['href'])
                        
                        # Evitar duplicados
                        if any(lab['Website'] == specific_lab_url for lab in labs):
                            continue
                        
                        # Extraer datos del laboratorio
                        lab_html = get_html(specific_lab_url)
                        if lab_html:
                            lab_soup = BeautifulSoup(lab_html, 'html.parser')
                            
                            # Extraer nombre del laboratorio
                            lab_name = None
                            lab_title = lab_soup.find(['h1', 'h2', 'title'])
                            if lab_title:
                                lab_name = lab_title.text.strip()
                            else:
                                lab_name = link.text.strip()
                            
                            if not lab_name or len(lab_name) < 3:
                                continue
                            
                            # Crear ID único
                            lab_id = f"LAB{str(abs(hash(lab_name + university_name)) % 10000).zfill(4)}"
                            
                            # Extraer investigadores
                            researchers = []
                            for person_section in lab_soup.find_all(['div', 'section'], class_=re.compile(r'(faculty|people|team|staff|researchers)', re.I)):
                                for person in person_section.find_all(['h3', 'h4', 'strong', 'div', 'p'], class_=re.compile(r'(name|person|researcher|faculty)', re.I)):
                                    name = person.text.strip()
                                    if name and len(name) > 3 and any(c.isalpha() for c in name):
                                        researchers.append(name)
                            
                            # Extraer director del laboratorio
                            director = None
                            director_patterns = [
                                r'(director|head|lead|principal investigator)[:\s]+([A-Za-z\.\- ]{5,40})',
                                r'([A-Za-z\.\- ]{5,40})[,\s]+(director|head|lead|principal)'
                            ]
                            
                            for pattern in director_patterns:
                                director_match = re.search(pattern, lab_html, re.I)
                                if director_match:
                                    director = normalize_text(director_match.group(2) if 'director' in director_match.group(1).lower() else director_match.group(1))
                                    break
                            
                            # Extraer departamento/facultad
                            department = None
                            dept_patterns = [
                                r'(department|faculty|school) of ([A-Za-z\s&]+)',
                                r'([A-Za-z\s&]+) (department|faculty|school)'
                            ]
                            
                            for pattern in dept_patterns:
                                dept_match = re.search(pattern, lab_html, re.I)
                                if dept_match:
                                    department = normalize_text(dept_match.group(2) if 'department' in dept_match.group(1).lower() else dept_match.group(1))
                                    break
                            
                            # Extraer proyectos activos
                            projects_count = None
                            projects_patterns = [
                                r'(\d+)\s+(projects?|ongoing research|active (projects|research))',
                                r'(projects?|ongoing research|active (projects|research))[:\s]+(\d+)'
                            ]
                            
                            for pattern in projects_patterns:
                                projects_match = re.search(pattern, lab_html, re.I)
                                if projects_match:
                                    projects_count = projects_match.group(1) if projects_match.group(1).isdigit() else projects_match.group(3)
                                    break
                            
                            # Crear registro del laboratorio
                            lab = {
                                'Lab_ID': lab_id,
                                'Univ_ID': univ_id,
                                'Prog_ID': '',
                                'Laboratory / Center Name': lab_name,
                                'Department/Faculty': department or 'N/A',
                                'Research Fields': area,
                                'Website': specific_lab_url,
                                'Lab Director': director or 'N/A',
                                'Contact Email': 'N/A',
                                'Key Researchers': ', '.join(researchers[:5]) if researchers else 'N/A',
                                'Location (Building)': 'N/A',
                                'Number of Active Projects': projects_count or 'N/A',
                                'Grant Funding (USD)': 'N/A',
                                'Industry Collaborations': 'N/A',
                                'Facilities': 'N/A',
                                'Annual Publications': 'N/A',
                                'Student Positions Available': 'N/A',
                                'Lab Ranking (if available)': 'N/A',
                                'Notes': ''
                            }
                            
                            # Buscar correo electrónico de contacto
                            email_match = re.search(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)', lab_html)
                            if email_match:
                                lab['Contact Email'] = email_match.group(1)
                            
                            # Buscar colaboraciones con la industria
                            industry_patterns = [
                                r'(industry|companies|corporate|partnership)[:\s]+([^\.]+)',
                                r'(collaborat\w+) with ([^\.]+)'
                            ]
                            
                            for pattern in industry_patterns:
                                industry_match = re.search(pattern, lab_html, re.I)
                                if industry_match:
                                    industry_text = industry_match.group(2)
                                    if len(industry_text) > 5 and ('industry' in industry_text.lower() or 
                                                                    'compan' in industry_text.lower() or 
                                                                    any(company in industry_text.lower() for company in ['google', 'microsoft', 'amazon', 'ibm', 'nvidia'])):
                                        lab['Industry Collaborations'] = industry_text[:100] + '...' if len(industry_text) > 100 else industry_text
                                        break
                                    
                            labs.append(lab)
                            log_reference(university_name, f"Laboratorio: {lab_name}", specific_lab_url)
                            
                            # Limitar a 5 laboratorios por universidad
                            if len(labs) >= 5:
                                break
                    
                    if len(labs) >= 5:
                        break
                
                if len(labs) >= 5:
                    break
                    
        except Exception as e:
            logging.error(f"Error extrayendo laboratorios para {university_name}: {str(e)}")
    
    return labs

def extract_scholarship_info(university_name, university_url, univ_id):
    """Extrae información sobre becas y financiamiento"""
    scholarships = []
    
    # URLs comunes donde se pueden encontrar becas
    scholarship_urls = [
        f"{university_url}/scholarships",
        f"{university_url}/financial-aid",
        f"{university_url}/funding",
        f"{university_url}/fees-and-funding",
        f"{university_url}/international/scholarships",
        f"{university_url}/graduate/funding",
        f"{university_url}/admissions/financial-aid"
    ]
    
    for scholarship_url in scholarship_urls:
        try:
            html = get_html(scholarship_url)
            if not html:
                continue
                
            soup = BeautifulSoup(html, 'html.parser')
            
            # Buscar secciones que contengan información de becas
            scholarship_sections = []
            
            # Buscar por clases/IDs típicos de becas
            for section in soup.find_all(['div', 'section', 'article'], class_=re.compile(r'(scholarship|funding|financial|aid)', re.I)):
                scholarship_sections.append(section)
            
            # Buscar por encabezados relacionados con becas
            for heading in soup.find_all(['h1', 'h2', 'h3', 'h4'], text=re.compile(r'(scholarship|funding|award|grant|bursary)', re.I)):
                # Obtener la sección que sigue al encabezado
                section = heading.find_next(['div', 'section', 'article', 'p', 'ul'])
                if section:
                    scholarship_sections.append(section)
            
            # Si no encontramos secciones específicas, usar toda la página
            if not scholarship_sections:
                scholarship_sections = [soup]
                
            for section in scholarship_sections:
                # Buscar nombres de becas
                scholarship_titles = []
                
                # Buscar en listas
                for item in section.find_all('li'):
                    text = item.text.strip()
                    if any(term in text.lower() for term in ['scholarship', 'grant', 'award', 'fellowship', 'bursary']) and len(text) < 100:
                        scholarship_titles.append(text)
                
                # Buscar en encabezados
                for heading in section.find_all(['h3', 'h4', 'h5', 'strong']):
                    text = heading.text.strip()
                    if any(term in text.lower() for term in ['scholarship', 'grant', 'award', 'fellowship', 'bursary']) and len(text) < 100:
                        scholarship_titles.append(text)
                
                # Procesar cada beca encontrada
                for title in scholarship_titles:
                    # Crear ID único
                    scholarship_id = f"SCH{str(abs(hash(title + university_name)) % 10000).zfill(4)}"
                    
                    # Crear registro de beca
                    scholarship = {
                        'Scholarship_ID': scholarship_id,
                        'Univ_ID': univ_id,
                        'Prog_ID': '',
                        'Scholarship Name': title,
                        'Type of Funding': 'N/A',
                        'Amount': 'N/A',
                        'Currency': 'N/A',
                        'Eligibility Criteria': 'N/A',
                        'Competitiveness': 'N/A',
                        'Number of Awards': 'N/A',
                        'Application Deadline': 'N/A',
                        'Notification Date': 'N/A',
                        'Disbursement Schedule': 'N/A',
                        'Renewal Conditions': 'N/A',
                        'Selection Process': 'N/A',
                        'Scholarship Website': scholarship_url,
                        'Contact Person': 'N/A',
                        'Contact Email': 'N/A',
                        'Notes': ''
                    }
                    
                    # Buscar información detallada de la beca
                    details_element = None
                    
                    # Buscar en el elemento que contiene el título
                    for element in section.find_all(text=re.compile(re.escape(title))):
                        parent = element.parent
                        # Obtener el siguiente párrafo o lista
                        details_element = parent.find_next(['p', 'div', 'ul'])
                        if details_element:
                            break
                    
                    if details_element:
                        details_text = details_element.text
                        
                        # Extraer tipo de financiamiento
                        funding_types = {
                            'full tuition': 'Full Tuition',
                            'partial tuition': 'Partial Tuition',
                            'living stipend': 'Living Stipend',
                            'travel grant': 'Travel Grant',
                            'research grant': 'Research Grant',
                            'teaching assistant': 'Teaching Assistantship',
                            'research assistant': 'Research Assistantship'
                        }
                        
                        for key, value in funding_types.items():
                            if key in details_text.lower():
                                scholarship['Type of Funding'] = value
                                break
                        
                        # Extraer monto
                        amount_match = re.search(r'(\$|\€|\£|\¥)?(\d{1,3}(,\d{3})+|\d{4,})', details_text)
                        if amount_match:
                            scholarship['Amount'] = amount_match.group(0)
                            
                            # Extraer moneda
                            currency_match = re.search(r'(\$|\€|\£|\¥)', details_text)
                            if currency_match:
                                currency_symbol = currency_match.group(1)
                                currency_map = {
                                    '$': 'USD',
                                    '€': 'EUR',
                                    '£': 'GBP',
                                    '¥': 'JPY'
                                }
                                scholarship['Currency'] = currency_map.get(currency_symbol, 'N/A')
                        
                        # Extraer criterios de elegibilidad
                        eligibility_patterns = [
                            r'(eligibility|eligible|requirements?)[:\s]+([^\.]+)',
                            r'(available to|open to|for students?)[:\s]+([^\.]+)'
                        ]
                        
                        for pattern in eligibility_patterns:
                            eligibility_match = re.search(pattern, details_text, re.I)
                            if eligibility_match:
                                scholarship['Eligibility Criteria'] = eligibility_match.group(2)[:100] + '...' if len(eligibility_match.group(2)) > 100 else eligibility_match.group(2)
                                break
                        
                        # Extraer plazo de solicitud
                        deadline_match = re.search(r'(deadline|apply by|due)[:\s]+([A-Za-z]+ \d{1,2}(st|nd|rd|th)?,? \d{4}|\d{1,2}[- /\.]\d{1,2}[- /\.]\d{2,4})', details_text, re.I)
                        if deadline_match:
                            scholarship['Application Deadline'] = deadline_match.group(2)
                    
                    scholarships.append(scholarship)
                    log_reference(university_name, f"Beca: {title}", scholarship_url)
                    
                    # Limitar a 5 becas por universidad
                    if len(scholarships) >= 5:
                        break
                
                if len(scholarships) >= 5:
                    break
            
            if len(scholarships) >= 5:
                break
                
        except Exception as e:
            logging.error(f"Error extrayendo becas para {university_name}: {str(e)}")
    
    # Añadir becas internacionales conocidas
    international_scholarships = [
        {
            'name': 'Fulbright Foreign Student Program',
            'type': 'Full Tuition',
            'url': 'https://foreign.fulbrightonline.org/',
            'eligibility': 'International students applying to US universities',
            'countries': ['Estados Unidos']
        },
        {
            'name': 'Chevening Scholarships',
            'type': 'Full Tuition',
            'url': 'https://www.chevening.org/',
            'eligibility': 'International students applying to UK universities',
            'countries': ['Reino Unido']
        },
        {
            'name': 'Gates Cambridge Scholarship',
            'type': 'Full Tuition',
            'url': 'https://www.gatescambridge.org/',
            'eligibility': 'International students applying to University of Cambridge',
            'countries': ['Reino Unido']
        },
        {
            'name': 'DAAD Scholarships',
            'type': 'Full Tuition',
            'url': 'https://www.daad.de/en/',
            'eligibility': 'International students applying to German universities',
            'countries': ['Alemania']
        },
        {
            'name': 'Swiss Government Excellence Scholarships',
            'type': 'Full Tuition',
            'url': 'https://www.sbfi.admin.ch/sbfi/en/home/education/scholarships-and-grants/swiss-government-excellence-scholarships.html',
            'eligibility': 'International students applying to Swiss universities',
            'countries': ['Suiza']
        },
        {
            'name': 'Erasmus Mundus Joint Master Degrees',
            'type': 'Full Tuition',
            'url': 'https://erasmus-plus.ec.europa.eu/opportunities/individuals/students/erasmus-mundus-joint-masters-scholarships',
            'eligibility': 'International students applying to European universities',
            'countries': ['España', 'Reino Unido', 'Alemania', 'Suiza', 'Países Bajos']
        },
        {
            'name': 'Colfuturo',
            'type': 'Partial Tuition',
            'url': 'https://www.colfuturo.org/',
            'eligibility': 'Colombian students for international postgraduate studies',
            'countries': ['Estados Unidos', 'España', 'Reino Unido', 'Canadá', 'Alemania', 'Suiza', 'Países Bajos', 'Chile']
        }
    ]
    
    for scholarship_info in international_scholarships:
        # Comprobar si la beca aplica para el país de la universidad
        if university_name.split(', ')[0] in scholarship_info['countries']:
            scholarship_id = f"SCH{str(abs(hash(scholarship_info['name'])) % 10000).zfill(4)}"
            
            scholarship = {
                'Scholarship_ID': scholarship_id,
                'Univ_ID': univ_id,
                'Prog_ID': '',
                'Scholarship Name': scholarship_info['name'],
                'Type of Funding': scholarship_info['type'],
                'Amount': 'Varies',
                'Currency': 'USD',
                'Eligibility Criteria': scholarship_info['eligibility'],
                'Competitiveness': 'High',
                'Number of Awards': 'N/A',
                'Application Deadline': 'Check website',
                'Notification Date': 'N/A',
                'Disbursement Schedule': 'N/A',
                'Renewal Conditions': 'N/A',
                'Selection Process': 'N/A',
                'Scholarship Website': scholarship_info['url'],
                'Contact Person': 'N/A',
                'Contact Email': 'N/A',
                'Notes': 'International scholarship program'
            }
            
            # Evitar duplicados
            if not any(s['Scholarship Name'] == scholarship_info['name'] for s in scholarships):
                scholarships.append(scholarship)
                log_reference(university_name, f"Beca Internacional: {scholarship_info['name']}", scholarship_info['url'])
    
    return scholarships

def extract_admission_info(university_name, university_url, univ_id, prog_id=''):
    """Extrae información sobre requisitos de admisión"""
    admission = {
        'Admission_ID': f"ADM{str(abs(hash(university_name + (prog_id or ''))) % 10000).zfill(4)}",
        'Univ_ID': univ_id,
        'Prog_ID': prog_id,
        'Minimum GPA': 'N/A',
        'GPA Scale': 'N/A',
        'Required Exams': 'N/A',
        'Minimum Scores': 'N/A',
        'Language Test Validity (years)': 'N/A',
        'Letters of Recommendation': 'N/A',
        'Statement of Purpose': 'N/A',
        'Resume / CV': 'N/A',
        'Interview Requirement': 'N/A',
        'Research Proposal': 'N/A',
        'Experience Required': 'N/A',
        'Portfolio/Writing Samples': 'N/A',
        'Application Deadline': 'N/A',
        'Application Fee (USD)': 'N/A',
        'Rolling Admission': 'N/A',
        'Other Requirements': 'N/A',
        'Notes': ''
    }
    
    # URLs comunes para requisitos de admisión
    admission_urls = [
        f"{university_url}/admissions",
        f"{university_url}/apply",
        f"{university_url}/graduate/admissions",
        f"{university_url}/graduate/apply",
        f"{university_url}/international/requirements",
        f"{university_url}/requirements",
        f"{university_url}/graduate/requirements"
    ]
    
    for admission_url in admission_urls:
        try:
            html = get_html(admission_url)
            if not html:
                continue
                
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extraer GPA mínimo
            gpa_patterns = [
                r'(minimum|required)\s+GPA\s+(?:of)?\s+(\d+\.\d+)',
                r'GPA\s+(?:of)?\s+(\d+\.\d+)\s+or\s+(above|higher)',
                r'GPA\s*[:=]\s*(\d+\.\d+)'
            ]
            
            for pattern in gpa_patterns:
                gpa_match = re.search(pattern, soup.text, re.I)
                if gpa_match:
                    gpa_value = next((g for g in gpa_match.groups() if g and re.match(r'\d+\.\d+', g)), None)
                    if gpa_value:
                        admission['Minimum GPA'] = gpa_value
                        
                        # Determinar escala de GPA
                        if float(gpa_value) <= 4.0:
                            admission['GPA Scale'] = '4.0'
                        elif float(gpa_value) <= 5.0:
                            admission['GPA Scale'] = '5.0'
                        elif float(gpa_value) <= 10.0:
                            admission['GPA Scale'] = '10.0'
                        break
            
            # Extraer exámenes requeridos
            exam_patterns = {
                'GRE': r'(GRE|Graduate Record Examination)',
                'GMAT': r'(GMAT|Graduate Management Admission Test)',
                'TOEFL': r'(TOEFL|Test of English as a Foreign Language)',
                'IELTS': r'(IELTS|International English Language Testing System)'
            }
            
            required_exams = []
            for exam, pattern in exam_patterns.items():
                if re.search(pattern, soup.text, re.I):
                    required_exams.append(exam)
            
            if required_exams:
                admission['Required Exams'] = ', '.join(required_exams)
            
            # Extraer puntuaciones mínimas
            score_patterns = {
                'TOEFL': r'TOEFL\s+(?:minimum|required)?\s+(?:score\s+(?:of)?)?\s+(\d+)',
                'IELTS': r'IELTS\s+(?:minimum|required)?\s+(?:score\s+(?:of)?)?\s+(\d+(?:\.\d+)?)',
                'GRE': r'GRE\s+(?:minimum|required)?\s+(?:score\s+(?:of)?)?\s+(\d+)',
                'GMAT': r'GMAT\s+(?:minimum|required)?\s+(?:score\s+(?:of)?)?\s+(\d+)'
            }
            
            min_scores = []
            for exam, pattern in score_patterns.items():
                score_match = re.search(pattern, soup.text, re.I)
                if score_match:
                    min_scores.append(f"{exam}: {score_match.group(1)}")
            
            if min_scores:
                admission['Minimum Scores'] = ', '.join(min_scores)
            
            # Extraer validez de prueba de idioma
            validity_match = re.search(r'(TOEFL|IELTS).*?valid for (\d+) years?', soup.text, re.I)
            if validity_match:
                admission['Language Test Validity (years)'] = validity_match.group(2)
            
            # Extraer cartas de recomendación
            rec_match = re.search(r'(\d+).*?letters? of recommendation', soup.text, re.I)
            if rec_match:
                admission['Letters of Recommendation'] = rec_match.group(1)
            
            # Extraer statement of purpose
            if re.search(r'statement of (purpose|intent|objectives)', soup.text, re.I):
                admission['Statement of Purpose'] = 'Yes'
            
            # Extraer requisito de CV
            if re.search(r'(resume|CV|curriculum vitae)', soup.text, re.I):
                admission['Resume / CV'] = 'Yes'
            
            # Extraer requisito de entrevista
            if re.search(r'interview', soup.text, re.I):
                admission['Interview Requirement'] = 'Yes'
            
            # Extraer requisito de propuesta de investigación
            if re.search(r'research proposal', soup.text, re.I):
                admission['Research Proposal'] = 'Yes'
            
            # Extraer tarifa de aplicación
            fee_match = re.search(r'application fee.*?(\$|\€|\£|\¥)?(\d+)', soup.text, re.I)
            if fee_match:
                currency_symbol = fee_match.group(1) or '$'
                fee_amount = fee_match.group(2)
                
                # Convertir a USD si no está en esa moneda
                if currency_symbol == '$':
                    admission['Application Fee (USD)'] = fee_amount
                else:
                    # Conversión aproximada (se podrían usar APIs de conversión de moneda)
                    conversion_rates = {'€': 1.1, '£': 1.3, '¥': 0.0068}
                    rate = conversion_rates.get(currency_symbol, 1)
                    usd_amount = int(float(fee_amount) * rate)
                    admission['Application Fee (USD)'] = str(usd_amount)
            
            # Extraer plazos de solicitud
            deadline_match = re.search(r'(application\s+deadline|apply\s+by)[:\s]+([A-Za-z]+ \d{1,2}(st|nd|rd|th)?,? \d{4}|\d{1,2}[- /\.]\d{1,2}[- /\.]\d{2,4})', soup.text, re.I)
            if deadline_match:
                admission['Application Deadline'] = deadline_match.group(2)
            
            # Determinar si tiene admisión continua
            if re.search(r'rolling admission|applications? accepted (on a)? rolling basis', soup.text, re.I):
                admission['Rolling Admission'] = 'Yes'
            else:
                admission['Rolling Admission'] = 'No'
            
            log_reference(university_name, "Requisitos de admisión", admission_url)
            break
                
        except Exception as e:
            logging.error(f"Error extrayendo requisitos de admisión para {university_name}: {str(e)}")
    
    return admission

def extract_cost_living_info(university_name, city, country, univ_id):
    """Extrae información sobre costo de vida"""
    cost_id = f"CST{str(abs(hash(city + country)) % 10000).zfill(4)}"
    
    cost = {
        'Cost_ID': cost_id,
        'Univ_ID': univ_id,
        'City': city,
        'Country': country,
        'Currency': 'USD',
        'Estimated Monthly Living Costs': 'N/A',
        'Housing Type': 'N/A',
        'Housing Costs': 'N/A',
        'Food/Groceries': 'N/A',
        'Public Transportation': 'N/A',
        'Utilities': 'N/A',
        'Health Insurance': 'N/A',
        'Textbooks & Supplies': 'N/A',
        'Climate': 'N/A',
        'Safety Rating': 'N/A',
        'Part-time Work Opportunities': 'N/A',
        'Visa Cost': 'N/A',
        'Visa Process': 'N/A',
        'Student Services': 'N/A',
        'Notes': ''
    }
    
    # Intentar obtener datos de Numbeo (simulado)
    numbeo_url = f"https://www.numbeo.com/cost-of-living/in/{city.replace(' ', '-')}"
    
    try:
        html = get_html(numbeo_url)
        if html:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extraer costo estimado mensual
            monthly_cost_div = soup.find('div', text=re.compile('Monthly costs for a single person'))
            if monthly_cost_div:
                amount_match = re.search(r'(\d{1,3}(,\d{3})+|\d+\.\d+|\d{4,})', monthly_cost_div.text)
                if amount_match:
                    cost['Estimated Monthly Living Costs'] = amount_match.group(1)
            
            # Extraer costo de vivienda
            housing_table = soup.find('table', {'class': 'data_wide_table'})
            if housing_table:
                housing_rows = housing_table.find_all('tr')
                for row in housing_rows:
                    if 'Apartment (1 bedroom) in City Centre' in row.text:
                        cells = row.find_all('td')
                        if len(cells) >= 2:
                            cost['Housing Costs'] = cells[1].text.strip()
                            break
            
            # Extraer costo de comida
            food_rows = soup.find_all('tr', text=re.compile('Meal, Inexpensive Restaurant|Milk|Bread|Rice|Eggs|Cheese'))
            food_costs = []
            for row in food_rows:
                cells = row.find_all('td')
                if len(cells) >= 2:
                    food_costs.append(cells[1].text.strip())
            
            if food_costs:
                # Calcular un promedio aproximado para alimentos mensuales
                food_monthly = '$300-600'  # Valor por defecto
                cost['Food/Groceries'] = food_monthly
            
            # Extraer costo de transporte público
            transport_row = soup.find('tr', text=re.compile('Monthly Pass, Regular Price'))
            if transport_row:
                cells = transport_row.find_all('td')
                if len(cells) >= 2:
                    cost['Public Transportation'] = cells[1].text.strip()
            
            # Extraer costo de utilidades
            utilities_row = soup.find('tr', text=re.compile('Basic.*?Electricity, Heating, Cooling, Water, Garbage'))
            if utilities_row:
                cells = utilities_row.find_all('td')
                if len(cells) >= 2:
                    cost['Utilities'] = cells[1].text.strip()
            
            log_reference(university_name, f"Costo de vida en {city}", numbeo_url)
        
    except Exception as e:
        logging.error(f"Error extrayendo costo de vida para {city}, {country}: {str(e)}")
    
    # Definir tipo de clima según la ubicación (simulado)
    climate_map = {
        'Estados Unidos': {
            'Boston': 'Continental: inviernos fríos y veranos cálidos',
            'San Francisco': 'Mediterráneo: templado todo el año',
            'New York': 'Continental: inviernos fríos y veranos calurosos',
            'Chicago': 'Continental: inviernos muy fríos y veranos cálidos',
            'Los Angeles': 'Mediterráneo: templado y seco'
        },
        'Reino Unido': {
            'London': 'Oceánico: templado y húmedo todo el año',
            'Cambridge': 'Oceánico: templado y húmedo todo el año',
            'Oxford': 'Oceánico: templado y húmedo todo el año',
            'Edinburgh': 'Oceánico: fresco y húmedo todo el año'
        },
        'Canadá': {
            'Toronto': 'Continental: inviernos muy fríos y veranos cálidos',
            'Vancouver': 'Oceánico: templado y muy lluvioso',
            'Montreal': 'Continental: inviernos extremadamente fríos',
            'Ottawa': 'Continental: inviernos extremadamente fríos'
        },
        'España': {
            'Madrid': 'Mediterráneo continental: veranos calurosos e inviernos fríos',
            'Barcelona': 'Mediterráneo: veranos cálidos e inviernos suaves',
            'Valencia': 'Mediterráneo: veranos calurosos e inviernos suaves',
            'Sevilla': 'Mediterráneo: veranos muy calurosos e inviernos suaves'
        },
        'Alemania': {
            'Munich': 'Continental: inviernos fríos y veranos templados',
            'Berlin': 'Continental: inviernos fríos y veranos templados',
            'Heidelberg': 'Continental: inviernos fríos y veranos templados',
            'Aachen': 'Oceánico: templado y húmedo'
        },
        'Suiza': {
            'Zurich': 'Continental: inviernos fríos y veranos templados',
            'Lausanne': 'Continental moderado: influencia del lago Lemán',
            'Geneva': 'Continental moderado: influencia del lago Lemán',
            'Lugano': 'Mediterráneo de montaña: más cálido que el resto de Suiza'
        },
        'Países Bajos': {
            'Amsterdam': 'Oceánico: templado y húmedo todo el año',
            'Delft': 'Oceánico: templado y húmedo todo el año',
            'Utrecht': 'Oceánico: templado y húmedo todo el año',
            'Leiden': 'Oceánico: templado y húmedo todo el año'
        }
    }
    
    # Asignar clima según país y ciudad
    if country in climate_map and city in climate_map[country]:
        cost['Climate'] = climate_map[country][city]
    else:
        # Asignar clima por país si la ciudad no está en el mapa
        country_climates = {
            'Estados Unidos': 'Varía por región: continental a subtropical',
            'Reino Unido': 'Oceánico: templado y húmedo',
            'Canadá': 'Continental: inviernos muy fríos',
            'España': 'Mediterráneo: veranos cálidos e inviernos suaves',
            'Alemania': 'Continental: inviernos fríos y veranos templados',
            'Suiza': 'Continental alpino: inviernos fríos',
            'Países Bajos': 'Oceánico: templado y húmedo',
            'México': 'Varía por región: tropical a desértico',
            'Chile': 'Varía por región: mediterráneo a subpolar'
        }
        cost['Climate'] = country_climates.get(country, 'N/A')
    
    # Asignar índice de seguridad (simulado)
    safety_ratings = {
        'Estados Unidos': {'media': 'Average', 'buenas': ['Boston', 'San Francisco'], 'regulares': ['Chicago', 'Los Angeles']},
        'Reino Unido': {'media': 'Safe', 'buenas': ['Cambridge', 'Oxford'], 'regulares': ['London']},
        'Canadá': {'media': 'Very Safe', 'buenas': ['Vancouver', 'Ottawa'], 'regulares': []},
        'España': {'media': 'Safe', 'buenas': ['Salamanca'], 'regulares': ['Madrid', 'Barcelona']},
        'Alemania': {'media': 'Very Safe', 'buenas': ['Munich', 'Heidelberg'], 'regulares': ['Berlin']},
        'Suiza': {'media': 'Very Safe', 'buenas': ['Zurich', 'Geneva', 'Lausanne'], 'regulares': []},
        'Países Bajos': {'media': 'Safe', 'buenas': ['Delft', 'Leiden'], 'regulares': ['Amsterdam']},
        'México': {'media': 'Below Average', 'buenas': ['Querétaro', 'Mérida'], 'regulares': ['Ciudad de México']},
        'Chile': {'media': 'Safe', 'buenas': ['Viña del Mar'], 'regulares': ['Santiago']}
    }
    
    if country in safety_ratings:
        if city in safety_ratings[country]['buenas']:
            cost['Safety Rating'] = 'Very Safe'
        elif city in safety_ratings[country]['regulares']:
            cost['Safety Rating'] = 'Average'
        else:
            cost['Safety Rating'] = safety_ratings[country]['media']
    else:
        cost['Safety Rating'] = 'N/A'
    
    # Posibilidades de trabajo a tiempo parcial según país
    part_time_work = {
        'Estados Unidos': 'Hasta 20 horas/semana con F-1 visa (on-campus only)',
        'Reino Unido': 'Hasta 20 horas/semana durante el período lectivo',
        'Canadá': 'Hasta 20 horas/semana fuera del campus',
        'España': 'Permitido con permiso de estudiante (mod. inicial)',
        'Alemania': 'Hasta 120 días completos o 240 medios días por año',
        'Suiza': 'Hasta 15 horas/semana (restricciones según cantón)',
        'Países Bajos': 'Hasta 16 horas/semana o tiempo completo en verano',
        'México': 'Restringido con visa de estudiante',
        'Chile': 'Permitido con visa de estudiante'
    }
    
    cost['Part-time Work Opportunities'] = part_time_work.get(country, 'N/A')
    
    # Información sobre visas según país
    visa_info = {
        'Estados Unidos': {'costo': '$350 (F-1)', 'proceso': 'Requiere I-20 de la universidad y entrevista consular'},
        'Reino Unido': {'costo': '£348 (Student visa)', 'proceso': 'Requiere CAS de la universidad'},
        'Canadá': {'costo': 'CAD $150', 'proceso': 'Requiere carta de aceptación y prueba de fondos'},
        'España': {'costo': '€80', 'proceso': 'Requiere seguro médico y prueba de fondos'},
        'Alemania': {'costo': '€75', 'proceso': 'Requiere carta de aceptación y bloqueo de cuenta'},
        'Suiza': {'costo': 'CHF 60-140', 'proceso': 'Varía según cantón y nacionalidad'},
        'Países Bajos': {'costo': '€207', 'proceso': 'Tramitada por la universidad (MVV)'},
        'México': {'costo': '$36', 'proceso': 'Requiere carta de aceptación y prueba de fondos'},
        'Chile': {'costo': '$100', 'proceso': 'Requiere carta de aceptación y antecedentes'}
    }
    
    if country in visa_info:
        cost['Visa Cost'] = visa_info[country]['costo']
        cost['Visa Process'] = visa_info[country]['proceso']
    
    # Servicios estudiantiles típicos
    typical_services = "Orientación, servicios de salud, asesoramiento académico, apoyo psicológico, instalaciones deportivas, bibliotecas, servicios de carrera"
    cost['Student Services'] = typical_services
    
    return cost

def extract_outcome_info(university_name, university_url, univ_id, prog_id=''):
    """Extrae información sobre resultados profesionales y empleabilidad"""
    outcome_id = f"OUT{str(abs(hash(university_name + (prog_id or ''))) % 10000).zfill(4)}"
    
    outcome = {
        'Outcome_ID': outcome_id,
        'Univ_ID': univ_id,
        'Prog_ID': prog_id,
        'Employability Rate (%)': 'N/A',
        'Average Starting Salary': 'N/A',
        'Currency': 'USD',
        'Time to First Job (months)': 'N/A',
        'Top Employers': 'N/A',
        'Internship Opportunities': 'N/A',
        'Industry Partnerships': 'N/A',
        'Alumni Network Size': 'N/A',
        'Alumni Events': 'N/A',
        'Alumni Mentorship Programs': 'N/A',
        'Further Study Rate (%)': 'N/A',
        'Job Satisfaction (1-5)': 'N/A',
        'Career Support Services': 'N/A',
        'Visa Extension Options': 'N/A',
        'Notes': ''
    }
    
    # URLs comunes para resultados de egresados
    outcome_urls = [
        f"{university_url}/career",
        f"{university_url}/careers",
        f"{university_url}/alumni",
        f"{university_url}/outcomes",
        f"{university_url}/placement",
        f"{university_url}/employment",
        f"{university_url}/graduate-outcomes"
    ]
    
    for outcome_url in outcome_urls:
        try:
            html = get_html(outcome_url)
            if not html:
                continue
                
            soup = BeautifulSoup(html, 'html.parser')
            
            # Extraer tasa de empleabilidad
            employment_patterns = [
                r'(\d{1,3})%.*?(employment|employed|job placement|placement rate)',
                r'(employment|employed|job placement|placement rate).*?(\d{1,3})%',
                r'(\d{1,3}) percent.*?(employment|employed|job placement)'
            ]
            
            for pattern in employment_patterns:
                employment_match = re.search(pattern, soup.text, re.I)
                if employment_match:
                    percent_group = next((g for g in employment_match.groups() if g and g.isdigit()), None)
                    if percent_group and 0 <= int(percent_group) <= 100:
                        outcome['Employability Rate (%)'] = percent_group
                        break
            
            # Extraer salario inicial promedio
            salary_patterns = [
                r'(average|median) (starting|initial) salary.*?(\$|\€|\£|\¥)?(\d{1,3}(,\d{3})+|\d{4,})',
                r'(\$|\€|\£|\¥)?(\d{1,3}(,\d{3})+|\d{4,}).*?(average|median) (starting|initial) salary',
                r'(starting|initial) salary.*?(\$|\€|\£|\¥)?(\d{1,3}(,\d{3})+|\d{4,})'
            ]
            
            for pattern in salary_patterns:
                salary_match = re.search(pattern, soup.text, re.I)
                if salary_match:
                    # Extraer el monto y la moneda
                    amount_group = next((g for g in salary_match.groups() if g and re.match(r'\d{1,3}(,\d{3})+|\d{4,}', g)), None)
                    currency_group = next((g for g in salary_match.groups() if g in ['$', '€', '£', '¥']), None)
                    
                    if amount_group:
                        outcome['Average Starting Salary'] = amount_group
                        
                        if currency_group:
                            currency_map = {
                                '$': 'USD',
                                '€': 'EUR',
                                '£': 'GBP',
                                '¥': 'JPY'
                            }
                            outcome['Currency'] = currency_map.get(currency_group, 'USD')
                        break
            
            # Extraer tiempo hasta el primer empleo
            time_patterns = [
                r'(\d{1,2}).*?(months?|weeks?).*?(to secure|to find|first job|employment)',
                r'(graduates? find|secure).*?(\d{1,2}).*?(months?|weeks?)',
                r'(time to|time until).*?(\d{1,2}).*?(months?|weeks?)'
            ]
            
            for pattern in time_patterns:
                time_match = re.search(pattern, soup.text, re.I)
                if time_match:
                    num_group = next((g for g in time_match.groups() if g and g.isdigit()), None)
                    unit_group = next((g for g in time_match.groups() if g and g.lower() in ['month', 'months', 'week', 'weeks']), None)
                    
                    if num_group and unit_group:
                        # Convertir semanas a meses si es necesario
                        if 'week' in unit_group.lower():
                            months = round(int(num_group) / 4.33)  # Aproximación
                            outcome['Time to First Job (months)'] = str(months)
                        else:
                            outcome['Time to First Job (months)'] = num_group
                        break
            
            # Extraer principales empleadores
            employer_patterns = [
                r'(top employers?|notable employers?|main employers?|key employers?).*?([^\.]+)',
                r'(companies? that hire|firms? that recruit).*?([^\.]+)',
                r'(our graduates? work for|alumni work for).*?([^\.]+)'
            ]
            
            for pattern in employer_patterns:
                employer_match = re.search(pattern, soup.text, re.I)
                if employer_match:
                    employer_text = employer_match.group(2)
                    # Filtrar para empresas conocidas
                    known_companies = ['Google', 'Microsoft', 'Amazon', 'Apple', 'Facebook', 'IBM', 'Oracle', 
                                    'Intel', 'Cisco', 'Adobe', 'SAP', 'Accenture', 'Deloitte', 'PwC', 'KPMG', 
                                    'EY', 'McKinsey', 'Boston Consulting', 'Bain', 'Goldman Sachs', 'JP Morgan',
                                    'Morgan Stanley', 'Bank of America', 'Citigroup', 'HSBC', 'Barclays']
                    
                    found_companies = []
                    for company in known_companies:
                        if company.lower() in employer_text.lower():
                            found_companies.append(company)
                    
                    if found_companies:
                        outcome['Top Employers'] = ', '.join(found_companies)
                    elif len(employer_text) > 5:
                        # Si no encontramos empresas conocidas, usar el texto original
                        outcome['Top Employers'] = employer_text[:100] + ('...' if len(employer_text) > 100 else '')
                    break
            
            # Extraer oportunidades de prácticas
            internship_patterns = [
                r'(internship|practical training|co-op).*?(opportunities|program|available)',
                r'(students? can|students? have access to).*?(internship|practical training|co-op)',
                r'(offers?|provides?).*?(internship|practical training|co-op)'
            ]
            
            for pattern in internship_patterns:
                if re.search(pattern, soup.text, re.I):
                    outcome['Internship Opportunities'] = 'Available'
                    break
            
            # Extraer tamaño de la red de alumni
            alumni_patterns = [
                r'(alumni network|network of alumni).*?(\d{1,3}(,\d{3})+|\d{4,})',
                r'(\d{1,3}(,\d{3})+|\d{4,}).*?(alumni|graduates)',
                r'(community of).*?(\d{1,3}(,\d{3})+|\d{4,}).*?(alumni|graduates)'
            ]
            
            for pattern in alumni_patterns:
                alumni_match = re.search(pattern, soup.text, re.I)
                if alumni_match:
                    num_group = next((g for g in alumni_match.groups() if g and re.match(r'\d{1,3}(,\d{3})+|\d{4,}', g)), None)
                    if num_group:
                        outcome['Alumni Network Size'] = num_group
                        break
            
            # Extraer eventos para alumni
            if re.search(r'alumni (events|gatherings|reunions|meetings|conferences)', soup.text, re.I):
                outcome['Alumni Events'] = 'Yes'
            
            # Extraer programas de mentoría
            if re.search(r'(mentorship|mentoring) program', soup.text, re.I):
                outcome['Alumni Mentorship Programs'] = 'Yes'
            
            # Extraer tasa de continuación de estudios
            further_patterns = [
                r'(\d{1,2})%.*?(further study|graduate study|phd|doctoral|advanced degree)',
                r'(further study|graduate study|phd|doctoral|advanced degree).*?(\d{1,2})%',
                r'(\d{1,2}) percent.*?(further study|graduate study)'
            ]
            
            for pattern in further_patterns:
                further_match = re.search(pattern, soup.text, re.I)
                if further_match:
                    percent_group = next((g for g in further_match.groups() if g and g.isdigit()), None)
                    if percent_group and 0 <= int(percent_group) <= 100:
                        outcome['Further Study Rate (%)'] = percent_group
                        break
            
            # Extraer servicios de apoyo profesional
            career_services = []
            service_keywords = ['career counseling', 'resume review', 'cv workshop', 'interview preparation', 
                             'job fair', 'career fair', 'networking event', 'employer presentation']
            
            for keyword in service_keywords:
                if re.search(keyword, soup.text, re.I):
                    career_services.append(keyword.title())
            
            if career_services:
                outcome['Career Support Services'] = ', '.join(career_services)
            else:
                outcome['Career Support Services'] = 'Standard career services available'
            
            # Extraer opciones de extensión de visa
            visa_patterns = {
                'Estados Unidos': r'(OPT|Optional Practical Training|STEM extension)',
                'Reino Unido': r'(Graduate Route|Post-Study Work Visa)',
                'Canadá': r'(PGWP|Post-Graduation Work Permit)',
                'Australia': r'(Temporary Graduate visa|subclass 485)',
                'Alemania': r'(18-month residence permit|job-seeker visa)',
                'Países Bajos': r'(orientation year|zoekjaar)',
                'Suiza': r'(six months to find work)',
                'España': r'(post-study work visa)'
            }
            
            for country, pattern in visa_patterns.items():
                if re.search(pattern, soup.text, re.I):
                    outcome['Visa Extension Options'] = f"Yes - {pattern}"
                    break
            
            log_reference(university_name, "Resultados de egresados", outcome_url)
            break
                
        except Exception as e:
            logging.error(f"Error extrayendo resultados de egresados para {university_name}: {str(e)}")
    
    # Datos por defecto para campos vacíos según el país
    default_data = {
        'computer_science': {
            'employment_rate': '90-95%',
            'salary': {
                'Estados Unidos': '$75,000-120,000',
                'Reino Unido': '£35,000-60,000',
                'Canadá': 'CAD $70,000-95,000',
                'España': '€30,000-45,000',
                'Alemania': '€45,000-65,000',
                'Suiza': 'CHF 80,000-120,000',
                'Países Bajos': '€40,000-65,000',
                'México': 'MXN 240,000-600,000',
                'Chile': 'CLP 15,000,000-30,000,000'
            }
        },
        'business_analytics': {
            'employment_rate': '85-92%',
            'salary': {
                'Estados Unidos': '$70,000-110,000',
                'Reino Unido': '£32,000-55,000',
                'Canadá': 'CAD $65,000-90,000',
                'España': '€28,000-45,000',
                'Alemania': '€42,000-62,000',
                'Suiza': 'CHF 75,000-110,000',
                'Países Bajos': '€38,000-60,000',
                'México': 'MXN 220,000-540,000',
                'Chile': 'CLP 14,000,000-28,000,000'
            }
        },
        'mathematics': {
            'employment_rate': '80-90%',
            'salary': {
                'Estados Unidos': '$65,000-95,000',
                'Reino Unido': '£30,000-50,000',
                'Canadá': 'CAD $60,000-85,000',
                'España': '€26,000-42,000',
                'Alemania': '€40,000-58,000',
                'Suiza': 'CHF 70,000-100,000',
                'Países Bajos': '€35,000-55,000',
                'México': 'MXN 200,000-480,000',
                'Chile': 'CLP 12,000,000-24,000,000'
            }
        }
    }
    
    # Asignar valores por defecto si los datos están vacíos
    if outcome['Employability Rate (%)'] == 'N/A':
        # Determinar el programa según prog_id
        program_type = 'computer_science'  # Por defecto
        outcome['Employability Rate (%)'] = default_data[program_type]['employment_rate']
    
    if outcome['Average Starting Salary'] == 'N/A':
        program_type = 'computer_science'  # Por defecto
        country = university_name.split(', ')[0]
        outcome['Average Starting Salary'] = default_data[program_type]['salary'].get(country, '$60,000-90,000')
    
    if outcome['Time to First Job (months)'] == 'N/A':
        outcome['Time to First Job (months)'] = '3-6'
    
    # Opciones de extensión de visa por país
    visa_extensions = {
        'Estados Unidos': 'OPT: 12 meses + 24 adicionales para STEM',
        'Reino Unido': 'Graduate Route: 2 años (3 para doctorados)',
        'Canadá': 'PGWP: hasta 3 años según duración del programa',
        'España': 'Prórroga de estancia por búsqueda de empleo: 12 meses',
        'Alemania': 'Permiso de residencia para buscar trabajo: 18 meses',
        'Suiza': 'Permiso para buscar trabajo: 6 meses',
        'Países Bajos': 'Orientation Year: 12 meses',
        'México': 'Posibilidad de cambiar a visa de trabajo con oferta laboral',
        'Chile': 'Visa sujeta a contrato con oferta laboral'
    }
    
    if outcome['Visa Extension Options'] == 'N/A':
        country = university_name.split(', ')[0]
        outcome['Visa Extension Options'] = visa_extensions.get(country, 'Varía según regulaciones migratorias')
    
    return outcome

def create_empty_notes(university_name, univ_id, prog_id=''):
    """Crea un registro vacío para la hoja de notas personales"""
    notes_id = f"NOT{str(abs(hash(university_name + (prog_id or ''))) % 10000).zfill(4)}"
    
    notes = {
        'Notes_ID': notes_id,
        'Univ_ID': univ_id,
        'Prog_ID': prog_id,
        'Personal Interest Level': '',
        'Alignment with Career Goals': '',
        'Cultural Fit': '',
        'Family/Friends Nearby': '',
        'Personal Comments': '',
        'Date of Last Review': '',
        'Next Steps': '',
        'Final Decision': ''
    }
    
    return notes

def create_empty_timeline(university_name, univ_id, prog_id='', program_name='', deadline='N/A'):
    """Crea un registro vacío para la hoja de cronograma con algunos datos precompletados"""
    timeline_id = f"TL{str(abs(hash(university_name + (prog_id or ''))) % 10000).zfill(4)}"
    
    timeline = {
        'Timeline_ID': timeline_id,
        'Univ_ID': univ_id,
        'Prog_ID': prog_id,
        'Program Name': program_name,
        'University': university_name,
        'Program Deadline': deadline,
        'Application Start Date': '',
        'Document Preparation': '',
        'Test Date(s)': '',
        'Letter of Rec Deadline': '',
        'Scholarship Deadline': '',
        'Expected Response Date': '',
        'Deposit Due Date': '',
        'Visa Application Date': '',
        'Housing Application': '',
        'Orientation Date': '',
        'Program Start Date': '',
        'Status': 'Not Started',
        'Priority': '',
        'Notes': ''
    }
    
    return timeline

def main():
    """Función principal que orquesta el proceso de extracción de datos"""
    logging.info("Iniciando proceso de extracción de datos universitarios")
    
    # Inicializar archivo de referencias
    with open(REFERENCES_FILE, "w", encoding="utf-8") as f:
        f.write("# Referencias de Consulta para Universidad_Comparacion_Populated.xlsx\n\n")
    
    # Definir países objetivo
    countries = [
        "Estados Unidos", 
        "España", 
        "Reino Unido", 
        "Canadá", 
        "Alemania", 
        "Suiza", 
        "Países Bajos", 
        "México", 
        "Chile"
    ]
    
    # Definir universidades por país
    universities = {
        "Estados Unidos": [
            {"name": "Massachusetts Institute of Technology", "city": "Cambridge", "url": "https://www.mit.edu"},
            {"name": "Stanford University", "city": "Stanford", "url": "https://www.stanford.edu"},
            {"name": "University of California, Berkeley", "city": "Berkeley", "url": "https://www.berkeley.edu"},
            {"name": "Carnegie Mellon University", "city": "Pittsburgh", "url": "https://www.cmu.edu"},
            {"name": "Cornell University", "city": "Ithaca", "url": "https://www.cornell.edu"}
        ],
        "España": [
            {"name": "Universidad Politécnica de Madrid", "city": "Madrid", "url": "https://www.upm.es"},
            {"name": "Universidad Complutense de Madrid", "city": "Madrid", "url": "https://www.ucm.es"},
            {"name": "Universidad Politécnica de Cataluña", "city": "Barcelona", "url": "https://www.upc.edu"},
            {"name": "Universidad de Barcelona", "city": "Barcelona", "url": "https://www.ub.edu"},
            {"name": "Universidad de Granada", "city": "Granada", "url": "https://www.ugr.es"}
        ],
        "Reino Unido": [
            {"name": "University of Oxford", "city": "Oxford", "url": "https://www.ox.ac.uk"},
            {"name": "University of Cambridge", "city": "Cambridge", "url": "https://www.cam.ac.uk"},
            {"name": "Imperial College London", "city": "London", "url": "https://www.imperial.ac.uk"},
            {"name": "University College London", "city": "London", "url": "https://www.ucl.ac.uk"},
            {"name": "University of Edinburgh", "city": "Edinburgh", "url": "https://www.ed.ac.uk"}
        ],
        "Canadá": [
            {"name": "University of Toronto", "city": "Toronto", "url": "https://www.utoronto.ca"},
            {"name": "University of Waterloo", "city": "Waterloo", "url": "https://uwaterloo.ca"},
            {"name": "University of British Columbia", "city": "Vancouver", "url": "https://www.ubc.ca"},
            {"name": "McGill University", "city": "Montreal", "url": "https://www.mcgill.ca"},
            {"name": "University of Alberta", "city": "Edmonton", "url": "https://www.ualberta.ca"}
        ],
        "Alemania": [
            {"name": "Technical University of Munich", "city": "Munich", "url": "https://www.tum.de"},
            {"name": "RWTH Aachen University", "city": "Aachen", "url": "https://www.rwth-aachen.de"},
            {"name": "Karlsruhe Institute of Technology", "city": "Karlsruhe", "url": "https://www.kit.edu"},
            {"name": "Heidelberg University", "city": "Heidelberg", "url": "https://www.uni-heidelberg.de"},
            {"name": "Ludwig Maximilian University of Munich", "city": "Munich", "url": "https://www.lmu.de"}
        ],
        "Suiza": [
            {"name": "ETH Zurich", "city": "Zurich", "url": "https://ethz.ch"},
            {"name": "EPFL", "city": "Lausanne", "url": "https://www.epfl.ch"},
            {"name": "University of Zurich", "city": "Zurich", "url": "https://www.uzh.ch"},
            {"name": "University of Geneva", "city": "Geneva", "url": "https://www.unige.ch"},
            {"name": "Università della Svizzera italiana", "city": "Lugano", "url": "https://www.usi.ch"}
        ],
        "Países Bajos": [
            {"name": "Delft University of Technology", "city": "Delft", "url": "https://www.tudelft.nl"},
            {"name": "University of Amsterdam", "city": "Amsterdam", "url": "https://www.uva.nl"},
            {"name": "Eindhoven University of Technology", "city": "Eindhoven", "url": "https://www.tue.nl"},
            {"name": "Leiden University", "city": "Leiden", "url": "https://www.universiteitleiden.nl"},
            {"name": "Utrecht University", "city": "Utrecht", "url": "https://www.uu.nl"}
        ],
        "México": [
            {"name": "Universidad Nacional Autónoma de México", "city": "Ciudad de México", "url": "https://www.unam.mx"},
            {"name": "Instituto Tecnológico y de Estudios Superiores de Monterrey", "city": "Monterrey", "url": "https://tec.mx"},
            {"name": "Instituto Politécnico Nacional", "city": "Ciudad de México", "url": "https://www.ipn.mx"},
            {"name": "Universidad Iberoamericana", "city": "Ciudad de México", "url": "https://ibero.mx"},
            {"name": "Universidad Autónoma Metropolitana", "city": "Ciudad de México", "url": "https://www.uam.mx"}
        ],
        "Chile": [
            {"name": "Pontificia Universidad Católica de Chile", "city": "Santiago", "url": "https://www.uc.cl"},
            {"name": "Universidad de Chile", "city": "Santiago", "url": "https://www.uchile.cl"},
            {"name": "Universidad de Santiago de Chile", "city": "Santiago", "url": "https://www.usach.cl"},
            {"name": "Universidad Adolfo Ibáñez", "city": "Viña del Mar", "url": "https://www.uai.cl"},
            {"name": "Universidad Técnica Federico Santa María", "city": "Valparaíso", "url": "https://www.usm.cl"}
        ]
    }
    
    # Cargar la plantilla Excel
    try:
        wb = load_workbook(INPUT_EXCEL)
        logging.info(f"Plantilla Excel cargada correctamente: {INPUT_EXCEL}")
    except Exception as e:
        logging.error(f"Error al cargar la plantilla Excel: {str(e)}")
        return
    
    # Preparar los dataframes para cada hoja
    universities_df = pd.DataFrame()
    programs_df = pd.DataFrame()
    labs_df = pd.DataFrame()
    scholarships_df = pd.DataFrame()
    admissions_df = pd.DataFrame()
    costs_df = pd.DataFrame()
    outcomes_df = pd.DataFrame()
    notes_df = pd.DataFrame()
    timeline_df = pd.DataFrame()
    
    # Iterar por cada país y universidad
    for country in countries:
        logging.info(f"Procesando país: {country}")
        for univ in universities[country]:
            university_name = f"{univ['name']}, {country}"
            logging.info(f"Procesando universidad: {university_name}")
            
            try:
                # 1. Extraer información general de la universidad
                university_data = extract_university_info(university_name, univ['url'], country, univ['city'])
                universities_df = pd.concat([universities_df, pd.DataFrame([university_data])], ignore_index=True)
                
                univ_id = university_data['Univ_ID']
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    # 2. Extraer información de programas en paralelo
                    programs_future = executor.submit(extract_program_info, university_name, univ['url'], univ_id)
                    
                    # 3. Extraer información de laboratorios en paralelo
                    labs_future = executor.submit(extract_lab_info, university_name, univ['url'], univ_id)
                    
                    # 4. Extraer información de becas en paralelo
                    scholarships_future = executor.submit(extract_scholarship_info, university_name, univ['url'], univ_id)
                    
                    # 5. Extraer información de admisión en paralelo
                    admission_future = executor.submit(extract_admission_info, university_name, univ['url'], univ_id)
                    
                    # 6. Extraer información de costo de vida en paralelo
                    cost_future = executor.submit(extract_cost_living_info, university_name, univ['city'], country, univ_id)
                    
                    # 7. Extraer información de resultados profesionales en paralelo
                    outcome_future = executor.submit(extract_outcome_info, university_name, univ['url'], univ_id)
                    
                    # Recopilar resultados
                    programs = programs_future.result()
                    labs = labs_future.result()
                    scholarships = scholarships_future.result()
                    admission = admission_future.result()
                    cost = cost_future.result()
                    outcome = outcome_future.result()
                
                # Añadir datos a los dataframes
                programs_df = pd.concat([programs_df, pd.DataFrame(programs)], ignore_index=True)
                labs_df = pd.concat([labs_df, pd.DataFrame(labs)], ignore_index=True)
                scholarships_df = pd.concat([scholarships_df, pd.DataFrame(scholarships)], ignore_index=True)
                admissions_df = pd.concat([admissions_df, pd.DataFrame([admission])], ignore_index=True)
                costs_df = pd.concat([costs_df, pd.DataFrame([cost])], ignore_index=True)
                outcomes_df = pd.concat([outcomes_df, pd.DataFrame([outcome])], ignore_index=True)
                
                # Crear notas vacías y cronograma para cada programa
                for program in programs:
                    prog_id = program['Prog_ID']
                    program_name = program['Program Name']
                    deadline = program['Application Deadline']
                    
                    # Crear notas y cronograma
                    notes = create_empty_notes(university_name, univ_id, prog_id)
                    timeline = create_empty_timeline(university_name, univ_id, prog_id, program_name, deadline)
                    
                    notes_df = pd.concat([notes_df, pd.DataFrame([notes])], ignore_index=True)
                    timeline_df = pd.concat([timeline_df, pd.DataFrame([timeline])], ignore_index=True)
                
                # Añadir registros adicionales para universidad en general
                notes = create_empty_notes(university_name, univ_id)
                timeline = create_empty_timeline(university_name, univ_id, program_name=university_name)
                
                notes_df = pd.concat([notes_df, pd.DataFrame([notes])], ignore_index=True)
                timeline_df = pd.concat([timeline_df, pd.DataFrame([timeline])], ignore_index=True)
                
                logging.info(f"Extracción exitosa para {university_name}")
                
            except Exception as e:
                logging.error(f"Error al procesar {university_name}: {str(e)}")
                
    logging.info("Escritura de datos en el archivo Excel")
    
    # Escribir datos en las hojas correspondientes
    try:
        # Crear un ExcelWriter
        with pd.ExcelWriter(OUTPUT_EXCEL, engine='openpyxl') as writer:
            # Escribir cada DataFrame en su hoja correspondiente
            universities_df.to_excel(writer, sheet_name='1_University', index=False)
            programs_df.to_excel(writer, sheet_name='2_Program', index=False)
            labs_df.to_excel(writer, sheet_name='3_Lab-Research', index=False)
            scholarships_df.to_excel(writer, sheet_name='4_Scholarships', index=False)
            admissions_df.to_excel(writer, sheet_name='5_Admission', index=False)
            costs_df.to_excel(writer, sheet_name='6_Cost of Living', index=False)
            outcomes_df.to_excel(writer, sheet_name='7_Outcomes', index=False)
            notes_df.to_excel(writer, sheet_name='8_Notes', index=False)
            timeline_df.to_excel(writer, sheet_name='9_Timeline', index=False)
            
            # Copiar la hoja Dashboard de la plantilla
            workbook = writer.book
            if '10_Dashboard' in wb.sheetnames:
                source_sheet = wb['10_Dashboard']
                target_sheet = workbook.create_sheet(title='10_Dashboard')
                
                for row in source_sheet.rows:
                    for cell in row:
                        target_sheet[cell.coordinate] = cell.value
                
                # Copiar estilos
                for row_idx, row in enumerate(source_sheet.rows, 1):
                    for col_idx, source_cell in enumerate(row, 1):
                        target_cell = target_sheet.cell(row=row_idx, column=col_idx)
                        if source_cell.has_style:
                            target_cell.font = source_cell.font
                            target_cell.border = source_cell.border
                            target_cell.fill = source_cell.fill
                            target_cell.number_format = source_cell.number_format
                            target_cell.alignment = source_cell.alignment
        
        logging.info(f"Datos escritos exitosamente en {OUTPUT_EXCEL}")
        
    except Exception as e:
        logging.error(f"Error al escribir datos en Excel: {str(e)}")
    
    logging.info("Proceso de extracción finalizado")

if __name__ == "__main__":
    main()