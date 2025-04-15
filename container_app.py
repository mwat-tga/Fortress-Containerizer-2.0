import streamlit as st
import pandas as pd
import math
import base64
st.set_page_config(page_title="Container Splitter", layout="wide")
from io import BytesIO
from datetime import datetime
from io import BytesIO
from datetime import datetime
MAX_CONTAINER_WEIGHT = 43900
if uploaded_file:
    st.markdown(f"**Uploaded File:** {uploaded_file.name}")
    with st.spinner('Processing your file...'):
    try:
    meta_df = load_product_metadata()
    df = load_and_prepare_data(uploaded_file, meta_df)
    summary, container_weights = force_rotate_units(df, interleave_mode)
    output = updated_export_with_summary(summary, container_weights, interleave_mode, auto_topoff)
    st.download_button(
    label="📥 Download Container Excel (Multiple Sheets)",
    data=output.getvalue(),
    file_name="containerized_orders_by_container.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    except Exception as e:
                st.error(f"Something went wrong during processing: {e}")
    st.info('📥 Please upload an Excel or CSV file to begin.')
st.title("📦 SKU Container Splitter")
st.markdown("Upload your ERP export file and we'll split suggested order quantities into balanced, weight-optimized containers.")
distribution_mode = st.radio('Distribution Mode', ['Evenly Spread SKUs', 'Group Similar Products'])
interleave_mode = distribution_mode == 'Evenly Spread SKUs'
distribution_mode = st.radio(
    "📦 Distribution Mode",
    ["Evenly Spread SKUs", "Group Similar Products"]
)
auto_topoff = st.toggle('Auto-fill final container with extra best-sellers (recommended)', value=True)
@st.cache_data
def load_product_metadata():
    return pd.read_csv("product-meta-data.csv")
def normalize_columns(df):
    import re
    col_map = {
        col: re.sub(r'\s+', ' ', col.strip().lower().replace('_', ' ').replace('-', ' ')).strip()
        for col in df.columns
    }
    df.rename(columns=col_map, inplace=True)
    df = df.loc[:, ~df.columns.str.contains("unnamed")]
    rename_map = {
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
    df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)
    return df
def load_and_prepare_data(file, metadata_df):
    if file.name.endswith(".csv"):
        df = pd.read_csv(file)
        df = pd.read_excel(file)
    df = normalize_columns(df)
    metadata_df = normalize_columns(metadata_df)
    df = df.merge(metadata_df, on="Product Code", how="left")
    required_cols = ['Product Code', 'Available Stock', 'Stock On Order', 'Max']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        st.stop()
    if 'Unit Qty' not in df.columns or 'Weight per piece' not in df.columns:
        st.stop()
    df['Suggested Pcs'] = df.apply(
        lambda row: math.ceil(
            max(row['Max'] - (row['Available Stock'] + row['Stock On Order']), 0) / row['Unit Qty']
        ) * row['Unit Qty'], axis=1)
    df['Suggested Units'] = df['Suggested Pcs'] / df['Unit Qty']
    df['Total Weight'] = df.apply(lambda row: row['Suggested Pcs'] * row['Weight per piece'], axis=1)
    return df
def force_rotate_units(df, interleave_mode=True):
    containers = []
    container_weights = []
    sku_units = []
    for _, row in df.iterrows():
        for _ in range(int(row['Suggested Units'])):
            sku_units.append({
                'Product Code': row['Product Code'],
                'Manufacturer SKU': row['Manufacturer SKU'],
                'Description': row['Description'],
                'Category': row.get('category', 'Unknown'),
                'Color': row.get('color', 'Unknown'),
                'Unit Qty': row['Unit Qty'],
                'Weight': row['Unit Qty'] * row['Weight per piece'],
                'Top Off': False
            })
    num_containers = max(1, math.ceil(sum([u['Weight'] for u in sku_units]) / MAX_CONTAINER_WEIGHT))
    containers = [[] for _ in range(num_containers)]
    container_weights = [0] * num_containers
    if interleave_mode:
        container_idx = 0
        for unit in sku_units:
            placed = False
            attempts = 0
            while not placed and attempts < num_containers:
                if container_weights[container_idx] + unit['Weight'] <= MAX_CONTAINER_WEIGHT:
                    containers[container_idx].append(unit)
                    container_weights[container_idx] += unit['Weight']
                    placed = True
                container_idx = (container_idx + 1) % num_containers
                attempts += 1
        for unit in sku_units:
            placed = False
            for i in range(num_containers):
                if container_weights[i] + unit['Weight'] <= MAX_CONTAINER_WEIGHT:
                    containers[i].append(unit)
                    container_weights[i] += unit['Weight']
                    placed = True
                    break
            if not placed:
                containers.append([unit])
                container_weights.append(unit['Weight'])
    final_output = []
    for i, container in enumerate(containers, 1):
        for item in container:
            item['Container #'] = i
            final_output.append(item)
    df_out = pd.DataFrame(final_output)
    summary_df = df_out.groupby(['Container #', 'Product Code', 'Manufacturer SKU', 'Description', 'Category', 'Color', 'Top Off']).agg({
        'Unit Qty': 'sum',
        'Weight': 'sum'
    }).reset_index().rename(columns={'Weight': 'Total Weight'})
    return summary_df, container_weights
def updated_export_with_summary(summary_df, container_weights, interleave_mode, auto_topoff):
    today = datetime.today().strftime('%Y-%m-%d')
    mode_label = "Evenly Spread SKUs" if interleave_mode else "Group Similar Products"
    topoff_label = "Enabled" if auto_topoff else "Disabled"
    summary_rows = []
    for idx, weight in enumerate(container_weights, start=1):
        unit_total = summary_df[summary_df["Container #"] == idx]["Unit Qty"].sum()
        summary_rows.append({
            "Container #": f"Container {idx}",
            "Weight (lbs)": round(weight, 2),
            "Units": int(unit_total)
        })
    meta_info = pd.DataFrame({
        "Report Title": ["Fortress Containerization Output"],
        "Date": [today],
        "Distribution Mode": [mode_label],
        "Top-Off Logic": [topoff_label],
        "Total Containers": [len(container_weights)]
    })
    summary_df_final = pd.DataFrame(summary_rows)
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        meta_info.to_excel(writer, index=False, sheet_name="Summary")
        summary_df_final.to_excel(writer, index=False, startrow=4, sheet_name="Summary")
        for container_num, group in summary_df.groupby("Container #"):
            sheet_name = f"Container {container_num}"[:31]
            group.to_excel(writer, sheet_name=sheet_name, index=False)
    output.seek(0)
    return output
# Handle single file upload once
uploaded_file = st.file_uploader('Upload ERP File (Excel or CSV)', type=['xlsx', 'csv'], key='erp_file')

if uploaded_file:
    st.markdown(f"**Uploaded File:** {uploaded_file.name}")
    with st.spinner('Processing your file...'):
    try:
    meta_df = load_product_metadata()
    df = load_and_prepare_data(uploaded_file, meta_df)
    summary, container_weights = force_rotate_units(df, interleave_mode)
    output = updated_export_with_summary(summary, container_weights, interleave_mode, auto_topoff)
    label="📥 Download Container Excel (Multiple Sheets)",
    data=output.getvalue(),
    file_name="containerized_orders_by_container.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    except Exception as e:
st.error(f"Something went wrong during processing: {e}")
st.info('📥 Please upload an Excel or CSV file to begin.')

st.title("📦 SKU Container Splitter")
st.markdown("Upload your ERP export file and we'll split suggested order quantities into balanced, weight-optimized containers.")
distribution_mode = st.radio('Distribution Mode', ['Evenly Spread SKUs', 'Group Similar Products'])
interleave_mode = distribution_mode == 'Evenly Spread SKUs'
distribution_mode = st.radio(
    "📦 Distribution Mode",
    ["Evenly Spread SKUs", "Group Similar Products"]
)
auto_topoff = st.toggle('Auto-fill final container with extra best-sellers (recommended)', value=True)
@st.cache_data
def load_product_metadata():
    return pd.read_csv("product-meta-data.csv")
def normalize_columns(df):
    import re
    col_map = {
        col: re.sub(r'\s+', ' ', col.strip().lower().replace('_', ' ').replace('-', ' ')).strip()
        for col in df.columns
    }
    df.rename(columns=col_map, inplace=True)
    df = df.loc[:, ~df.columns.str.contains("unnamed")]
    rename_map = {
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
    df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)
    return df
def load_and_prepare_data(file, metadata_df):
    if file.name.endswith(".csv"):
        df = pd.read_csv(file)
        df = pd.read_excel(file)
    df = normalize_columns(df)
    metadata_df = normalize_columns(metadata_df)
    df = df.merge(metadata_df, on="Product Code", how="left")
    required_cols = ['Product Code', 'Available Stock', 'Stock On Order', 'Max']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        st.stop()
    if 'Unit Qty' not in df.columns or 'Weight per piece' not in df.columns:
        st.stop()
    df['Suggested Pcs'] = df.apply(
        lambda row: math.ceil(
            max(row['Max'] - (row['Available Stock'] + row['Stock On Order']), 0) / row['Unit Qty']
        ) * row['Unit Qty'], axis=1)
    df['Suggested Units'] = df['Suggested Pcs'] / df['Unit Qty']
    df['Total Weight'] = df.apply(lambda row: row['Suggested Pcs'] * row['Weight per piece'], axis=1)
    return df
def force_rotate_units(df, interleave_mode=True):
    containers = []
    container_weights = []
    sku_units = []
    for _, row in df.iterrows():
        for _ in range(int(row['Suggested Units'])):
            sku_units.append({
                'Product Code': row['Product Code'],
                'Manufacturer SKU': row['Manufacturer SKU'],
                'Description': row['Description'],
                'Category': row.get('category', 'Unknown'),
                'Color': row.get('color', 'Unknown'),
                'Unit Qty': row['Unit Qty'],
                'Weight': row['Unit Qty'] * row['Weight per piece'],
                'Top Off': False
            })
    num_containers = max(1, math.ceil(sum([u['Weight'] for u in sku_units]) / MAX_CONTAINER_WEIGHT))
    containers = [[] for _ in range(num_containers)]
    container_weights = [0] * num_containers
    if interleave_mode:
        container_idx = 0
        for unit in sku_units:
            placed = False
            attempts = 0
            while not placed and attempts < num_containers:
                if container_weights[container_idx] + unit['Weight'] <= MAX_CONTAINER_WEIGHT:
                    containers[container_idx].append(unit)
                    container_weights[container_idx] += unit['Weight']
                    placed = True
                container_idx = (container_idx + 1) % num_containers
                attempts += 1
        for unit in sku_units:
            placed = False
            for i in range(num_containers):
                if container_weights[i] + unit['Weight'] <= MAX_CONTAINER_WEIGHT:
                    containers[i].append(unit)
                    container_weights[i] += unit['Weight']
                    placed = True
                    break
            if not placed:
                containers.append([unit])
                container_weights.append(unit['Weight'])
    final_output = []
    for i, container in enumerate(containers, 1):
        for item in container:
            item['Container #'] = i
            final_output.append(item)
    df_out = pd.DataFrame(final_output)
    summary_df = df_out.groupby(['Container #', 'Product Code', 'Manufacturer SKU', 'Description', 'Category', 'Color', 'Top Off']).agg({
        'Unit Qty': 'sum',
        'Weight': 'sum'
    }).reset_index().rename(columns={'Weight': 'Total Weight'})
    return summary_df, container_weights
def updated_export_with_summary(summary_df, container_weights, interleave_mode, auto_topoff):
    today = datetime.today().strftime('%Y-%m-%d')
    mode_label = "Evenly Spread SKUs" if interleave_mode else "Group Similar Products"
    topoff_label = "Enabled" if auto_topoff else "Disabled"
    summary_rows = []
    for idx, weight in enumerate(container_weights, start=1):
        unit_total = summary_df[summary_df["Container #"] == idx]["Unit Qty"].sum()
        summary_rows.append({
            "Container #": f"Container {idx}",
            "Weight (lbs)": round(weight, 2),
            "Units": int(unit_total)
        })
    meta_info = pd.DataFrame({
        "Report Title": ["Fortress Containerization Output"],
        "Date": [today],
        "Distribution Mode": [mode_label],
        "Top-Off Logic": [topoff_label],
        "Total Containers": [len(container_weights)]
    })
    summary_df_final = pd.DataFrame(summary_rows)
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        meta_info.to_excel(writer, index=False, sheet_name="Summary")
        summary_df_final.to_excel(writer, index=False, startrow=4, sheet_name="Summary")
        for container_num, group in summary_df.groupby("Container #"):
            sheet_name = f"Container {container_num}"[:31]
            group.to_excel(writer, sheet_name=sheet_name, index=False)
    output.seek(0)
    return output
# Handle single file upload once
uploaded_file = st.file_uploader('Upload ERP File (Excel or CSV)', type=['xlsx', 'csv'], key='erp_file')
if uploaded_file:
    st.markdown(f"**Uploaded File:** {uploaded_file.name}")
    if st.button('🚀 Process File', key='process_file_btn'):
    with st.spinner('Processing your file...'):
    try:
    meta_df = load_product_metadata()
    df = load_and_prepare_data(uploaded_file, meta_df)
    summary, container_weights = force_rotate_units(df, interleave_mode)
    output = updated_export_with_summary(summary, container_weights, interleave_mode, auto_topoff)
    except Exception as e:
                st.error(f"Something went wrong during processing: {e}")
distribution_mode = st.radio(
    "📦 Distribution Mode",
    ["Evenly Spread SKUs", "Group Similar Products"]
)
auto_topoff = st.toggle('Auto-fill final container with extra best-sellers (recommended)', value=True)
@st.cache_data
def load_product_metadata():
    return pd.read_csv("product-meta-data.csv")
def normalize_columns(df):
    import re
    col_map = {
        col: re.sub(r'\s+', ' ', col.strip().lower().replace('_', ' ').replace('-', ' ')).strip()
        for col in df.columns
    }
    df.rename(columns=col_map, inplace=True)
    df = df.loc[:, ~df.columns.str.contains("unnamed")]
    rename_map = {
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
    df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)
    return df
def load_and_prepare_data(file, metadata_df):
    if file.name.endswith(".csv"):
        df = pd.read_csv(file)
        df = pd.read_excel(file)
    df = normalize_columns(df)
    metadata_df = normalize_columns(metadata_df)
    df = df.merge(metadata_df, on="Product Code", how="left")
    required_cols = ['Product Code', 'Available Stock', 'Stock On Order', 'Max']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        st.stop()
    if 'Unit Qty' not in df.columns or 'Weight per piece' not in df.columns:
        st.stop()
    df['Suggested Pcs'] = df.apply(
        lambda row: math.ceil(
            max(row['Max'] - (row['Available Stock'] + row['Stock On Order']), 0) / row['Unit Qty']
        ) * row['Unit Qty'], axis=1)
    df['Suggested Units'] = df['Suggested Pcs'] / df['Unit Qty']
    df['Total Weight'] = df.apply(lambda row: row['Suggested Pcs'] * row['Weight per piece'], axis=1)
    return df
def force_rotate_units(df, interleave_mode=True):
    containers = []
    container_weights = []
    sku_units = []
    for _, row in df.iterrows():
        for _ in range(int(row['Suggested Units'])):
            sku_units.append({
                'Product Code': row['Product Code'],
                'Manufacturer SKU': row['Manufacturer SKU'],
                'Description': row['Description'],
                'Category': row.get('category', 'Unknown'),
                'Color': row.get('color', 'Unknown'),
                'Unit Qty': row['Unit Qty'],
                'Weight': row['Unit Qty'] * row['Weight per piece'],
                'Top Off': False
            })
    num_containers = max(1, math.ceil(sum([u['Weight'] for u in sku_units]) / MAX_CONTAINER_WEIGHT))
    containers = [[] for _ in range(num_containers)]
    container_weights = [0] * num_containers
    if interleave_mode:
        container_idx = 0
        for unit in sku_units:
            placed = False
            attempts = 0
            while not placed and attempts < num_containers:
                if container_weights[container_idx] + unit['Weight'] <= MAX_CONTAINER_WEIGHT:
                    containers[container_idx].append(unit)
                    container_weights[container_idx] += unit['Weight']
                    placed = True
                container_idx = (container_idx + 1) % num_containers
                attempts += 1
        for unit in sku_units:
            placed = False
            for i in range(num_containers):
                if container_weights[i] + unit['Weight'] <= MAX_CONTAINER_WEIGHT:
                    containers[i].append(unit)
                    container_weights[i] += unit['Weight']
                    placed = True
                    break
            if not placed:
                containers.append([unit])
                container_weights.append(unit['Weight'])
    final_output = []
    for i, container in enumerate(containers, 1):
        for item in container:
            item['Container #'] = i
            final_output.append(item)
    df_out = pd.DataFrame(final_output)
    summary_df = df_out.groupby(['Container #', 'Product Code', 'Manufacturer SKU', 'Description', 'Category', 'Color', 'Top Off']).agg({
        'Unit Qty': 'sum',
        'Weight': 'sum'
    }).reset_index().rename(columns={'Weight': 'Total Weight'})
    return summary_df, container_weights
def updated_export_with_summary(summary_df, container_weights, interleave_mode, auto_topoff):
    today = datetime.today().strftime('%Y-%m-%d')
    mode_label = "Evenly Spread SKUs" if interleave_mode else "Group Similar Products"
    topoff_label = "Enabled" if auto_topoff else "Disabled"
    summary_rows = []
    for idx, weight in enumerate(container_weights, start=1):
        unit_total = summary_df[summary_df["Container #"] == idx]["Unit Qty"].sum()
        summary_rows.append({
            "Container #": f"Container {idx}",
            "Weight (lbs)": round(weight, 2),
            "Units": int(unit_total)
        })
    meta_info = pd.DataFrame({
        "Report Title": ["Fortress Containerization Output"],
        "Date": [today],
        "Distribution Mode": [mode_label],
        "Top-Off Logic": [topoff_label],
        "Total Containers": [len(container_weights)]
    })
    summary_df_final = pd.DataFrame(summary_rows)
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        meta_info.to_excel(writer, index=False, sheet_name="Summary")
        summary_df_final.to_excel(writer, index=False, startrow=4, sheet_name="Summary")
        for container_num, group in summary_df.groupby("Container #"):
            sheet_name = f"Container {container_num}"[:31]
            group.to_excel(writer, sheet_name=sheet_name, index=False)
    output.seek(0)
    return output
# Handle single file upload once
uploaded_file = st.file_uploader('Upload ERP File (Excel or CSV)', type=['xlsx', 'csv'], key='erp_file')

if uploaded_file:
    st.markdown(f"**Uploaded File:** {uploaded_file.name}")
    with st.spinner('Processing your file...'):
    try:
    meta_df = load_product_metadata()
    df = load_and_prepare_data(uploaded_file, meta_df)
    summary, container_weights = force_rotate_units(df, interleave_mode)
    output = updated_export_with_summary(summary, container_weights, interleave_mode, auto_topoff)
    label="📥 Download Container Excel (Multiple Sheets)",
    data=output.getvalue(),
    file_name="containerized_orders_by_container.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    except Exception as e:
st.error(f"Something went wrong during processing: {e}")
st.info('📥 Please upload an Excel or CSV file to begin.')

st.title("📦 SKU Container Splitter")
st.markdown("Upload your ERP export file and we'll split suggested order quantities into balanced, weight-optimized containers.")
distribution_mode = st.radio('Distribution Mode', ['Evenly Spread SKUs', 'Group Similar Products'])
interleave_mode = distribution_mode == 'Evenly Spread SKUs'
distribution_mode = st.radio(
    "📦 Distribution Mode",
    ["Evenly Spread SKUs", "Group Similar Products"]
)
auto_topoff = st.toggle('Auto-fill final container with extra best-sellers (recommended)', value=True)
@st.cache_data
def load_product_metadata():
    return pd.read_csv("product-meta-data.csv")
def normalize_columns(df):
    import re
    col_map = {
        col: re.sub(r'\s+', ' ', col.strip().lower().replace('_', ' ').replace('-', ' ')).strip()
        for col in df.columns
    }
    df.rename(columns=col_map, inplace=True)
    df = df.loc[:, ~df.columns.str.contains("unnamed")]
    rename_map = {
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
    df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}, inplace=True)
    return df
def load_and_prepare_data(file, metadata_df):
    if file.name.endswith(".csv"):
        df = pd.read_csv(file)
        df = pd.read_excel(file)
    df = normalize_columns(df)
    metadata_df = normalize_columns(metadata_df)
    df = df.merge(metadata_df, on="Product Code", how="left")
    required_cols = ['Product Code', 'Available Stock', 'Stock On Order', 'Max']
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        st.stop()
    if 'Unit Qty' not in df.columns or 'Weight per piece' not in df.columns:
        st.stop()
    df['Suggested Pcs'] = df.apply(
        lambda row: math.ceil(
            max(row['Max'] - (row['Available Stock'] + row['Stock On Order']), 0) / row['Unit Qty']
        ) * row['Unit Qty'], axis=1)
    df['Suggested Units'] = df['Suggested Pcs'] / df['Unit Qty']
    df['Total Weight'] = df.apply(lambda row: row['Suggested Pcs'] * row['Weight per piece'], axis=1)
    return df
def force_rotate_units(df, interleave_mode=True):
    containers = []
    container_weights = []
    sku_units = []
    for _, row in df.iterrows():
        for _ in range(int(row['Suggested Units'])):
            sku_units.append({
                'Product Code': row['Product Code'],
                'Manufacturer SKU': row['Manufacturer SKU'],
                'Description': row['Description'],
                'Category': row.get('category', 'Unknown'),
                'Color': row.get('color', 'Unknown'),
                'Unit Qty': row['Unit Qty'],
                'Weight': row['Unit Qty'] * row['Weight per piece'],
                'Top Off': False
            })
    num_containers = max(1, math.ceil(sum([u['Weight'] for u in sku_units]) / MAX_CONTAINER_WEIGHT))
    containers = [[] for _ in range(num_containers)]
    container_weights = [0] * num_containers
    if interleave_mode:
        container_idx = 0
        for unit in sku_units:
            placed = False
            attempts = 0
            while not placed and attempts < num_containers:
                if container_weights[container_idx] + unit['Weight'] <= MAX_CONTAINER_WEIGHT:
                    containers[container_idx].append(unit)
                    container_weights[container_idx] += unit['Weight']
                    placed = True
                container_idx = (container_idx + 1) % num_containers
                attempts += 1
        for unit in sku_units:
            placed = False
            for i in range(num_containers):
                if container_weights[i] + unit['Weight'] <= MAX_CONTAINER_WEIGHT:
                    containers[i].append(unit)
                    container_weights[i] += unit['Weight']
                    placed = True
                    break
            if not placed:
                containers.append([unit])
                container_weights.append(unit['Weight'])
    final_output = []
    for i, container in enumerate(containers, 1):
        for item in container:
            item['Container #'] = i
            final_output.append(item)
    df_out = pd.DataFrame(final_output)
    summary_df = df_out.groupby(['Container #', 'Product Code', 'Manufacturer SKU', 'Description', 'Category', 'Color', 'Top Off']).agg({
        'Unit Qty': 'sum',
        'Weight': 'sum'
    }).reset_index().rename(columns={'Weight': 'Total Weight'})
    return summary_df, container_weights
def updated_export_with_summary(summary_df, container_weights, interleave_mode, auto_topoff):
    today = datetime.today().strftime('%Y-%m-%d')
    mode_label = "Evenly Spread SKUs" if interleave_mode else "Group Similar Products"
    topoff_label = "Enabled" if auto_topoff else "Disabled"
    summary_rows = []
    for idx, weight in enumerate(container_weights, start=1):
        unit_total = summary_df[summary_df["Container #"] == idx]["Unit Qty"].sum()
        summary_rows.append({
            "Container #": f"Container {idx}",
            "Weight (lbs)": round(weight, 2),
            "Units": int(unit_total)
        })
    meta_info = pd.DataFrame({
        "Report Title": ["Fortress Containerization Output"],
        "Date": [today],
        "Distribution Mode": [mode_label],
        "Top-Off Logic": [topoff_label],
        "Total Containers": [len(container_weights)]
    })
    summary_df_final = pd.DataFrame(summary_rows)
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        meta_info.to_excel(writer, index=False, sheet_name="Summary")
        summary_df_final.to_excel(writer, index=False, startrow=4, sheet_name="Summary")
        for container_num, group in summary_df.groupby("Container #"):
            sheet_name = f"Container {container_num}"[:31]
            group.to_excel(writer, sheet_name=sheet_name, index=False)
    output.seek(0)
    return output
# Handle single file upload once
uploaded_file = st.file_uploader('Upload ERP File (Excel or CSV)', type=['xlsx', 'csv'], key='erp_file')
if uploaded_file:
    st.markdown(f"**Uploaded File:** {uploaded_file.name}")
    if st.button('🚀 Process File', key='process_file_btn'):
    with st.spinner('Processing your file...'):
    try:
    meta_df = load_product_metadata()
    df = load_and_prepare_data(uploaded_file, meta_df)
    summary, container_weights = force_rotate_units(df, interleave_mode)
    output = updated_export_with_summary(summary, container_weights, interleave_mode, auto_topoff)
    except Exception as e:
                st.error(f"Something went wrong during processing: {e}")
