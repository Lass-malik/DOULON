"""
=============================================================
APP STREAMLIT — DÉTECTION DES DOUBLONS DE RÉCLAMATIONS
=============================================================
"""

import io
import re

import pandas as pd
import streamlit as st

# ── Configuration de la page ──────────────────────────────────
st.set_page_config(
    page_title="Détecteur de Doublons · Réclamations",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS personnalisé ──────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=Syne:wght@400;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Syne', sans-serif;
}

/* Fond général */
.stApp {
    background: #0d0f14;
    color: #e8e6e0;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: #13161d;
    border-right: 1px solid #1e2330;
}

/* Titre principal */
.hero-title {
    font-family: 'Syne', sans-serif;
    font-weight: 800;
    font-size: 2.6rem;
    line-height: 1.1;
    color: #f0ede6;
    letter-spacing: -0.02em;
    margin-bottom: 0.2rem;
}
.hero-sub {
    font-family: 'DM Mono', monospace;
    font-size: 0.78rem;
    color: #5a6070;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    margin-bottom: 2rem;
}

/* Métriques custom */
.metric-card {
    background: #13161d;
    border: 1px solid #1e2330;
    border-radius: 12px;
    padding: 1.2rem 1.4rem;
    text-align: center;
    transition: border-color 0.2s;
}
.metric-card:hover { border-color: #f97316; }
.metric-value {
    font-family: 'Syne', sans-serif;
    font-size: 2.2rem;
    font-weight: 800;
    color: #f97316;
    line-height: 1;
}
.metric-label {
    font-family: 'DM Mono', monospace;
    font-size: 0.7rem;
    color: #5a6070;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-top: 0.4rem;
}

/* Badge de statut */
.badge-ok  { color: #4ade80; font-weight: 600; }
.badge-warn{ color: #f97316; font-weight: 600; }

/* Tableau */
.dataframe { font-family: 'DM Mono', monospace !important; font-size: 0.78rem !important; }

/* Bouton download */
.stDownloadButton > button {
    background: #f97316 !important;
    color: #0d0f14 !important;
    font-family: 'Syne', sans-serif !important;
    font-weight: 700 !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 0.6rem 1.4rem !important;
    transition: opacity 0.2s !important;
}
.stDownloadButton > button:hover { opacity: 0.85 !important; }

/* File uploader */
[data-testid="stFileUploader"] {
    border: 2px dashed #1e2330 !important;
    border-radius: 12px !important;
    background: #13161d !important;
    padding: 1rem !important;
}

/* Séparateur */
hr { border-color: #1e2330 !important; }

/* Selectbox / radio */
.stSelectbox > div > div, .stRadio > div {
    background: #13161d !important;
}

/* Spinner */
.stSpinner > div { border-top-color: #f97316 !important; }

/* Alerte */
.stAlert { border-radius: 10px !important; }

/* Progress bar */
.stProgress > div > div { background: #f97316 !important; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# FONCTIONS MÉTIER
# ══════════════════════════════════════════════════════════════

PATTERN_ID_TRANSACTION = r"(?<!\d)([1-9]\d{9,10})(?!\d)"

def extraire_id_transaction(commentaire: str) -> str | None:
    """
    Extrait le premier ID de transaction valide (10-11 chiffres, ≠ 0 en tête)
    depuis un commentaire de soumission.
    """
    if pd.isna(commentaire) or str(commentaire).strip() in ("", "nan"):
        return None
    match = re.search(PATTERN_ID_TRANSACTION, str(commentaire))
    return match.group(1) if match else None


def detecter_doublons(df_raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Pipeline complet de détection des doublons de réclamations.

    Returns
    -------
    df_final : DataFrame résultat
    stats    : dictionnaire de métriques
    """
    stats = {}

    # 1. Nettoyage
    df_raw = df_raw.dropna(how="all")
    COLONNES_UTILES = [
        "N°REC", "NUMERO ABONNE", "COMMENTAIRES DE SOUMISSION",
        "SOUS CATEGORIE 1", "TYPE DE REQUETE", "TRAITEE PAR", "STATUT",
    ]
    # Vérification colonnes
    manquantes = [c for c in COLONNES_UTILES if c not in df_raw.columns]
    if manquantes:
        raise ValueError(f"Colonnes manquantes dans le fichier : {manquantes}")

    df = df_raw[COLONNES_UTILES].copy()
    df = df.dropna(subset=["N°REC"])
    df["COMMENTAIRES DE SOUMISSION"] = df["COMMENTAIRES DE SOUMISSION"].astype(str).str.strip()
    df["NUMERO ABONNE"] = df["NUMERO ABONNE"].astype(str).str.strip()
    # Nettoyage TRAITEE PAR : valeur vide → "Inconnu"
    df["TRAITEE PAR"] = df["TRAITEE PAR"].fillna("Inconnu").astype(str).str.strip()
    df["STATUT"] = df["STATUT"].fillna("Inconnu").astype(str).str.strip()
    stats["total_reclamations"] = len(df)

    # 2. Extraction ID
    df["ID_TRANSACTION"] = df["COMMENTAIRES DE SOUMISSION"].apply(extraire_id_transaction)
    stats["avec_id"] = int(df["ID_TRANSACTION"].notna().sum())
    stats["sans_id"] = stats["total_reclamations"] - stats["avec_id"]
    stats["taux_extraction"] = stats["avec_id"] / stats["total_reclamations"] if stats["total_reclamations"] else 0

    # 3. Filtrage
    df_avec_id = df.dropna(subset=["ID_TRANSACTION"]).copy()

    # 4. Groupby — on collecte les paires (N°REC, TRAITEE PAR) pour chaque groupe
    def agreger_groupe(g: pd.DataFrame) -> pd.Series:
        nb = len(g)
        liste = " | ".join(
            f"{rec} ({statut}) ({agent})"
            for rec, statut, agent in zip(g["N°REC"], g["STATUT"], g["TRAITEE PAR"])
        )
        return pd.Series({"NOMBRE_RECLAMATIONS": nb, "LISTE_RECLAMATIONS": liste})

    df_grouped = (
        df_avec_id
        .groupby(
            ["NUMERO ABONNE", "ID_TRANSACTION", "SOUS CATEGORIE 1", "TYPE DE REQUETE"],
            as_index=False,
        )
        .apply(agreger_groupe, include_groups=False)
        .reset_index(drop=True)
    )
    stats["nb_groupes"] = len(df_grouped)

    # 5. Doublons uniquement
    df_doublons = df_grouped[df_grouped["NOMBRE_RECLAMATIONS"] > 1].copy()
    stats["nb_doublons"] = len(df_doublons)
    stats["nb_rec_concernees"] = int(df_doublons["NOMBRE_RECLAMATIONS"].sum())

    # 6. Nettoyage final
    df_final = df_doublons.drop_duplicates(subset=["ID_TRANSACTION"]).reset_index(drop=True)
    df_final = df_final[[
        "NUMERO ABONNE", "ID_TRANSACTION", "NOMBRE_RECLAMATIONS",
        "SOUS CATEGORIE 1", "TYPE DE REQUETE", "LISTE_RECLAMATIONS",
    ]]

    return df_final, stats


def convertir_liste(df: pd.DataFrame) -> pd.DataFrame:
    """LISTE_RECLAMATIONS est déjà une chaîne — pas de transformation nécessaire."""
    return df.copy()


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Doublons")
    return buf.getvalue()


def to_csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8-sig")


def to_tsv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False, sep="\t", encoding="utf-8-sig").encode("utf-8-sig")


# ══════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("""
    <div style='margin-bottom:1.5rem'>
        <div style='font-family:Syne,sans-serif;font-weight:800;font-size:1.1rem;color:#f0ede6'>
            🔍 Doublons Réclamations
        </div>
        <div style='font-family:DM Mono,monospace;font-size:0.65rem;color:#5a6070;
                    text-transform:uppercase;letter-spacing:0.1em;margin-top:2px'>
            Outil d'analyse v2.2
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("##### 📁 Import du fichier")
    uploaded_file = st.file_uploader(
        label="Glisser-déposer ou cliquer",
        type=["xlsx", "xls", "csv"],
        label_visibility="collapsed",
    )

    st.markdown("---")
    st.markdown("##### ⚙️ Options d'export")
    format_export = st.radio(
        "Format de téléchargement",
        options=["Excel (.xlsx)", "CSV (.csv)", "TSV (.tsv)"],
        index=0,
    )

    st.markdown("---")
    st.markdown("##### 📋 Colonnes requises")
    for col in ["N°REC", "NUMERO ABONNE", "COMMENTAIRES DE SOUMISSION",
                "SOUS CATEGORIE 1", "TYPE DE REQUETE", "TRAITEE PAR", "STATUT"]:
        st.markdown(
            f"<div style='font-family:DM Mono,monospace;font-size:0.7rem;"
            f"color:#5a6070;margin:2px 0'>• {col}</div>",
            unsafe_allow_html=True
        )

    st.markdown("---")
    st.markdown(
        "<div style='font-family:DM Mono,monospace;font-size:0.62rem;color:#3a4050'>"
        "Regex pattern : séquence 10–11 chiffres<br>ne commençant pas par 0"
        "</div>",
        unsafe_allow_html=True
    )


# ══════════════════════════════════════════════════════════════
# CORPS PRINCIPAL
# ══════════════════════════════════════════════════════════════

st.markdown('<div class="hero-title">Détecteur de Doublons</div>', unsafe_allow_html=True)
st.markdown('<div class="hero-sub">Identification des réclamations liées à une même transaction</div>', unsafe_allow_html=True)

# ── État vide ─────────────────────────────────────────────────
if uploaded_file is None:
    st.markdown("""
    <div style="
        background:#13161d;border:1px solid #1e2330;border-radius:16px;
        padding:3rem 2rem;text-align:center;margin-top:1rem
    ">
        <div style="font-size:3rem;margin-bottom:1rem">📂</div>
        <div style="font-family:Syne,sans-serif;font-size:1.2rem;font-weight:600;
                    color:#f0ede6;margin-bottom:0.5rem">
            Importez votre fichier de réclamations
        </div>
        <div style="font-family:DM Mono,monospace;font-size:0.75rem;color:#5a6070">
            Formats acceptés : .xlsx · .xls · .csv — utilisez la sidebar à gauche
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()


# ── Chargement du fichier ─────────────────────────────────────
@st.cache_data(show_spinner=False)
def charger_fichier(file_bytes: bytes, file_name: str) -> pd.DataFrame:
    if file_name.endswith(".csv"):
        try:
            return pd.read_csv(io.BytesIO(file_bytes), sep=";", encoding="utf-8-sig")
        except Exception:
            return pd.read_csv(io.BytesIO(file_bytes), sep=",")
    else:
        return pd.read_excel(io.BytesIO(file_bytes))


with st.spinner("Chargement du fichier…"):
    try:
        df_raw = charger_fichier(uploaded_file.read(), uploaded_file.name)
    except Exception as e:
        st.error(f"❌ Impossible de lire le fichier : {e}")
        st.stop()

st.success(f"✅ Fichier chargé : **{uploaded_file.name}** — {len(df_raw):,} lignes brutes")

# ── Analyse ───────────────────────────────────────────────────
with st.spinner("Analyse en cours…"):
    try:
        df_final, stats = detecter_doublons(df_raw)
    except ValueError as e:
        st.error(f"❌ {e}")
        st.stop()

# ── Métriques ─────────────────────────────────────────────────
st.markdown("<div style='margin-top:1.5rem'></div>", unsafe_allow_html=True)
c1, c2, c3, c4, c5 = st.columns(5)

metrics = [
    (c1, stats["total_reclamations"], "Réclamations totales"),
    (c2, f"{stats['taux_extraction']:.1%}", "Taux d'extraction ID"),
    (c3, stats["nb_groupes"], "Groupes uniques"),
    (c4, stats["nb_doublons"], "Transactions en doublon"),
    (c5, stats["nb_rec_concernees"], "Réclamations concernées"),
]
for col, val, label in metrics:
    with col:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{val}</div>
            <div class="metric-label">{label}</div>
        </div>
        """, unsafe_allow_html=True)

st.markdown("<div style='margin-top:1.5rem'></div>", unsafe_allow_html=True)

# ── Tabs résultats ────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["📊 Résultats", "🔎 Aperçu brut", "📥 Export"])

# ── TAB 1 : Résultats ─────────────────────────────────────────
with tab1:
    if df_final.empty:
        st.info("ℹ️ Aucun doublon détecté dans ce fichier.")
    else:
        st.markdown(
            f"<div style='font-family:DM Mono,monospace;font-size:0.78rem;color:#5a6070;"
            f"margin-bottom:0.8rem'>"
            f"<span class='badge-warn'>▶ {len(df_final)} transactions</span> "
            f"avec réclamations multiples détectées</div>",
            unsafe_allow_html=True
        )

        # Filtres inline
        col_f1, col_f2, col_f3 = st.columns([2, 2, 1])
        with col_f1:
            sous_cats = ["Toutes"] + sorted(df_final["SOUS CATEGORIE 1"].dropna().unique().tolist())
            filtre_cat = st.selectbox("Filtrer par Sous Catégorie", sous_cats)
        with col_f2:
            types = ["Tous"] + sorted(df_final["TYPE DE REQUETE"].dropna().unique().tolist())
            filtre_type = st.selectbox("Filtrer par Type de Requête", types)
        with col_f3:
            filtre_min = st.number_input("Nb min de réclamations", min_value=2, value=2, step=1)

        # Application des filtres
        df_view = df_final.copy()
        if filtre_cat != "Toutes":
            df_view = df_view[df_view["SOUS CATEGORIE 1"] == filtre_cat]
        if filtre_type != "Tous":
            df_view = df_view[df_view["TYPE DE REQUETE"] == filtre_type]
        df_view = df_view[df_view["NOMBRE_RECLAMATIONS"] >= filtre_min]

        st.markdown(
            f"<div style='font-family:DM Mono,monospace;font-size:0.7rem;color:#5a6070;"
            f"margin-bottom:0.5rem'>{len(df_view)} résultat(s) après filtres</div>",
            unsafe_allow_html=True
        )

        # Affichage
        df_display = df_view.copy()
        st.dataframe(
            df_display,
            use_container_width=True,
            height=480,
            column_config={
                "NOMBRE_RECLAMATIONS": st.column_config.NumberColumn("Nb Réclamations", format="%d"),
                "ID_TRANSACTION": st.column_config.TextColumn("ID Transaction"),
                "LISTE_RECLAMATIONS": st.column_config.TextColumn("Liste N°REC", width="large"),
            }
        )

        # Distribution
        st.markdown("---")
        st.markdown("##### Distribution du nombre de réclamations par doublon")
        dist = df_view["NOMBRE_RECLAMATIONS"].value_counts().sort_index().reset_index()
        dist.columns = ["Nb réclamations", "Nb transactions"]
        st.bar_chart(dist.set_index("Nb réclamations"), color="#f97316")


# ── TAB 2 : Aperçu brut ───────────────────────────────────────
with tab2:
    st.markdown(
        f"<div style='font-family:DM Mono,monospace;font-size:0.75rem;color:#5a6070;"
        f"margin-bottom:0.8rem'>Aperçu des 100 premières lignes du fichier importé</div>",
        unsafe_allow_html=True
    )
    st.dataframe(df_raw.head(100), use_container_width=True, height=400)


# ── TAB 3 : Export ────────────────────────────────────────────
with tab3:
    if df_final.empty:
        st.info("ℹ️ Aucun résultat à exporter.")
    else:
        df_export = convertir_liste(df_final)

        st.markdown("##### Télécharger les résultats")
        st.markdown(
            f"<div style='font-family:DM Mono,monospace;font-size:0.75rem;color:#5a6070;"
            f"margin-bottom:1.2rem'>"
            f"Format sélectionné dans la sidebar : <strong style='color:#f97316'>"
            f"{format_export}</strong></div>",
            unsafe_allow_html=True
        )

        if format_export == "Excel (.xlsx)":
            data_bytes = to_excel_bytes(df_export)
            fname = "doublons_reclamations.xlsx"
            mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        elif format_export == "CSV (.csv)":
            data_bytes = to_csv_bytes(df_export)
            fname = "doublons_reclamations.csv"
            mime = "text/csv"
        else:
            data_bytes = to_tsv_bytes(df_export)
            fname = "doublons_reclamations.tsv"
            mime = "text/tab-separated-values"

        st.download_button(
            label=f"⬇️  Télécharger — {fname}",
            data=data_bytes,
            file_name=fname,
            mime=mime,
            use_container_width=True,
        )

        st.markdown("---")
        st.markdown("##### Aperçu de l'export")
        st.dataframe(df_export.head(20), use_container_width=True, height=320)
