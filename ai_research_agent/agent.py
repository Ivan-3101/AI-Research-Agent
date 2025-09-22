# agent.py
import os
import io
import requests
import pypdf
import trafilatura
import google.generativeai as genai
from tavily import TavilyClient
from dotenv import load_dotenv
from datetime import datetime

# --- NEW: DATABASE SETUP (using SQLAlchemy) ---
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

# Define the database connection
DATABASE_URL = "sqlite:///research_reports.db"
engine = create_engine(DATABASE_URL)
Base = declarative_base()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Define the Report table model
class Report(Base):
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True, index=True)
    query = Column(String, index=True)
    report_content = Column(Text)
    sources = Column(Text) # Storing sources as a comma-separated string
    timestamp = Column(DateTime, default=datetime.utcnow)

# Create the table in the database if it doesn't exist
Base.metadata.create_all(bind=engine)
# --- END NEW SECTION ---


# --- 1. SETUP ---
# Load environment variables from .env file
load_dotenv()

# Configure the API clients
try:
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
except TypeError:
    print("Error: One or more API keys not found. Make sure they are in your .env file.")
    exit()

# Instantiate the Gemini model
gemini_model = genai.GenerativeModel('gemini-1.5-flash')


# --- 2. CORE FUNCTIONS ---

def search_online(query: str, max_results=3):
    """Searches online using Tavily and returns a list of URLs."""
    print(f"🔎 Searching online for: '{query}'...")
    try:
        response = tavily_client.search(query=query, search_depth="basic", max_results=max_results)
        return [obj["url"] for obj in response["results"]]
    except Exception as e:
        print(f"Error during online search: {e}")
        return []

def extract_content_from_url(url: str):
    """Extracts clean text content from a given URL (handles HTML and PDF)."""
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
    """Uses Gemini to summarize the text into a structured report."""
    if not text:
        return "Error: No text was extracted for summarization."
    
    print("🤖 Summarizing content with Gemini...")
    prompt = f"""
    Based on the following extracted text and the original user query, create a short, structured report.
    The report must include:
    1. A clear, relevant title.
    2. A brief summary of the main topics.
    3. A few key bullet points highlighting the most important findings.

    Original User Query: "{query}"

    Extracted Text:
    ---
    {text}
    ---
    """
    try:
        response = gemini_model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"An error occurred during summarization: {e}"

# --- NEW: Function to save report to the database ---
def save_report_to_db(query: str, report_content: str, sources: list):
    """Saves the generated report and its metadata to the SQLite database."""
    db = SessionLocal()
    try:
        new_report = Report(
            query=query,
            report_content=report_content,
            sources=", ".join(sources) # Join list of URLs into a single string
        )
        db.add(new_report)
        db.commit()
        db.refresh(new_report)
        print(f"💾 Report for query '{query}' saved to database.")
    except Exception as e:
        print(f"Error saving report to database: {e}")
        db.rollback()
    finally:
        db.close()
# --- END NEW SECTION ---


# --- 3. MAIN WORKFLOW ---

def run_agent(query: str):
    """The main function that orchestrates the agent's workflow."""
    urls = search_online(query)
    
    if not urls:
        print("Could not find any relevant URLs. Exiting.")
        return

    all_content = ""
    for url in urls:
        content = extract_content_from_url(url)
        if content:
            all_content += content + "\n\n"
            
    if not all_content:
        print("Failed to extract content from any of the URLs. Exiting.")
        return
        
    final_report = summarize_with_gemini(all_content, query)
    
    print("\n\n--- ✅ FINAL REPORT ---")
    print(final_report)
    print("\n--- SOURCES ---")
    for url in urls:
        print(f"- {url}")
        
    # --- NEW: Save the report ---
    if final_report:
        save_report_to_db(query, final_report, urls)
    # --- END NEW SECTION ---


# --- EXECUTION ---
if __name__ == '__main__':
    user_query = "Impact of Mediterranean diet on heart health"
    run_agent(user_query)