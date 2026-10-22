import hashlib
import io
import html
import re
import streamlit as st
import pandas as pd
import PyPDF2
import docx
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# ==========================================
# 1. PARSERS (.txt, .pdf, .docx)
# ==========================================
def extract_text(file) -> str:
    ext = file.name.lower().split(".")[-1]
    if ext == "txt":
        return file.read().decode("utf-8", errors="ignore")
    elif ext == "pdf":
        reader = PyPDF2.PdfReader(io.BytesIO(file.read()))
        return "\n".join(re.sub(r'([^\.\!\?\:\n])\n([^\n])', r'\1 \2', p.extract_text() or "") for p in reader.pages)
    elif ext == "docx":
        return "\n".join(p.text for p in docx.Document(io.BytesIO(file.read())).paragraphs if p.text)
    return ""

# ==========================================
# 2. ALGORITHMIC ENGINE
# ==========================================
class MerkleNode:
    def __init__(self, hash_val, left=None, right=None, text="", span=(0, 0)):
        self.hash, self.left, self.right, self.text, self.span = str(hash_val), left, right, text, span

class RabinKarpHasher:
    def __init__(self, window_size=25, base=256, prime=1000000007):
        self.w, self.base, self.prime = window_size, base, prime
        self.h = pow(base, max(0, window_size - 1), prime)

    def hash_text(self, text: str) -> list:
        leaves, n = [], len(text)
        if n < self.w:
            return [MerkleNode(hashlib.sha256(text.encode()).hexdigest(), text=text, span=(0, n))] if n > 0 else []
        cur = 0
        for c in text[:self.w]:
            cur = (self.base * cur + ord(c)) % self.prime
        for i in range(n - self.w + 1):
            chunk = text[i : i + self.w]
            h = hashlib.sha256(f"{cur}:{chunk}".encode()).hexdigest()
            leaves.append(MerkleNode(h, text=chunk, span=(i, i + self.w)))
            if i < n - self.w:
                cur = (self.base * (cur - ord(text[i]) * self.h) + ord(text[i + self.w])) % self.prime
        return leaves

def build_canonical_merkle_tree(nodes: list) -> MerkleNode:
    if not nodes:
        return None
    if len(nodes) == 1:
        return nodes[0]
    s = sorted(nodes, key=lambda x: x.hash)
    parents = [MerkleNode(hashlib.sha256((s[i].hash + (s[i+1].hash if i+1 < len(s) else s[i].hash)).encode()).hexdigest(), s[i], s[i+1] if i+1 < len(s) else s[i]) for i in range(0, len(s), 2)]
    return build_canonical_merkle_tree(parents)

def extract_leaves(text: str, hasher: RabinKarpHasher) -> list:
    leaves, pos = [], 0
    for line in [l.strip() for l in text.splitlines() if l.strip()]:
        idx = text.find(line, pos)
        idx = pos if idx == -1 else idx
        for node in hasher.hash_text(line):
            node.span = (idx + node.span[0], idx + node.span[1])
            leaves.append(node)
        pos = idx + len(line)
    return leaves

def detect_categorized_matches(t1: str, t2: str, map1: dict, map2: dict, common: set) -> list:
    matches = []
    # 1. Exact rolling matches (Direct Plagiarism vs Rearrangement based on relative displacement)
    for h in common:
        n1, n2 = map1[h], map2[h]
        rel1 = n1.span[0] / max(1, len(t1))
        rel2 = n2.span[0] / max(1, len(t2))
        cat = "Rearrangement" if abs(rel1 - rel2) > 0.08 else "Direct Plagiarism"
        matches.append({
            "Start_Char": n1.span[0],
            "End_Char": n1.span[1],
            "Category": cat,
            "Plagiarized_Text": n1.text
        })
    
    # 2. Sentence-level fuzzy scanning for Slight Rephrasing
    sent_pat = re.compile(r'[^.!?:\n]+(?:[.!?:\n]+|$)')
    s1_list = [(m.start(), m.end(), t1[m.start():m.end()].strip()) for m in sent_pat.finditer(t1) if len(t1[m.start():m.end()].strip()) >= 20]
    s2_words = [set(m.group().strip().lower().split()) for m in sent_pat.finditer(t2) if len(m.group().strip()) >= 20]
    
    exact_covered = set()
    for m in matches:
        for p in range(m["Start_Char"], m["End_Char"]):
            exact_covered.add(p)
            
    for s_start, s_end, text in s1_list:
        covered = sum(1 for p in range(s_start, s_end) if p in exact_covered)
        if covered / max(1, (s_end - s_start)) < 0.60:
            w1 = set(text.lower().split())
            if len(w1) >= 4:
                best_sim = max((len(w1 & w2) / max(1, len(w1 | w2)) for w2 in s2_words), default=0)
                if 0.35 <= best_sim < 0.85:
                    matches.append({
                        "Start_Char": s_start,
                        "End_Char": s_end,
                        "Category": "Slight Rephrasing",
                        "Plagiarized_Text": text
                    })
    matches.sort(key=lambda x: x["Start_Char"])
    return matches

def segment_document(text: str, matches: list) -> list:
    char_cats = [None] * len(text)
    for m in matches:
        if m["Category"] in ("Rearrangement", "Direct Plagiarism"):
            for p in range(m["Start_Char"], min(len(text), m["End_Char"])):
                char_cats[p] = m["Category"]
    for m in matches:
        if m["Category"] == "Slight Rephrasing":
            for p in range(m["Start_Char"], min(len(text), m["End_Char"])):
                char_cats[p] = m["Category"]
    segments, i = [], 0
    while i < len(text):
        cat, start = char_cats[i], i
        while i < len(text) and char_cats[i] == cat:
            i += 1
        segments.append((start, i, cat))
    return segments

def generate_pdf_report(t_name, r_name, sim, root_match, r1, r2, matches, doc_text="", segments=None, window_size=25) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("<b>Document Tamper & Multi-Category Plagiarism Report</b>", styles['Heading1']),
        Spacer(1, 10),
        Table([
            ["Target Document:", t_name],
            ["Reference Document:", r_name],
            ["Rabin-Karp Window Size:", f"{window_size} characters"],
            ["Overall Similarity (%):", f"{sim:.2f}%"],
            ["Merkle Root Verdict:", "MATCH (100% Identical / Shuffled)" if root_match else "DIFFER (Divergent Content)"],
            ["Target Merkle Root:", Paragraph(f"<font size=7>{r1}</font>", styles['Normal'])],
            ["Reference Merkle Root:", Paragraph(f"<font size=7>{r2}</font>", styles['Normal'])]
        ], colWidths=[140, 400], style=[
            ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f8fafc')),
            ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#cbd5e1')),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#e2e8f0')),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('TOPPADDING', (0,0), (-1,-1), 4),
            ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ]),
        Spacer(1, 14),
        Paragraph("<b>Categorized Plagiarized Offsets (First 50 Matches):</b>", styles['Heading3']),
        Spacer(1, 6)
    ]
    if matches:
        t_data = [["#", "Category", "Start", "End", "Plagiarized Text"]] + [
            [str(i), m['Category'], str(m['Start_Char']), str(m['End_Char']), Paragraph(f"<font size=8>{html.escape(m['Plagiarized_Text'])}</font>", styles['Normal'])]
            for i, m in enumerate(matches[:50], 1)
        ]
        story.append(Table(t_data, colWidths=[25, 95, 40, 40, 340], style=[
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f1f5f9')),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
            ('FONTSIZE', (0,0), (-1,-1), 8),
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ]))
    else:
        story.append(Paragraph("No matching substrings detected.", styles['Normal']))

    if doc_text and segments:
        story.extend([
            Spacer(1, 14),
            Paragraph("<b>Full Document with Multi-Category Highlighted Text:</b>", styles['Heading3']),
            Paragraph("<font color='#991b1b'>■ Red: Direct Plagiarism</font> &nbsp;|&nbsp; <font color='#9a3412'>■ Orange: Rearrangement</font> &nbsp;|&nbsp; <font color='#854d0e'>■ Yellow: Slight Rephrasing</font>", styles['Normal']),
            Spacer(1, 6)
        ])
        parts = []
        color_map = {
            'Direct Plagiarism': ('#fee2e2', '#991b1b'),
            'Rearrangement': ('#ffedd5', '#9a3412'),
            'Slight Rephrasing': ('#fef9c3', '#854d0e'),
        }
        for s, e, cat in segments:
            escaped = html.escape(doc_text[s:e]).replace('\r\n', '\n').replace('\n', '<br/>')
            if cat in color_map:
                bg, fg = color_map[cat]
                parts.append(f"<font backColor='{bg}' color='{fg}'><b>{escaped}</b></font>")
            else:
                parts.append(escaped)
        story.append(Paragraph(''.join(parts), ParagraphStyle('DocHighlight', parent=styles['Normal'], fontSize=8, leading=11, textColor=colors.HexColor('#1e293b'))))

    doc.build(story)
    return buf.getvalue()

# ==========================================
# 3. STREAMLIT UI
# ==========================================
st.set_page_config(page_title="Document Tamper Detection", layout="wide")
st.title("Document Tamper Detection")

col1, col2 = st.columns(2)
with col1:
    f1 = st.file_uploader("Target Document", type=["txt", "pdf", "docx"])
with col2:
    f2 = st.file_uploader("Reference Document", type=["txt", "pdf", "docx"])

window_size = st.slider(
    "Rabin-Karp Window Size (Characters)",
    min_value=10,
    max_value=80,
    value=25,
    help="Sliding substring window size for Rabin-Karp rolling hashing. Smaller sizes detect finer similarities; larger sizes require longer identical character matches."
)

if f1 and f2:
    t1, t2 = extract_text(f1), extract_text(f2)
    hasher = RabinKarpHasher(window_size)
    leaves1, leaves2 = extract_leaves(t1, hasher), extract_leaves(t2, hasher)

    tree1, tree2 = build_canonical_merkle_tree(leaves1), build_canonical_merkle_tree(leaves2)
    map1 = {n.hash: n for n in leaves1}
    map2 = {n.hash: n for n in leaves2}
    common, total = set(map1) & set(map2), set(map1) | set(map2)

    sim = (len(common) / len(total) * 100) if total else 0.0
    root_match = bool(tree1 and tree2 and tree1.hash == tree2.hash)
    r1, r2 = (tree1.hash if tree1 else "N/A"), (tree2.hash if tree2 else "N/A")

    # 1. High-Level Metrics
    m1, m2, m3 = st.columns(3)
    m1.metric("Similarity Score (%)", f"{sim:.2f}%")
    m2.metric("Target Merkle Root", f"{r1[:16]}...", help=r1)
    m3.metric("Reference Merkle Root", f"{r2[:16]}...", help=r2)

    with st.expander("View Full 64-Character Merkle Root Hashes"):
        st.text(f"Target Merkle Root:    {r1}\nReference Merkle Root: {r2}")

    # 2. Categorization & Metrics Breakdown
    matches = detect_categorized_matches(t1, t2, map1, map2, common)
    segments = segment_document(t1, matches)

    tot_len = max(1, len(t1))
    d_pct = sum(e - s for s, e, c in segments if c == "Direct Plagiarism") / tot_len * 100
    r_pct = sum(e - s for s, e, c in segments if c == "Rearrangement") / tot_len * 100
    p_pct = sum(e - s for s, e, c in segments if c == "Slight Rephrasing") / tot_len * 100

    b1, b2, b3 = st.columns(3)
    b1.metric("🔴 Direct Plagiarism", f"{d_pct:.2f}%", help="Exact matching text in preserved sequential order")
    b2.metric("🟠 Rearrangement", f"{r_pct:.2f}%", help="Identical text transposed or shuffled from another location")
    b3.metric("🟡 Slight Rephrasing", f"{p_pct:.2f}%", help="Paraphrased sentences with high structural and word similarity")

    # 3. Verification Verdict Banner
    if root_match:
        st.success("100% Identical / Shuffled: Both documents contain the exact same content. Canonical Merkle sorting verified order-invariant identity in O(1) time.")
    elif sim > 0:
        st.warning(f"Plagiarism Detected: Direct ({d_pct:.1f}%), Rearranged ({r_pct:.1f}%), Rephrased ({p_pct:.1f}%).")
    else:
        st.info(f"Clean Document: 0% match across all sequential {window_size}-character Rabin-Karp windows.")

    # 4. Evidence Table
    st.subheader("Plagiarized Substring Offsets")
    if matches:
        st.dataframe(pd.DataFrame(matches), use_container_width=True)
    else:
        st.write("No matching substrings found.")

    pdf_bytes = generate_pdf_report(f1.name, f2.name, sim, root_match, r1, r2, matches, t1, segments, window_size)
    st.download_button("📄 Download Plagiarism Report (PDF)", pdf_bytes, "plagiarism_report.pdf", "application/pdf")

    # 5. Document Viewer with Multi-Color Inline Highlights
    with st.expander("View Full Document with Highlighted Plagiarized Text", expanded=True):
        st.markdown("""
        <div style="display:flex;gap:14px;align-items:center;margin-bottom:12px;padding:8px 12px;background:#f8fafc;border:1px solid #cbd5e1;border-radius:6px;font-size:13px;">
          <span style="font-weight:bold;color:#334155;">Legend:</span>
          <span style="background:#fee2e2;color:#991b1b;border:1px solid #f87171;padding:2px 8px;border-radius:4px;font-weight:600;">🔴 Direct Plagiarism</span>
          <span style="background:#ffedd5;color:#9a3412;border:1px solid #fb923c;padding:2px 8px;border-radius:4px;font-weight:600;">🟠 Rearrangement</span>
          <span style="background:#fef9c3;color:#854d0e;border:1px solid #facc15;padding:2px 8px;border-radius:4px;font-weight:600;">🟡 Slight Rephrasing</span>
        </div>
        """, unsafe_allow_html=True)

        if segments and any(c is not None for _, _, c in segments):
            parts = []
            for s, e, cat in segments:
                txt = html.escape(t1[s:e])
                if cat == "Direct Plagiarism":
                    parts.append(f"<mark style='background:#fee2e2;color:#991b1b;border-bottom:2px solid #ef4444;border-radius:3px;padding:1px 3px;font-weight:600;' title='Direct Plagiarism'>{txt}</mark>")
                elif cat == "Rearrangement":
                    parts.append(f"<mark style='background:#ffedd5;color:#9a3412;border-bottom:2px solid #f97316;border-radius:3px;padding:1px 3px;font-weight:600;' title='Rearrangement'>{txt}</mark>")
                elif cat == "Slight Rephrasing":
                    parts.append(f"<mark style='background:#fef9c3;color:#854d0e;border-bottom:2px solid #eab308;border-radius:3px;padding:1px 3px;font-weight:600;' title='Slight Rephrasing'>{txt}</mark>")
                else:
                    parts.append(txt)
            st.markdown(f"<div style='white-space:pre-wrap;font-family:monospace;padding:14px;background:#f8fafc;border:1px solid #cbd5e1;border-radius:8px;color:#1e293b;line-height:1.6;'>{''.join(parts)}</div>", unsafe_allow_html=True)
        else:
            st.text(t1)