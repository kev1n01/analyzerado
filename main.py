import streamlit as st

pg = st.navigation([
    st.Page("src/pages/app.py", title="Analyzer", icon=":material/wand_stars:"), 
    st.Page("src/pages/request.py", title="Request Builder", icon=":material/search_gear:", url_path="/query-builder"),
    st.Page("src/pages/auth.py", title="Auth Config", icon=":material/security:", url_path="/auth-config")
])
pg.run()
