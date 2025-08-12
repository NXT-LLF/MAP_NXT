import streamlit as st
import requests
from geopy.distance import geodesic
import pandas as pd
import pydeck as pdk
import math
from unidecode import unidecode
import time

st.markdown("<h1 style='color:#ff002d;'>MAP MRKTG POLE PERF NXT</h1>", unsafe_allow_html=True)

# --- Fonction pour récupérer les infos d'une commune ---
def get_commune_info(ville_input):
    ville_input = unidecode(ville_input.lower().replace(" ", "-"))
    url = f"https://geo.api.gouv.fr/communes?nom={ville_input}&fields=nom,code,codePostal,codesPostaux,centre&format=json&geometry=centre"
    r = requests.get(url)
    data = r.json()
    if not data:
        return None
    commune = data[0]

    if "codePostal" in commune and commune["codePostal"]:
        cp = commune["codePostal"]
    elif "codesPostaux" in commune and commune["codesPostaux"]:
        cp = ", ".join(commune["codesPostaux"])
    else:
        cp = ""

    return {
        "nom": commune["nom"],
        "code_postal": cp,
        "latitude": commune["centre"]["coordinates"][1],
        "longitude": commune["centre"]["coordinates"][0]
    }

# --- Récupération de toutes les communes ---
@st.cache_data
def get_all_communes():
    url = "https://geo.api.gouv.fr/communes?fields=nom,code,codePostal,codesPostaux,centre&format=json&geometry=centre"
    r = requests.get(url)
    data = r.json()
    cleaned = []
    for c in data:
        try:
            lat = c["centre"]["coordinates"][1]
            lon = c["centre"]["coordinates"][0]
            if "codePostal" in c and c["codePostal"]:
                cp = c["codePostal"]
            elif "codesPostaux" in c and c["codesPostaux"]:
                cp = ", ".join(c["codesPostaux"])
            else:
                cp = ""
            cleaned.append({
                "nom": c["nom"],
                "code_postal": cp,
                "latitude": lat,
                "longitude": lon,
                "label": f'{c["nom"]}'
            })
        except:
            continue
    return pd.DataFrame(cleaned)

# --- Création d'un cercle ---
def create_circle_polygon(center, radius_m, points=100):
    lat, lon = center
    coords = []
    for i in range(points):
        angle = 2 * math.pi * i / points
        dx = radius_m * math.cos(angle)
        dy = radius_m * math.sin(angle)
        delta_lat = dy / 111320
        delta_lon = dx / (40075000 * math.cos(math.radians(lat)) / 360)
        coords.append([lon + delta_lon, lat + delta_lat])
    return coords

communes_df = get_all_communes()

# --- Recherche améliorée ---
search_input = st.text_input("Rechercher la ville de référence :", "Paris")
search_input_clean = unidecode(search_input.strip().lower())

matching_villes = communes_df[communes_df["nom"].apply(lambda x: unidecode(x.lower())).str.contains(search_input_clean)]
if matching_villes.empty:
    st.error("Aucune ville trouvée.")
    st.stop()

ville_input = st.selectbox("Résultats trouvés :", options=matching_villes["label"].tolist())

rayon = st.slider("Rayon de recherche (km) :", 1, 50, 10)

# --- Coordonnées de référence ---
ref_data = communes_df[communes_df["label"] == ville_input].iloc[0]
ref_coords = (ref_data["latitude"], ref_data["longitude"])

# --- Calcul distances avec barre de progression ---
df = communes_df.copy()
progress_bar = st.progress(0)
total = len(df)
distances = []

for i, row in enumerate(df.itertuples()):
    dist = geodesic(ref_coords, (row.latitude, row.longitude)).km
    distances.append(dist)
    if i % 10 == 0 or i == total - 1:
        progress_bar.progress((i + 1) / total)
        time.sleep(0.01)

df["distance_km"] = distances
communes_filtrees = df[df["distance_km"] <= rayon].sort_values("distance_km")

progress_bar.progress(1)
progress_bar.empty()

st.success(f"{len(communes_filtrees)} villes trouvées.")

# --- Carte ---
circle_polygon = create_circle_polygon(ref_coords, rayon * 1000)
circle_layer = pdk.Layer(
    "PolygonLayer",
    data=[{
        "polygon": circle_polygon,
        "fill_color": [173, 216, 230, 50],
        "line_color": [173, 216, 230, 150],
    }],
    get_polygon="polygon",
    get_fill_color="fill_color",
    get_line_color="line_color",
    pickable=False,
    stroked=True,
    filled=True,
    extruded=False,
)
scatter_layer = pdk.Layer(
    "ScatterplotLayer",
    data=communes_filtrees,
    get_position='[longitude, latitude]',
    get_radius=500,
    get_fill_color=[255, 0, 45, 180],
    pickable=True,
)
view_state = pdk.ViewState(
    latitude=ref_data["latitude"],
    longitude=ref_data["longitude"],
    zoom=9,
    pitch=0
)
st.pydeck_chart(pdk.Deck(
    layers=[circle_layer, scatter_layer],
    initial_view_state=view_state,
    map_style='light',
    tooltip={"text": "{nom}"}
))

# --- Sélection manuelle ---
selected_villes = st.multiselect(
    "Sélectionnez les villes à afficher",
    options=communes_filtrees["label"],
    default=communes_filtrees["label"].tolist()
)
final_villes = communes_filtrees[communes_filtrees["label"].isin(selected_villes)]

# --- Tableau avec CP ---
st.subheader("Résultats")
st.dataframe(final_villes[["nom", "code_postal", "distance_km"]].reset_index(drop=True))

# --- Codes postaux à copier ---
codes_postaux = final_villes["code_postal"].tolist()
resultat_texte = ", ".join(codes_postaux)
st.text_area("Zone de chalandise :", resultat_texte, height=100)
