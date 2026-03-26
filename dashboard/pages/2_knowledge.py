"""
dashboard/pages/2_knowledge.py — Knowledge Base Manager
"""

import time
import streamlit as st
import httpx

st.set_page_config(page_title="Knowledge Base — AuroLab", page_icon="⚗", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');
html, body, [class*="css"] { font-family: 'IBM Plex Sans', sans-serif; }
[data-testid="stSidebar"] { background: #0d0d0f; border-right: 1px solid #1f1f23; }
.main .block-container { padding-top: 2rem; max-width: 1280px; }
h1,h2,h3 { font-family:'IBM Plex Sans',sans-serif; font-weight:600; letter-spacing:-0.02em; }
.doc-row { display:flex; align-items:center; gap:12px; padding:10px 14px; background:#0d0d12; border:1px solid #1a1a22; border-radius:6px; margin:5px 0; }
.doc-name { font-size:0.9em; color:#d0d0dc; flex:1; }
.doc-meta { font-family:'IBM Plex Mono',monospace; font-size:0.75em; color:#555568; }
.status-ready    { background:#0a2e1a; color:#22c55e; border:1px solid #166534; padding:1px 8px; border-radius:3px; font-family:'IBM Plex Mono',monospace; font-size:0.72em; }
.status-processing { background:#0a1a2e; color:#60a5fa; border:1px solid #1e40af; padding:1px 8px; border-radius:3px; font-family:'IBM Plex Mono',monospace; font-size:0.72em; }
.status-failed   { background:#2e0a0a; color:#ef4444; border:1px solid #991b1b; padding:1px 8px; border-radius:3px; font-family:'IBM Plex Mono',monospace; font-size:0.72em; }
.status-queued   { background:#1a1a0a; color:#d4d460; border:1px solid #666620; padding:1px 8px; border-radius:3px; font-family:'IBM Plex Mono',monospace; font-size:0.72em; }
.section-divider { border:none; border-top:1px solid #1a1a22; margin:24px 0; }
.upload-zone { border:2px dashed #2a2a38; border-radius:10px; padding:32px; text-align:center; background:#0a0a0e; }
</style>
""", unsafe_allow_html=True)

API_BASE = "http://localhost:8080"

def api_get(path):
    try:
        r = httpx.get(f"{API_BASE}{path}", timeout=15.0)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return None

def api_post(path, **kwargs):
    try:
        r = httpx.post(f"{API_BASE}{path}", timeout=60.0, **kwargs)
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:
        detail = e.response.json().get("detail", str(e))
        st.error(f"API {e.response.status_code}: {detail}")
        return None
    except Exception as e:
        st.error(f"Connection error: {e}")
        return None

def api_delete(path):
    try:
        r = httpx.delete(f"{API_BASE}{path}", timeout=15.0)
        return r.status_code == 204
    except Exception:
        return False

# ---------------------------------------------------------------------------
# Page layout
# ---------------------------------------------------------------------------

st.markdown("## Knowledge Base")
st.markdown("Upload lab protocol PDFs, SOPs, and research papers to expand the retrieval index.")
st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

upload_col, list_col = st.columns([2, 3], gap="large")

with upload_col:
    st.markdown("#### Upload documents")

    uploaded_files = st.file_uploader(
        "Drop PDFs here",
        type=["pdf"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )

    if uploaded_files:
        for uf in uploaded_files:
            # Check if already queued this session
            queued = st.session_state.get("queued_uploads", set())
            if uf.name in queued:
                continue

            with st.spinner(f"Uploading {uf.name}..."):
                result = api_post(
                    "/api/v1/documents/upload",
                    files={"file": (uf.name, uf.getvalue(), "application/pdf")},
                )

            if result:
                status = result.get("status", "queued")
                sha = result.get("sha256", "")[:12]
                if status == "duplicate":
                    st.info(f"{uf.name} — already indexed ({result.get('message','')})")
                else:
                    st.success(f"{uf.name} queued — {result.get('size_kb',0)} KB · {sha}…")
                    queued.add(uf.name)
                    st.session_state.queued_uploads = queued

    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
    st.markdown("#### Supported document types")
    st.markdown("""
    <div style='font-size:0.84em; color:#888898; line-height:2;'>
    · Lab protocols (BCA, PCR, ELISA, Western blot…)<br>
    · Standard Operating Procedures (SOPs)<br>
    · Research papers with methods sections<br>
    · Equipment datasheets<br><br>
    <span style='color:#555568;'>Max file size: 50 MB · PDF only</span>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)
    st.markdown("#### Parsing pipeline")
    st.markdown("""
    <div style='font-size:0.83em; color:#888898; line-height:1.9;'>
    <b style='color:#a78bfa;'>Strategy 1:</b> PyMuPDF — fast, precise text extraction<br>
    <b style='color:#a78bfa;'>Strategy 2:</b> Unstructured — layout-aware fallback for scanned PDFs<br>
    <b style='color:#a78bfa;'>Chunking:</b> Heading-anchored sections, tables kept atomic<br>
    <b style='color:#a78bfa;'>Dedup:</b> SHA-256 hash guard — identical files skipped
    </div>
    """, unsafe_allow_html=True)

with list_col:
    st.markdown("#### Indexed documents")

    refresh = st.button("Refresh", use_container_width=False)
    docs_data = api_get("/api/v1/documents/")

    if docs_data is None:
        st.warning("Could not reach API. Start the backend with `uvicorn main:app --port 8080`")
    elif docs_data.get("total", 0) == 0:
        st.markdown("""
        <div style='text-align:center; padding:48px; color:#444458;'>
            <div style='font-size:2em; margin-bottom:12px;'>⚗</div>
            <div style='font-family:IBM Plex Mono,monospace; font-size:0.85em;'>No documents indexed yet.</div>
            <div style='font-size:0.8em; margin-top:6px;'>Upload a PDF to get started.</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        docs = docs_data.get("documents", [])

        # Summary stats
        ready = sum(1 for d in docs if d.get("status") == "ready")
        processing = sum(1 for d in docs if d.get("status") in ("processing", "queued"))
        failed = sum(1 for d in docs if d.get("status") == "failed")
        total_chunks = sum(d.get("chunk_count", 0) for d in docs)

        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Total", len(docs))
        s2.metric("Ready", ready)
        s3.metric("Processing", processing)
        s4.metric("Total chunks", f"{total_chunks:,}")

        st.markdown("<br>", unsafe_allow_html=True)

        for doc in docs:
            status = doc.get("status", "unknown")
            status_html = f"<span class='status-{status}'>{status.upper()}</span>"

            doc_type = doc.get("doc_type", "unknown")
            chunks = doc.get("chunk_count", 0)
            pages = doc.get("page_count", 0)
            strategy = doc.get("parse_strategy", "")
            sha = doc.get("sha256", "")[:10]

            with st.container():
                cols = st.columns([4, 1])
                with cols[0]:
                    st.markdown(f"""
                    <div class='doc-row'>
                        <div class='doc-name'>{doc.get('filename','unknown')}</div>
                        <div class='doc-meta'>{doc_type} · {pages}pp · {chunks} chunks · {strategy}</div>
                        {status_html}
                    </div>
                    """, unsafe_allow_html=True)
                with cols[1]:
                    if st.button("Delete", key=f"del_{sha}", use_container_width=True):
                        if api_delete(f"/api/v1/documents/{doc['sha256']}"):
                            st.success("Deleted")
                            time.sleep(0.5)
                            st.rerun()

        # Auto-refresh if any docs are still processing
        if processing > 0:
            time.sleep(3)
            st.rerun()