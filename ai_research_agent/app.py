# app.py
from flask import Flask, render_template, abort
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

# --- DATABASE SETUP (mirrors the setup in agent.py) ---
# We define the database connection and model here again so the web app
# is independent of the agent script.
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
    timestamp = Column(DateTime)

# Check if the table exists before trying to use it
Base.metadata.reflect(bind=engine)

# --- FLASK APP ---
app = Flask(__name__)

@app.route("/")
def index():
    """History page: lists all saved reports."""
    db = SessionLocal()
    # Query all reports, order by the most recent ones first
    reports = db.query(Report).order_by(Report.timestamp.desc()).all()
    db.close()
    return render_template("index.html", reports=reports)

@app.route("/report/<int:report_id>")
def report(report_id):
    """Report view page: displays a single report."""
    db = SessionLocal()
    # Query the specific report by its ID
    single_report = db.query(Report).filter(Report.id == report_id).first()
    db.close()
    if single_report is None:
        abort(404) # Not found
    
    # Split the sources string back into a list for cleaner display
    sources_list = single_report.sources.split(", ")
    return render_template("report.html", report=single_report, sources=sources_list)

if __name__ == '__main__':
    app.run(debug=True)