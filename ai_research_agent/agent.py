# agent.py
import os
import io
import requests
import pypdf
import trafilatura
import google.generativeai as genai
from tavily import TavilyClient
from dotenv import load_dotenv

# --- 1. SETUP ---
# Load environment variables from .env file
load_dotenv()

# Configure the API clients
try:
    # [cite_start]An agent that combines an LLM + exactly 2 tools (fixed): 1. Web Search API... 2. Content Extractor [cite: 11]
    # Configure Gemini
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    # Configure Tavily
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
        # [cite_start]Find 2-3 useful sources online. [cite: 5]
        response = tavily_client.search(query=query, search_depth="basic", max_results=max_results)
        # Return the URLs from the search results
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
        response.raise_for_status() # Raise an exception for bad status codes

        # Check content type for PDF
        if 'application/pdf' in response.headers.get('Content-Type', ''):
            # [cite_start]Content Extractor: ... pypdf for PDFs [cite: 13]
            with io.BytesIO(response.content) as f:
                reader = pypdf.PdfReader(f)
                text = "".join(page.extract_text() for page in reader.pages)
        # Otherwise, assume HTML
        else:
            # [cite_start]Content Extractor: trafilatura/readability for HTML [cite: 13]
            text = trafilatura.extract(response.text)
        
        return text
            
    except Exception as e:
        # [cite_start]If a page blocks scraping, show that gracefully and skip. [cite: 17]
        print(f"❗️ Gracefully skipping URL {url} due to error: {e}")
        return None

def summarize_with_gemini(text: str, query: str):
    """Uses Gemini to summarize the text into a structured report."""
    if not text:
        return "Error: No text was extracted for summarization."
    
    print("🤖 Summarizing content with Gemini...")
    # [cite_start]Summarize what you found using an LLM. [cite: 6]
    # [cite_start]Create a short, structured report with key points and links. [cite: 7]
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

# --- EXECUTION ---
if __name__ == '__main__':
    # [cite_start]Take a user query (e.g., "Latest research on Al in education", "Impact of Mediterranean diet on heart health", etc.). [cite: 4]
    user_query = "Latest research on AI in education"
    run_agent(user_query)