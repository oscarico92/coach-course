"""Interface : streamlit run app.py

- conversation façon messagerie : historique de la session, « Régénérer », « Nouvelle conversation » ;
- choix du modèle (qwen2.5:7b en local ou gpt-6-luna par l'API) et du niveau 0 à 3 (3 par défaut : l'assistant
  complet ; les autres niveaux servent à comparer, comme le demande la consigne) ;
- questions de suivi (option) : la question est réécrite en question autonome à partir des derniers échanges
  (src/conversation.py), puis passée au niveau choisi, qui reste inchangé (hors évaluation) ;
- sous chaque réponse : sources citées, modèle, niveau, durée, tokens, étapes, et la trace complète ;
- niveaux 2 et 3 : toute écriture dans le calendrier attend un clic « Confirmer » ou « Refuser » ;
- page principale : conversation à gauche ; à droite, calendrier des semaines à venir (export .ics) et
  prévisions Open-Meteo à 7 jours avec les alertes de la règle R5. Barre latérale : réglages.
"""
from datetime import date, timedelta

import streamlit as st

import src.llm as llm
from config import CALENDAR_DIR, LLM_PROVIDER, OPENAI_API_KEY
from src import rules
from src.conversation import standalone_question
from src.levels import get_level, is_available, LEVEL_NAMES
from src.tracing import Trace

st.set_page_config(page_title="Coach Course", page_icon="🏃", layout="wide")

CAL_PATH = CALENDAR_DIR / "utilisateur.ics"
JOURS = ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."]
state = st.session_state
state.setdefault("turns", [])   # échanges de la session : question, réponse, trace, confirmation éventuelle


# ------------------------------------------------------------------ barre latérale : modèle et niveau
# Modèle : même code pour les deux, seul l'appel au LLM change (src/llm.py). Les embeddings restent locaux.
MODELS = {"qwen2.5:7b (local, Ollama)": ("ollama", "qwen2.5:7b"),
          "gpt-6-luna (API OpenAI)": ("openai", "gpt-6-luna")}
labels = list(MODELS)
# valeur par défaut fixe (celle du .env) : calculée depuis llm.PROVIDER, elle changerait après chaque choix
# et Streamlit recréerait le widget
default = next((i for i, (prov, _) in enumerate(MODELS.values()) if prov == LLM_PROVIDER), 0)
model_label = st.sidebar.radio("Modèle", labels, index=default, key="modele")
llm.PROVIDER, llm.MODEL = MODELS[model_label]
if llm.PROVIDER == "openai":
    if not OPENAI_API_KEY:
        st.sidebar.error("Clé absente : ajouter OPENAI_API_KEY dans .env (jamais dans le dépôt).")
    if not llm.OPENAI_REASONING_EFFORT:
        llm.OPENAI_REASONING_EFFORT = "none"   # configuration mesurée dans le rapport (sans raisonnement)
st.sidebar.caption("Les embeddings (bge-m3) restent calculés en local par Ollama.")

levels = [n for n in LEVEL_NAMES if is_available(n)]
level = st.sidebar.radio("Niveau", levels, index=levels.index(3) if 3 in levels else len(levels) - 1,
                         format_func=lambda n: f"{n} · {LEVEL_NAMES[n]}", key="niveau")
st.sidebar.caption({0: "LLM seul, sans documents ni outils.",
                    1: "Recherche dans les documents du club, réponses sourcées.",
                    2: "Agent avec outils : allures, météo, calendrier (écriture confirmée).",
                    3: "Assistant complet : un orchestrateur confie la demande à l'agent documentaire (RAG) "
                       "ou à l'agent actions (outils)."}.get(level, "")
                   + " Les niveaux 0 à 2 servent à comparer ce que chaque étape apporte.")

follow_up = st.sidebar.toggle("Questions de suivi", value=True, key="suivi",
                              help="La question est réécrite à partir des derniers échanges avant d'être passée au "
                                   "niveau (« et pour la semaine 2 ? »). Hors évaluation : le jeu de test ne contient "
                                   "que des questions isolées.")
if st.sidebar.button("🗑️ Nouvelle conversation", use_container_width=True):
    state.turns = []
    st.rerun()


# ------------------------------------------------------------------ calendrier et météo (colonne de droite)
WEEK_LABELS = ["Cette semaine", "Semaine prochaine", "Dans 2 semaines", "Dans 3 semaines"]


def show_calendar():
    from src.tools import impl
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    st.subheader("📅 Mon calendrier")
    try:
        res = impl.lire_calendrier({"date_debut": today.isoformat(),
                                    "date_fin": (monday + timedelta(days=27)).isoformat()},
                                   {"calendar_path": CAL_PATH})
    except Exception as e:
        st.caption(f"Calendrier illisible : {e}")
        return
    if not res["seances"]:
        st.caption("Aucune séance prévue. Demande par exemple : « Ajoute la semaine 1 du plan 10 km la semaine "
                   "prochaine. »")
    week = None
    for s in sorted(res["seances"], key=lambda x: str(x["date"])):
        d = date.fromisoformat(str(s["date"]))
        w = (d - monday).days // 7
        if w != week:
            week = w
            total = sum(float(x.get("km") or 0) for x in res["seances"]
                        if (date.fromisoformat(str(x["date"])) - monday).days // 7 == w)
            st.markdown(f"**{WEEK_LABELS[min(w, 3)]}** · {total:g} km")
        km = f"{s['km']:g}" if isinstance(s.get("km"), (int, float)) else "?"
        st.markdown(f"{'🔥' if s.get('intense') else '🏃'} {JOURS[d.weekday()]} {d.strftime('%d/%m')} · "
                    f"{s['titre']} ({km} km)")
    if CAL_PATH.exists():
        st.download_button("⬇️ Exporter le calendrier (.ics)", CAL_PATH.read_bytes(),
                           file_name="coach-course.ics", mime="text/calendar", use_container_width=True,
                           help="À importer dans Google Agenda, Outlook ou Calendrier.")


@st.cache_data(ttl=1800, show_spinner=False)
def forecast(day):
    from src.tools import impl
    return impl.previsions(day, 7)


def weather_icon(f):
    if f["orage"]:
        return "⛈️"
    if f["code"] >= 61:
        return "🌧️"
    if f["code"] >= 45:
        return "🌫️" if f["code"] < 51 else "🌦️"
    return "☀️" if f["code"] <= 1 else "⛅"


def show_weather():
    st.subheader("🌤️ Météo à Paris")
    try:
        days = forecast(date.today().isoformat())
    except Exception:
        st.caption("Prévisions Open-Meteo indisponibles (pas de réseau ?). L'agent ne bloque alors pas sur la "
                   "règle R5.")
        return
    for f in days:
        d = date.fromisoformat(f["date"])
        alert = ""
        if f["orage"] or f["vent_kmh"] > rules.WIND_KMH:
            alert = " · ⚠️ séance à reporter (R5)"
        elif f["tmax_c"] > rules.HOT_C:
            alert = " · ⚠️ pas d'intense (R5)"
        st.markdown(f"{weather_icon(f)} {JOURS[d.weekday()]} {d.strftime('%d/%m')} · {f['tmax_c']:.0f} °C · "
                    f"vent {f['vent_kmh']:.0f} km/h{alert}")
    st.caption("Source : Open-Meteo. Vérifiée par le code avant tout ajout (règle R5).")




# ------------------------------------------------------------------ exécution d'une question
def run_turn(question, history):
    """Passe la question (réécrite si besoin) au niveau choisi ; renvoie l'échange à afficher."""
    module = get_level(level)
    trace = Trace(level=level, question=question)
    asked = standalone_question(question, history, trace) if follow_up and history else question
    if getattr(module, "USES_TOOLS", False):
        # None = « en attente » : l'agent s'arrête et l'interface demande la confirmation
        out = module.answer(asked, trace, confirm=lambda name, args: None, context={"calendar_path": CAL_PATH})
    else:
        out = module.answer(asked, trace)
    data = trace.close(out)
    return {"question": question, "asked": asked, "answer": out["answer"], "out": out, "data": data,
            "level": level, "model": llm.MODEL, "pending": out.get("pending_write"), "decision": None}


def history_for(turns):
    return [{"question": t["asked"], "answer": t["answer"]} for t in turns]


def confirm(i, accepted):
    turn = state.turns[i]
    agent = get_level(turn["level"])
    trace = Trace(level=turn["level"], question=f"[{'confirmation' if accepted else 'refus'}] {turn['asked']}")
    if accepted:
        result, error = agent.execute_confirmed(turn["pending"]["args"], trace, context={"calendar_path": CAL_PATH})
        trace.close({"confirmation": "acceptée", "result": result, "error": error})
        if error:
            turn["decision"] = ("error", f"Erreur : {error}")
        elif result.get("refuse"):
            turn["decision"] = ("error", "Refusé par les règles du club : " + " ".join(result["violations"]))
        else:
            turn["decision"] = ("success", f"✅ {result.get('ajoutees', 0)} séance(s) ajoutée(s) au calendrier.")
    else:
        trace.log("confirmation", decision="refusée par l'utilisateur")
        trace.close({"confirmation": "refusée"})
        turn["decision"] = ("info", "Rien n'a été modifié.")
    turn["pending"] = None


def show_trace(data):
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


# ------------------------------------------------------------------ conversation
st.title("🏃 Coach Course")
st.caption("Assistant d'entraînement du club fictif « Foulées ECE » · projet IA générative")
col_chat, col_side = st.columns([2.2, 1], gap="large")
with col_side:
    with st.container(border=True):
        show_calendar()
    with st.container(border=True):
        show_weather()

def show_turn(i, turn):
    last = i == len(state.turns) - 1
    with st.chat_message("user"):
        st.markdown(turn["question"])
    with st.chat_message("assistant"):
        if turn["asked"] != turn["question"]:
            st.caption(f"Question comprise : {turn['asked']}")
        answer = turn["answer"]
        if turn["decision"] and answer.startswith("Je propose d'ajouter ces séances"):
            answer = answer.replace("Je propose d'ajouter ces séances à ton calendrier. Tu confirmes ?",
                                    "Proposition d'ajout au calendrier :", 1)
        st.markdown(answer)
        out, data = turn["out"], turn["data"]
        if out.get("sources"):
            st.caption("📚 Sources : " + ", ".join(out["sources"]))
        elif out.get("abstained"):
            st.caption("Abstention : l'information n'a pas été trouvée dans les documents du club.")
        st.caption(f"{turn['model']} · niveau {turn['level']} · {LEVEL_NAMES[turn['level']]} · "
                   f"{data['duration_s']:.1f} s · {data['total_tokens']} tokens · {len(data['steps'])} étapes")

        if turn["pending"]:
            st.warning("⚠️ Action qui modifie ton calendrier : confirmation requise.")
            st.table([{"Date": s["date"], "Séance": s["titre"], "Type": s["type"], "km": s.get("km")}
                      for s in turn["pending"]["args"]["seances"]])
            col_ok, col_no = st.columns(2)
            if col_ok.button("✅ Confirmer", type="primary", key=f"ok_{i}"):
                confirm(i, True)
                st.rerun()
            if col_no.button("❌ Refuser", key=f"no_{i}"):
                confirm(i, False)
                st.rerun()
        if turn["decision"]:
            getattr(st, turn["decision"][0])(turn["decision"][1])
        show_trace(data)
        if last and not turn["pending"] and st.button("🔄 Régénérer", key=f"regen_{i}",
                                                     help="Repose la même question avec le modèle et le niveau choisis"):
            with st.spinner("Réflexion…"):
                state.turns[-1] = run_turn(turn["question"], history_for(state.turns[:-1]))
            st.rerun()


with col_chat:
    # zone de conversation de hauteur fixe : le calendrier et la météo restent visibles à côté
    chat_box = st.container(height=620, border=False)
    with chat_box:
        if not state.turns:
            st.info("Exemples : « Quelle est la séance de fractionné de la semaine 6 du plan 10 km ? » · "
                    "« Ma VMA est de 15 km/h, quelles sont mes allures ? » · "
                    "« Ajoute la semaine 1 du plan 10 km dans mon calendrier la semaine prochaine. »")
        for i, turn in enumerate(state.turns):
            show_turn(i, turn)

    pending = any(t["pending"] for t in state.turns)
    question = st.chat_input("Confirme ou refuse l'action en attente avant de continuer" if pending
                             else "Ta question…", disabled=pending)
    if question and question.strip():
        with chat_box:
            with st.chat_message("user"):
                st.markdown(question)
            with st.chat_message("assistant"):
                with st.spinner("Réflexion…"):
                    turn = run_turn(question, history_for(state.turns))
        state.turns.append(turn)
        st.rerun()
