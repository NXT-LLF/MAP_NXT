import streamlit as st
import requests
from geopy.distance import geodesic
import pandas as pd
import pydeck as pdk
import math
from unidecode import unidecode
from fuzzywuzzy import process

st.markdown("<h1 style='color:#ff002d;'>MAP MRKTG POLE PERF NXT</h1>", unsafe_allow_html=True)

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

def compute_distances(df, ref_coords):
    total = len(df)
    distances = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    for i, row in df.iterrows():
        distances.append(geodesic(ref_coords, (row["latitude"], row["longitude"])).km)
        progress_bar.progress((i + 1) / total)
        status_text.text(f"Calcul en cours... {(i + 1) * 100 // total}%")
    progress_bar.empty()
    status_text.empty()
    return distances

# Chargement des communes
communes_df = get_all_communes()

search_input = st.text_input("Tapez le nom de la ville de référence :", value="Paris")

if search_input:
    matches = process.extract(search_input, communes_df["nom"], limit=5)
    best_match = matches[0][0] if matches else search_input
else:
    best_match = "Paris"

try:
    default_index = int(communes_df[communes_df["nom"].str.lower() == best_match.lower()].index[0])
except:
    default_index = 0

ville_input = st.selectbox(
    "Ou sélectionnez dans la liste :",
    options=communes_df["label"].tolist(),
    index=default_index
)

rayon = st.slider("Rayon de recherche (km) :", 1, 50, 10)

ref_data = communes_df[communes_df["label"] == ville_input].iloc[0]
ref_coords = (ref_data["latitude"], ref_data["longitude"])

df = communes_df.copy()

# Calcul des distances avec la barre de progression
distances = compute_distances(df, ref_coords)
df["distance_km"] = distances
communes_filtrees = df[df["distance_km"] <= rayon].sort_values("distance_km")

st.success(f"{len(communes_filtrees)} villes trouvées.")

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
    latitude=ref_coords[0],
    longitude=ref_coords[1],
    zoom=9,
    pitch=0
)

st.pydeck_chart(pdk.Deck(
    layers=[circle_layer, scatter_layer],
    initial_view_state=view_state,
    map_style='light',
    tooltip={"text": "{nom}"}
))

selected_villes = st.multiselect(
    "Sélectionnez les villes à afficher",
    options=communes_filtrees["label"],
    default=communes_filtrees["label"].tolist()
)

final_villes = communes_filtrees[communes_filtrees["label"].isin(selected_villes)]

st.subheader("Résultats")
st.dataframe(final_villes[["nom", "code_postal", "distance_km"]].reset_index(drop=True))

codes_postaux = final_villes["code_postal"].tolist()
resultat_texte = ", ".join(codes_postaux)
st.text_area("Zone de chalandise :", resultat_texte, height=100)
