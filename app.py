from pathlib import Path
import pandas as pd
import streamlit as st
from main import run_store

st.set_page_config(page_title="Book Store Dashboard", layout="wide")

#every STORE folder next to app
BASE = Path(__file__).parent
stores = sorted(p.name for p in BASE.glob("STORE*") if p.is_dir())

@st.cache_data
def load(folder):
    return run_store(BASE / folder)

folder = st.sidebar.selectbox("Store", stores)
res = load(folder)
daily = res["daily_rev_df"]
top_buyer = res["top_buyer"]

st.title(f" Book Store Dashboard — {folder}")

#kpi row
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total revenue", f"${daily['paid_price'].sum():,.2f}")
c2.metric("Unique users", res["unique_users"])
c3.metric("Unique author sets", res["unique_author_sets"])
c4.metric("Best buyer", f"id {top_buyer['id']}", f"${top_buyer['spending']:,.2f}")

tab_rev, tab_users, tab_authors = st.tabs(["Revenue", "Users", "Authors"])

with tab_rev:
    st.subheader("Daily revenue")
    chart = daily.assign(date=pd.to_datetime(daily["date"])).set_index("date")["paid_price"]
    st.line_chart(chart, x_label="date", y_label="revenue ($)")

    st.subheader("Top 5 days by revenue")
    top5 = pd.DataFrame(res["top_5_days"], columns=["date", "revenue ($)"])
    st.dataframe(top5, hide_index=True, width="stretch",
                 column_config={"revenue ($)": st.column_config.NumberColumn(format="$%.2f")})

with tab_users:
    st.metric("Number of unique users", res["unique_users"])
    st.subheader("Best buyer (with aliases)")
    st.write(f"Total spending: **${top_buyer['spending']:,.2f}**")
    st.code(str(top_buyer["aliases"]), language="python")

with tab_authors:
    st.metric("Number of unique sets of authors", res["unique_author_sets"])
    st.subheader("Most popular author(s)")
    for author in res["top_authors"]:
        st.markdown(f"- **{author}**")
