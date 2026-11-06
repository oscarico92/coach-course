"""Interface : streamlit run app.py"""
import streamlit as st

from src.tracing import Trace
from src.levels import get_level, is_available, LEVEL_NAMES

st.set_page_config(page_title="Coach Course", page_icon="🏃")
st.title("Coach Course")

levels = [n for n in LEVEL_NAMES if is_available(n)]
level = st.sidebar.radio("Niveau", levels, format_func=lambda n: f"{n} · {LEVEL_NAMES[n]}")

question = st.text_area("Ta question", placeholder="Ex. : quelles allures pour un 10 km en 50 minutes ?")
if st.button("Envoyer", type="primary") and question.strip():
    trace = Trace(level=level, question=question)
    with st.spinner("Réflexion..."):
        out = get_level(level).answer(question, trace)
    data = trace.close(out)

    st.markdown(out["answer"])
    if out["sources"]:
        st.caption("Sources : " + ", ".join(out["sources"]))
    c1, c2, c3 = st.columns(3)
    c1.metric("Durée", f"{data['duration_s']:.1f} s")
    c2.metric("Tokens", data["total_tokens"])
    c3.metric("Étapes", len(data["steps"]))
    with st.expander("Trace"):
        st.json(data["steps"])
