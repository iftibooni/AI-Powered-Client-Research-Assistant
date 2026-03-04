from __future__ import annotations

import json
import os
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv

from research_assistant.llm import default_model_for, get_client, list_available_models
from research_assistant.pipeline import run_research


load_dotenv()


st.set_page_config(page_title="AI Research Assistant", layout="wide")
st.title("AI-Powered Client Research Assistant")

with st.sidebar:
    st.subheader("Inputs")
    url = st.text_input("Client website URL", placeholder="https://example.com")
    niche_hint = st.text_input("Niche / keywords (optional)", placeholder="e.g., B2B SaaS bookkeeping")

    st.subheader("LLM")
    client, base_url = get_client()
    model_default = default_model_for(base_url)

    available_models = list_available_models(client)
    if available_models:
        # Prefer a reasonable default if present in the provider list.
        idx = available_models.index(model_default) if model_default in available_models else 0
        model = st.selectbox("Model", options=available_models, index=idx)
    else:
        model = st.text_input("Model", value=model_default)
        st.caption("Could not list models from provider; using manual model input.")

    use_tools = st.checkbox("Allow tool-calling (web_search, fetch_url)", value=True)
    use_external_search = st.checkbox("Call external search script", value=True)

    run_btn = st.button("Run research", type="primary", use_container_width=True)


def _save_output(payload: dict) -> str:
    os.makedirs("outputs", exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join("outputs", f"research-{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        # Pydantic may contain types like HttpUrl; default=str ensures JSON-safe output.
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    return path


if run_btn:
    if not url.strip():
        st.error("Please enter a website URL.")
        st.stop()

    with st.status("Running research workflow…", expanded=True) as status:
        st.write("Scraping key pages…")
        result = run_research(
            client=client,
            model=model.strip(),
            url=url.strip(),
            niche_hint=niche_hint.strip(),
            use_tools=use_tools,
            use_external_search=use_external_search,
        )
        status.update(label="Done", state="complete", expanded=False)

    # Use Pydantic's JSON-friendly dump to avoid non-serializable types (e.g. HttpUrl).
    payload = result.model_dump(mode="json")
    saved_path = _save_output(payload)

    col1, col2 = st.columns([1, 1])
    with col1:
        st.subheader("Summary")
        st.write(payload.get("summary", ""))

        st.subheader("Basics")
        st.json(payload.get("basics", {}))

        st.subheader("Positioning ideas")
        for idea in payload.get("positioning_ideas", []) or []:
            with st.expander(idea.get("angle", "Positioning idea")):
                st.write(f"**Who it's for**: {idea.get('who_its_for','')}")
                st.write(f"**Key benefit**: {idea.get('key_benefit','')}")
                st.write(f"**Tagline**: {idea.get('sample_tagline','')}")
                if idea.get("proof_points"):
                    st.write("**Proof points**")
                    st.write(idea.get("proof_points"))

    with col2:
        st.subheader("Content ideas")
        for ci in payload.get("content_ideas", []) or []:
            with st.expander(ci.get("title", "Content idea")):
                st.write(f"**Format**: {ci.get('format','')}")
                st.write(f"**Intent**: {ci.get('intent','')}")
                st.write(ci.get("why_it_works", ""))
                if ci.get("outline_points"):
                    st.write(ci.get("outline_points"))

        st.subheader("Competitors (best-effort)")
        st.json(payload.get("competitors", []))

    st.subheader("Full structured output (JSON)")
    st.json(payload)
    st.caption(f"Saved to `{saved_path}`")

else:
    st.info("Enter a URL in the sidebar and click **Run research**.")

