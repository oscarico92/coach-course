"""Interface : streamlit run app.py

- choix du niveau 0 à 3 (seuls les niveaux disponibles sont proposés) ;
- réponse, sources citées, durée, tokens, nombre d'étapes ;
- trace de chaque exécution (étapes, outils, arguments) ;
- niveaux 2 et 3 : toute écriture dans le calendrier attend un clic « Confirmer » ou « Refuser ».
"""
from datetime import date, timedelta

import streamlit as st

from config import CALENDAR_DIR
from src.levels import get_level, is_available, LEVEL_NAMES
from src.tracing import Trace

st.set_page_config(page_title="Coach Course", page_icon="🏃", layout="wide")
st.title("🏃 Coach Course")
st.caption("Assistant d'entraînement du club fictif « Foulées ECE » · projet IA générative")

CAL_PATH = CALENDAR_DIR / "utilisateur.ics"
state = st.session_state
state.setdefault("result", None)       # dernier résultat affiché
state.setdefault("pending", None)      # écriture en attente de confirmation
state.setdefault("decision", None)     # message après confirmation / refus


# ------------------------------------------------------------------ barre latérale
levels = [n for n in LEVEL_NAMES if is_available(n)]
level = st.sidebar.radio("Niveau", levels, format_func=lambda n: f"{n} · {LEVEL_NAMES[n]}")
missing = [f"{n} · {LEVEL_NAMES[n]}" for n in LEVEL_NAMES if n not in levels]
if missing:
    st.sidebar.caption("Pas encore disponibles : " + ", ".join(missing))
st.sidebar.markdown({0: "LLM seul, sans documents ni outils.",
                     1: "Recherche dans les documents du club, réponses sourcées.",
                     2: "Agent avec outils : allures, météo, calendrier (écriture confirmée).",
                     3: "Multi-agents : un orchestrateur confie la demande à l'agent documentaire (RAG) "
                        "ou à l'agent actions (outils), rapports JSON dans la trace."}.get(level, ""))


def show_calendar():
    try:
        from src.tools import impl
        today = date.today()
        res = impl.lire_calendrier({"date_debut": today.isoformat(),
                                    "date_fin": (today + timedelta(days=21)).isoformat()},
                                   {"calendar_path": CAL_PATH})
    except Exception:
        return  # outils pas encore implémentés
    st.sidebar.subheader("Mon calendrier (3 semaines)")
    if not res["seances"]:
        st.sidebar.caption("Aucune séance prévue.")
    for s in sorted(res["seances"], key=lambda x: x["date"]):
        st.sidebar.markdown(f"**{s['date']}** · {s['titre']} ({s.get('km', '?')} km)"
                            + (" 🔥" if s.get("intense") else ""))


show_calendar()


# ------------------------------------------------------------------ question
question = st.text_area("Ta question", placeholder="Ex. : je vise 10 km en 50 min, ajoute la semaine 1 du plan à mon calendrier")
if st.button("Envoyer", type="primary", disabled=state.pending is not None) and question.strip():
    module = get_level(level)
    trace = Trace(level=level, question=question)
    with st.spinner("Réflexion..."):
        if getattr(module, "USES_TOOLS", False):
            # None = « en attente » : l'agent s'arrête et l'interface demande la confirmation
            out = module.answer(question, trace, confirm=lambda name, args: None,
                                context={"calendar_path": CAL_PATH})
        else:
            out = module.answer(question, trace)
    data = trace.close(out)
    state.result = {"out": out, "data": data, "level": level}
    state.pending = out.get("pending_write")
    state.decision = None


# ------------------------------------------------------------------ affichage
if state.result:
    out, data = state.result["out"], state.result["data"]
    st.markdown(out["answer"])
    if out.get("sources"):
        st.caption("📚 Sources : " + ", ".join(out["sources"]))
    elif out.get("abstained"):
        st.caption("Abstention : l'information n'a pas été trouvée.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Niveau", f"{state.result['level']} · {LEVEL_NAMES[state.result['level']]}")
    c2.metric("Durée", f"{data['duration_s']:.1f} s")
    c3.metric("Tokens", data["total_tokens"])
    c4.metric("Étapes", len(data["steps"]))

    # ---- confirmation d'une action qui modifie le calendrier
    if state.pending:
        st.warning("⚠️ Action qui modifie ton calendrier : confirmation requise.")
        st.table([{"Date": s["date"], "Séance": s["titre"], "Type": s["type"], "km": s.get("km")}
                  for s in state.pending["args"]["seances"]])
        col_ok, col_no = st.columns(2)
        if col_ok.button("✅ Confirmer", type="primary"):
            agent = get_level(state.result["level"])
            trace = Trace(level=state.result["level"], question=f"[confirmation] {data['question']}")
            result, error = agent.execute_confirmed(state.pending["args"], trace, context={"calendar_path": CAL_PATH})
            trace.close({"confirmation": "acceptée", "result": result, "error": error})
            if error:
                state.decision = ("error", f"Erreur : {error}")
            elif result.get("refuse"):
                state.decision = ("error", "Refusé par les règles du club : " + " ".join(result["violations"]))
            else:
                state.decision = ("success", f"{result.get('ajoutees', 0)} séance(s) ajoutée(s) au calendrier.")
            state.pending = None
            st.rerun()
        if col_no.button("❌ Refuser"):
            trace = Trace(level=state.result["level"], question=f"[refus] {data['question']}")
            trace.log("confirmation", decision="refusée par l'utilisateur")
            trace.close({"confirmation": "refusée"})
            state.decision = ("info", "Rien n'a été modifié.")
            state.pending = None
            st.rerun()
    if state.decision:
        getattr(st, state.decision[0])(state.decision[1])

    # ---- trace détaillée
    with st.expander("🔍 Trace de l'exécution"):
        for i, step in enumerate(data["steps"], 1):
            if step["type"] == "tool":
                st.markdown(f"**{i}. Outil `{step['name']}`**" + (" ❌" if step.get("error") else ""))
                st.json({"arguments": step["args"], "résultat": step.get("error") or step["result"]}, expanded=False)
            elif step["type"] == "llm":
                st.markdown(f"**{i}. LLM** ({step.get('note', '')}) · {step['tokens']} tokens · {step['latency_s']} s")
            else:
                st.markdown(f"**{i}. {step['type']}**")
                st.json({k: v for k, v in step.items() if k != "type"}, expanded=False)
