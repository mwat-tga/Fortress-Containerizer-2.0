import streamlit as st
import pandas as pd
import math
from io import BytesIO
from datetime import datetime

st.set_page_config(page_title="Container Splitter", layout="wide")

MAX_CONTAINER_WEIGHT = 43900

@st.cache_data
def load_product_metadata():
    return pd.read_csv("product-meta-data.csv")

def normalize_columns(df):
    df.columns = df.columns.str.strip().str.replace(r"[\s_\-]+", " ", regex=True).str.lower()
    df = df.loc[:, ~df.columns.str.contains("unnamed")]
    col_map = {
        "product code": "Product Code",
        "description": "Description",
        "manufacturer sku": "Manufacturer SKU",
        "unit qty": "Unit Qty",
        "weight per piece": "Weight per piece",
        "category": "category",
        "color": "color",
        "max": "Max",
        "available stock": "Available Stock",
        "stock on order": "Stock On Order"
    }
    df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}, inplace=True)
    return df

def load_and_prepare_data(file, metadata_df):
    df = pd.read_csv(file) if file.name.endswith(".csv") else pd.read_excel(file)
    df = normalize_columns(df)
    metadata_df = normalize_columns(metadata_df)
    df = df.merge(metadata_df, on="Product Code", how="left")

    for col in ["Product Code", "Available Stock", "Stock On Order", "Max", "Unit Qty", "Weight per piece"]:
        if col not in df.columns:
            st.error(f"Missing column: {col}")
            st.stop()

    df['Suggested Pcs'] = df.apply(
        lambda row: math.ceil(max(row['Max'] - (row['Available Stock'] + row['Stock On Order']), 0) / row['Unit Qty']) * row['Unit Qty'], axis=1)
    df['Suggested Units'] = df['Suggested Pcs'] / df['Unit Qty']
    df['Total Weight'] = df['Suggested Pcs'] * df['Weight per piece']
    return df

def force_rotate_units(df, interleave_mode=True):
    # simplified, add your logic
    return pd.DataFrame(), []

def updated_export_with_summary(summary_df, container_weights, interleave_mode, auto_topoff):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        pd.DataFrame({"hello": [1]}).to_excel(writer, index=False)  # dummy
    output.seek(0)
    return output

# UI
st.title("📦 SKU Container Splitter")

distribution_mode = st.radio("Distribution Mode", ["Evenly Spread SKUs", "Group Similar Products"])
interleave_mode = distribution_mode == "Evenly Spread SKUs"
auto_topoff = st.toggle("Auto-fill final container with extra best-sellers (recommended)", value=True)

uploaded_file = st.file_uploader("Upload ERP File (Excel or CSV)", type=["xlsx", "csv"])

if uploaded_file:
    if st.button("🚀 Process File"):
        with st.spinner("Processing your file..."):
            try:
                meta_df = load_product_metadata()
                df = load_and_prepare_data(uploaded_file, meta_df)
                summary, container_weights = force_rotate_units(df, interleave_mode)
                output = updated_export_with_summary(summary, container_weights, interleave_mode, auto_topoff)
                st.download_button("Download Results", data=output.getvalue(), file_name="container_results.xlsx")
            except Exception as e:
                st.error(f"Something went wrong: {e}")
