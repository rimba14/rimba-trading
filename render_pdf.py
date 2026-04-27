import os
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
        # If it's a table line or divider, just print it as is
        pdf.multi_cell(180, 6, line.strip()) 
        # No extra formatting to avoid "Not enough space" errors
        
    pdf.output(dst)
    print(f"PDF Success: {dst}")

if __name__ == "__main__":
    MD_PATH = r'C:\Users\Administrator\.gemini\antigravity\brain\12325980-a53b-4d3f-8c1d-135ccefcf2eb\exit_evolution_report.md'
    PDF_PATH = r'C:\Users\Administrator\.gemini\antigravity\brain\12325980-a53b-4d3f-8c1d-135ccefcf2eb\exit_evolution_report.pdf'
    generate_stable_pdf(MD_PATH, PDF_PATH)
