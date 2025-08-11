import streamlit as st
import requests
from geopy.distance import geodesic
import pandas as pd
import pydeck as pdk
import unicodedata
import numpy as np

# --- MOT DE PASSE ---
import streamlit as st

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    password = st.secrets["app_password"]
    user_input = st.text_input("Entrez le mot de passe :", type="password")
    if user_input == password:
        st.session_state.authenticated = True
        st.success("Mot de passe validé ! Rafraîchis la page si besoin.")
    else:
        if user_input:
            st.warning("Mot de passe incorrect")
        st.stop()

# --- UTILITAIRES ---
def normalize_text(txt):
    # Enlève accents, met en minuscules, enlève tirets et espaces multiples
    txt = txt.lower()
    txt = ''.join(c for c in unicodedata.normalize('NFD', txt) if unicodedata.category(c) != 'Mn')
    txt = txt.replace('-', ' ').replace('_', ' ')
    txt = ' '.join(txt.split())
    return txt

# --- FONCTIONS ---
def get_commune_info(ville_input):
    url = f"https://geo.api.gouv.fr/communes?nom={ville_input}&fields=nom,code,codePostal,centre&format=json&geometry=centre"
    r = requests.get(url)
    data = r.json()
    if not data:
        return None
    commune = data[0]
    return {
        "nom": commune["nom"],
        "code_postal": commune.get("codePostal", ""),
        "latitude": commune["centre"]["coordinates"][1],
        "longitude": commune["centre"]["coordinates"][0]
    }

@st.cache_data
def get_all_communes():
    url = "https://geo.api.gouv.fr/communes?fields=nom,code,codePostal,centre&format=json&geometry=centre"
    r = requests.get(url)
    data = r.json()
    cleaned = []
    for c in data:
        try:
            lat = c["centre"]["coordinates"][1]
            lon = c["centre"]["coordinates"][0]
            label = f'{c["nom"]} ({c.get("codePostal", "")})'
            cleaned.append({
                "nom": c["nom"],
                "code_postal": c.get("codePostal", ""),
                "latitude": lat,
                "longitude": lon,
                "label": label,
                "label_normalized": normalize_text(label)
            })
        except:
            continue
    return pd.DataFrame(cleaned)

# --- DONNÉES ---
communes_df = get_all_communes()

# --- INPUTS ---
# Recherche intelligente dans les labels (nom + cp)
search_input = st.text_input("Rechercher la ville de référence :", "Aubervilliers")

# Recherche dans dataframe avec normalisation + filtre
normalized_search = normalize_text(search_input)
matches = communes_df[communes_df["label_normalized"].str.contains(normalized_search)]

if matches.empty:
    st.warning("Aucune ville trouvée avec cette recherche.")
    st.stop()

selected_index = matches.index[0]

# Affiche la sélection avec un selectbox
ville_label = st.selectbox("Sélectionnez la ville :", options=matches["label"].tolist(), index=0)
ville_nom = ville_label.split(" (")[0]

rayon = st.slider("Rayon de recherche (km) :", 1, 50, 10)

# --- CALCUL EN TEMPS RÉEL ---
ref = get_commune_info(ville_nom)
if not ref:
    st.warning("Ville de référence non trouvée via l'API.")
    st.stop()

ref_coords = (ref["latitude"], ref["longitude"])

# Calcul distance avec barre de progression
distances = []
progress_text = "Calcul des distances..."
progress_bar = st.progress(0)

for i, row in communes_df.iterrows():
    dist = geodesic(ref_coords, (row["latitude"], row["longitude"])).km
    distances.append(dist)
    if i % 50 == 0:
        progress_bar.progress(min(i / len(communes_df), 1.0))
progress_bar.progress(1.0)
communes_df["distance_km"] = distances

# Filtrer et trier
communes_filtrees = communes_df[(communes_df["distance_km"] <= rayon) & (communes_df["nom"] != ref["nom"])]
communes_filtrees = communes_filtrees.sort_values("distance_km").reset_index(drop=True)

st.success(f"{len(communes_filtrees)} villes trouvées dans un rayon de {rayon} km autour de {ville_nom}")

# --- Sélection des villes à afficher ---
selected_villes = st.multiselect(
    "Cochez les villes à afficher sur la carte :",
    options=communes_filtrees["label"].tolist(),
    default=communes_filtrees["label"].tolist()
)

display_df = communes_filtrees[communes_filtrees["label"].isin(selected_villes)]

# --- Tableau propre ---
st.dataframe(display_df[["nom", "code_postal", "distance_km"]].rename(columns={"nom": "Ville", "code_postal": "Code postal", "distance_km": "Distance (km)"}))

# --- Résultat code postaux copiable ---
cp_list = ", ".join(display_df["code_postal"].tolist())
if st.button("📋 Copier les codes postaux"):
    st.experimental_set_clipboard(cp_list)
st.text_area("Codes postaux (copier-coller) :", cp_list, height=100)

# --- Carte claire avec cercles plus petits ---
circle_layer = pdk.Layer(
    "ScatterplotLayer",
    data=display_df,
    get_position='[longitude, latitude]',
    get_radius=500,  # cercle plus petit
    get_fill_color='[255, 0, 45, 180]',  # rouge #ff002D avec un peu plus d'opacité
    pickable=True,
)

# Cercle rayon autour ville de référence
theta = np.linspace(0, 2 * np.pi, 100)
circle = pd.DataFrame({
    'lon': ref["longitude"] + (rayon / 111) * np.cos(theta),
    'lat': ref["latitude"] + (rayon / 111) * np.sin(theta),
})

polygon_layer = pdk.Layer(
    "PolygonLayer",
    data=[{
        "polygon": circle[['lon', 'lat']].values.tolist(),
        "fill_color": [255, 0, 0, 40],
        "stroke_color": [255, 0, 0, 100],
        "stroke_width": 2,
    }],
    pickable=False,
    stroked=True,
    filled=True,
    extruded=False,
)

view_state = pdk.ViewState(
    latitude=ref["latitude"],
    longitude=ref["longitude"],
    zoom=9,
    pitch=0
)

st.pydeck_chart(pdk.Deck(
    layers=[circle_layer, polygon_layer],
    initial_view_state=view_state,
    tooltip={"text": "{nom} ({code_postal})"}
))
