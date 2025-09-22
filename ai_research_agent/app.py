# app.py
import os
import io
import requests
import pypdf
import trafilatura
import google.generativeai as genai
from tavily import TavilyClient
from dotenv import load_dotenv
from datetime import datetime

from flask import Flask, render_template, abort, request, redirect, url_for
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

# --- 1. SETUP ---
# Load environment variables and configure API clients
load_dotenv()
try:
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
    gemini_model = genai.GenerativeModel('gemini-1.5-flash')
except TypeError:
    print("Error: API key not found. Make sure GEMINI_API_KEY and TAVILY_API_KEY are in your .env file.")
    exit()

# Configure Database
DATABASE_URL = "sqlite:///research_reports.db"
engine = create_engine(DATABASE_URL)
Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True, index=True)
    query = Column(String, index=True)
    report_content = Column(Text)
    sources = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(bind=engine)

# --- 2. AGENT CORE LOGIC ---
# These functions are the core of the research agent
def search_online(query: str, max_results=3):
    print(f"🔎 Searching online for: '{query}'...")
    try:
        response = tavily_client.search(query=query, search_depth="basic", max_results=max_results)
        return [obj["url"] for obj in response["results"]]
    except Exception as e:
        print(f"Error during online search: {e}")
        return []

def extract_content_from_url(url: str):
    print(f"🕸️  Scraping content from: {url}...")
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        if 'application/pdf' in response.headers.get('Content-Type', ''):
            with io.BytesIO(response.content) as f:
                reader = pypdf.PdfReader(f)
                text = "".join(page.extract_text() for page in reader.pages)
        else:
            text = trafilatura.extract(response.text)
        return text
    except Exception as e:
        print(f"❗️ Gracefully skipping URL {url} due to error: {e}")
        return None

def summarize_with_gemini(text: str, query: str):
    if not text: return "Error: No text for summarization."
    print("🤖 Summarizing content with Gemini...")
    prompt = f"""
    Based on the following extracted text and the original user query, create a short, structured report.
    The report must include: A clear title, a brief summary, and a few key bullet points.
    Original User Query: "{query}"
    Extracted Text: --- {text} --- """
    try:
        response = gemini_model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"An error occurred during summarization: {e}"

def save_report_to_db(query: str, report_content: str, sources: list):
    db = SessionLocal()
    try:
        new_report = Report(query=query, report_content=report_content, sources=", ".join(sources))
        db.add(new_report)
        db.commit()
        print(f"💾 Report for query '{query}' saved to database.")
    finally:
        db.close()

def run_agent(query: str):
    urls = search_online(query)
    if not urls: return
    all_content = "".join([content for url in urls if (content := extract_content_from_url(url))])
    if not all_content: return
    final_report = summarize_with_gemini(all_content, query)
    if final_report and not final_report.startswith("Error:"):
        save_report_to_db(query, final_report, urls)

# --- 3. FLASK WEB APP ---
app = Flask(__name__)

@app.route("/")
def index():
    db = SessionLocal()
    reports = db.query(Report).order_by(Report.timestamp.desc()).all()
    db.close()
    return render_template("index.html", reports=reports)

@app.route("/report/<int:report_id>")
def report(report_id):
    db = SessionLocal()
    single_report = db.query(Report).filter(Report.id == report_id).first()
    db.close()
    if single_report is None: abort(404)
    sources_list = single_report.sources.split(", ")
    return render_template("report.html", report=single_report, sources=sources_list)

@app.route("/run", methods=["POST"])
def run():
    query = request.form.get("query")
    if query:
        run_agent(query)
    return redirect(url_for('index'))