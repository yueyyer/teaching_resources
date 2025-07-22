import streamlit as st

def load_sidebar_css():
    st.markdown("""
    <style>
    [data-testid="stSidebar"] {
        background-color: #e8f5e9;
        padding: 2rem 1.5rem;
    }

    .sidebar-title {
        font-size: 24px;
        font-weight: bold;
        color: #2e7d32;
        margin-bottom: 20px;
    }

    button[kind="secondary"] {
        background-color: #2e7d32 !important;
        color: white !important;
        border-radius: 8px;
        padding: 0.5rem 1rem;
        font-weight: 600;
        transition: background-color 0.3s ease;
        margin-bottom: 20px;
        border: none;
    }

    button[kind="secondary"]:hover {
        background-color: #388e3c !important;
        color: white !important;
    }

    .block-container .markdown-text-container h3 {
        color: #2e7d32;
        font-size: 20px;
        font-weight: 600;
        margin-top: 1.2rem;
        margin-bottom: 0.8rem;
    }

    .stRadio > div {
        row-gap: 0.4rem;
    }

    label[data-baseweb="radio"] {
        background-color: transparent !important;
        border: none !important;
        padding: 0.2rem 0.5rem;
        color: #2e7d32 !important;
        font-weight: 500;
        transition: color 0.2s ease;
        font-size: 16px;
        border-radius: 0;
    }

    label[data-baseweb="radio"]:hover {
        color: #1b5e20 !important;
        background-color: transparent !important;
        text-decoration: underline;
        cursor: pointer;
    }

    input[type="radio"]:checked + div {
        font-weight: bold !important;
        color: #1b5e20 !important;
        text-decoration: underline;
    }

    </style>
    """, unsafe_allow_html=True)
