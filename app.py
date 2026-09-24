"""Streamlit UI: Run / Review / Learn.

Streamlit reruns the whole script on every click, so the agent is run
synchronously inside the Run button's click handler (not in a background
thread) and every step is streamed into a placeholder container as it
happens. Labels are written to disk immediately via Memory, never only kept
in session_state, so a rerun never loses feedback.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from prospector.agent import Agent, RunState, Step
from prospector.learner import learn
from prospector.llm import GeminiLLM, LLMError
from prospector.memory import Memory

load_dotenv()

st.set_page_config(page_title="Prospector", layout="wide")
st.title("Prospector")

MEMORY = Memory(Path("data"))
RUNS_DIR = Path("runs")


def _list_run_ids() -> list[str]:
    if not RUNS_DIR.exists():
        return []
    return sorted(
        (p.name for p in RUNS_DIR.iterdir() if p.is_dir() and (p / "state.json").exists()),
        reverse=True,
    )


def _load_run(run_id: str) -> RunState:
    data = json.loads((RUNS_DIR / run_id / "state.json").read_text(encoding="utf-8"))
    return RunState.from_dict(data)


def _download_button(label: str, data: bytes, file_name: str, key: str) -> None:
    """st.download_button triggers a script rerun on click in older Streamlit
    versions, which (without care) can look like the run's results vanished.
    Newer versions accept on_click="ignore" to skip that rerun; fall back to
    a plain keyed button on versions that don't support it. Either way, the
    actual results are rendered from disk (see below), not from this
    button's branch, so a rerun here never loses them."""
    try:
        st.download_button(label, data, file_name=file_name, key=key, on_click="ignore")
    except TypeError:
        st.download_button(label, data, file_name=file_name, key=key)


def _render_run_results(run_id: str) -> None:
    """Render a run's leads table + report from disk. Called unconditionally
    on every script execution (not inside the Run button's branch), so a
    Streamlit rerun triggered by anything else on the page -- a Review tab
    Good/Bad click, a download button -- never wipes the last run's results."""
    state_path = RUNS_DIR / run_id / "state.json"
    if not state_path.exists():
        return
    state = _load_run(run_id)
    st.success(f"Run {state.run_id} finished with status={state.status}")
    if state.leads:
        df = pd.DataFrame([ld.to_dict() for ld in state.leads.values()]).sort_values(
            "score", ascending=False
        )
        st.dataframe(df[["name", "niche", "score", "phone", "website", "hook"]])
        csv_path = RUNS_DIR / run_id / "leads.csv"
        if csv_path.exists():
            _download_button("Download CSV", csv_path.read_bytes(), f"{run_id}_leads.csv", key=f"dl_{run_id}")
    report_path = RUNS_DIR / run_id / "report.md"
    if report_path.exists():
        st.markdown(report_path.read_text(encoding="utf-8"))


tab_run, tab_review, tab_learn = st.tabs(["Run", "Review", "Learn"])

with tab_run:
    goal = st.text_input("Goal", placeholder="Find 30 dental clinics in Pune that would buy an AI phone receptionist")
    max_steps = st.number_input("Max steps", min_value=1, max_value=100, value=25)
    if st.button("Run", type="primary") and goal:
        try:
            llm = GeminiLLM()
        except LLMError as exc:
            st.error(str(exc))
        else:
            feed = st.container(height=300)
            log_lines: list[str] = []

            def on_step(step: Step, _state: RunState) -> None:
                status = "OK" if step.ok else "FAIL"
                log_lines.append(f"[{step.n:02d}] ({status}) {step.action}({step.args}) -> {step.observation}")
                feed.code("\n".join(log_lines))

            agent = Agent(llm, MEMORY, max_steps=int(max_steps), runs_dir=RUNS_DIR, on_step=on_step)
            with st.spinner("Running agent..."):
                state = agent.run(goal)
            # Agent.run() always persists state.json/leads.csv/report.md
            # (try/finally, even on failure) before returning, so it's safe
            # to remember just the id here and render from disk below.
            st.session_state["last_run_id"] = state.run_id

    last_run_id = st.session_state.get("last_run_id")
    if last_run_id:
        _render_run_results(last_run_id)

with tab_review:
    run_ids = _list_run_ids()
    if not run_ids:
        st.info("No runs yet. Use the Run tab first.")
    else:
        picked = st.selectbox("Run", run_ids)
        state = _load_run(picked)
        leads = sorted(state.leads.values(), key=lambda ld: ld.score, reverse=True)

        labels = {r["lead_id"]: r["label"] for r in MEMORY.get_labels()}
        n_good = sum(1 for v in labels.values() if v == "good")
        n_bad = sum(1 for v in labels.values() if v == "bad")
        st.caption(f"Labeled so far (all runs): {n_good} good, {n_bad} bad")

        for lead in leads:
            cols = st.columns([4, 1, 1, 1])
            current = labels.get(lead.id)
            cols[0].write(f"**{lead.name}** ({lead.niche}, score={lead.score:.0f}) -- {current or 'unlabeled'}")
            if cols[1].button("Good", key=f"good_{lead.id}"):
                MEMORY.add_label(lead, "good", picked)
                st.rerun()
            if cols[2].button("Bad", key=f"bad_{lead.id}"):
                MEMORY.add_label(lead, "bad", picked)
                st.rerun()
            cols[3].write(", ".join(lead.reasons[:2]) if lead.reasons else "")

with tab_learn:
    if st.button("Learn"):
        try:
            llm = GeminiLLM()
        except LLMError as exc:
            st.error(str(exc))
        else:
            report = learn(MEMORY, llm)
            st.write(report.message)
            if report.ok:
                col1, col2 = st.columns(2)
                col1.metric("Test accuracy", f"{report.acc_after:.1f}%", f"{report.acc_after - report.acc_before:+.1f}")
                if report.p_at_10_after is None or report.p_at_10_before is None:
                    col2.metric("Precision@k", "n/a (test set too small)")
                else:
                    col2.metric("Precision@k", f"{report.p_at_10_after:.1f}%", f"{report.p_at_10_after - report.p_at_10_before:+.1f}")

                if report.added:
                    st.write("**Added rules**")
                    st.table([r.to_dict() for r in report.added])
                if report.removed:
                    st.write("**Removed rules**")
                    st.table([r.to_dict() for r in report.removed])
                if report.rejected:
                    st.write("**Rejected candidates**")
                    st.table(report.rejected)

    st.subheader("Current rules")
    rules = MEMORY.load_rules()
    if rules:
        st.table([r.to_dict() for r in rules])
    else:
        st.caption("No learned rules yet.")

    st.subheader("Accuracy over time")
    history = MEMORY.get_history()
    if history:
        df = pd.DataFrame(history)
        df["run"] = range(1, len(df) + 1)
        st.line_chart(df.set_index("run")[["acc_after", "p_at_10_after"]])
    else:
        st.caption("No learning runs yet.")
