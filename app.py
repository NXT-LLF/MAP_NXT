import streamlit as st
import requests
from geopy.distance import geodesic
import pandas as pd
import pydeck as pdk
import math
from unidecode import unidecode
from fuzzywuzzy import process

st.set_page_config(layout="wide")

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
                "label": c["nom"]
            })
        except:
            continue
    return pd.DataFrame(cleaned)

def normalize_text(text):
    return unidecode(text.lower().replace("-", " ").strip())

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

# Normalisation pour la recherche
communes_df["label_norm"] = communes_df["label"].apply(normalize_text)
city_names_norm = communes_df["label_norm"].tolist()
city_names = communes_df["label"].tolist()

st.subheader("Recherche ville de référence")
input_city_raw = st.text_input("Entrez le nom de la ville :", "paris")
input_city_norm = normalize_text(input_city_raw)

# Recherche floue
choices = process.extract(input_city_norm, city_names_norm, limit=10)
best_matches = [city_names[city_names_norm.index(match[0])] for match in choices]
selected_city = st.selectbox("Sélectionnez la ville correcte :", best_matches)

ref_data = communes_df[communes_df["label"] == selected_city].iloc[0]
ref_coords = (ref_data["latitude"], ref_data["longitude"])

rayon = st.slider("Rayon de recherche (km) :", 1, 50, 10)

# Affichage pourcentage de progression
progress_text = st.empty()

df = communes_df.copy()
distances = []
total = len(df)

for i, row in df.iterrows():
    distances.append(geodesic(ref_coords, (row["latitude"], row["longitude"])).km)
    if i % 100 == 0:
        pct = int((i / total) * 100)
        progress_text.text(f"Calcul en cours : {pct}%")

df["distance_km"] = distances
progress_text.text("Calcul en cours : 100% ✅")

communes_filtrees = df[df["distance_km"] <= rayon].sort_values("distance_km")

# Carte
circle_polygon = create_circle_polygon(ref_coords, rayon * 1000)
circle_layer = pdk.Layer(
    "PolygonLayer",
    data=[{"polygon": circle_polygon, "fill_color": [173, 216, 230, 50], "line_color": [173, 216, 230, 150]}],
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
view_state = pdk.ViewState(latitude=ref_coords[0], longitude=ref_coords[1], zoom=9)
st.pydeck_chart(pdk.Deck(layers=[circle_layer, scatter_layer], initial_view_state=view_state, map_style='light'))

# Sélection
selected_villes = st.multiselect("Sélectionnez les villes", communes_filtrees["label"], default=communes_filtrees["label"].tolist())
final_villes = communes_filtrees[communes_filtrees["label"].isin(selected_villes)]

# Tableau
st.dataframe(final_villes[["nom", "code_postal", "distance_km"]].reset_index(drop=True))

# Texte prêt à copier
st.text_area("Zone de chalandise :", ", ".join(final_villes["code_postal"].tolist()), height=100)
