import os
import textwrap
from fpdf import FPDF

class StablePDF(FPDF):
    def header(self):
        self.set_font('Courier', 'B', 12)
        self.cell(0, 10, "Sentinel Alpha: Exit Framework Audit", new_x="LMARGIN", new_y="NEXT", align='C')
        self.ln(5)

def generate_stable_pdf(src, dst):
    pdf = StablePDF()
    pdf.set_margins(15, 15, 15)
    pdf.add_page()
    pdf.set_font('Courier', '', 10)
    
    with open(src, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Process lines safely
    for line in content.split('\n'):
        # Fix: ensure line isn't too long for multi_cell
        # wrap(line) breaks long lines into segments based on width
        # width=80 is conservative for Courier 10pt on 180mm width
        segments = textwrap.wrap(line.strip(), width=80) or [""]
        for segment in segments:
            pdf.multi_cell(180, 6, segment)
        # No extra formatting to avoid "Not enough space" errors
        
    pdf.output(dst)
    print(f"PDF Success: {dst}")

if __name__ == "__main__":
    # Use relative paths for better portability
    MD_PATH = 'exit_evolution_report.md'
    PDF_PATH = 'exit_evolution_report.pdf'
    if os.path.exists(MD_PATH):
        generate_stable_pdf(MD_PATH, PDF_PATH)
