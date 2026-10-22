# Document Tamper & Multi-Category Plagiarism Detection

A high-performance algorithmic plagiarism detection and document tampering verification system built using **Rabin-Karp Rolling Hashes** and **Canonical Merkle Trees**.

## Features

- **Multi-Category Plagiarism Classification**:
  - 🔴 **Direct Plagiarism**: Identical sequential text matching in order.
  - 🟠 **Rearrangement**: Transposed, relocated, or shuffled paragraphs/sections.
  - 🟡 **Slight Rephrasing**: Sentence-level paraphrasing and structural synonym swaps.
- **Order-Invariant Verification**:
  - Bottom-up Canonical Merkle Tree child-sorting ensures $O(1)$ top-level root verification even when paragraphs are shuffled.
- **Dynamic Granularity**:
  - Real-time adjustable **Rabin-Karp Window Size (10–80 characters)** slider to fine-tune matching sensitivity.
- **Multi-Format Support**:
  - Ingests and analyzes `.pdf`, `.docx`, and `.txt` documents.
- **Interactive UI & PDF Export**:
  - Full-text document viewer with color-coded highlighting and legend.
  - Downloadable PDF report with metadata, similarity metrics, and highlighted text.

## Tech Stack

- **Language**: Python 3.10+
- **Frontend / UI**: Streamlit
- **Parsing**: `PyPDF2`, `python-docx`
- **Data & Tables**: `pandas`
- **PDF Report Generation**: `reportlab`

## Quick Start

```bash
# Clone the repository
git clone https://github.com/Adithya-2007/<repo-name>.git

# Install dependencies
pip install streamlit pandas pypdf2 python-docx reportlab

# Run the web application
python -m streamlit run app.py
```
