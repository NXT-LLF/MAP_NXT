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

            # Gestion codePostal et codesPostaux
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

# Normalize city names for search
communes_df["label_norm"] = communes_df["label"].apply(normalize_text)
city_names_norm = communes_df["label_norm"].tolist()
city_names = communes_df["label"].tolist()

st.subheader("Recherche ville de référence (recherche floue, insensible à la casse, accents, tirets)")

input_city_raw = st.text_input("Entrez le nom de la ville : ", "paris")
input_city_norm = normalize_text(input_city_raw)

# Recherche floue avec fuzzywuzzy, on propose les 10 meilleures correspondances
choices = process.extract(input_city_norm, city_names_norm, limit=10, scorer=None)

# choices est une liste de tuples (match, score)
# On affiche seulement les noms exacts d'origine correspondants aux meilleurs scores
best_matches = [city_names[city_names_norm.index(match[0])] for match in choices]

selected_city = st.selectbox("Sélectionnez la ville correcte :", best_matches)

# Récupération des données de la ville sélectionnée
ref_data = communes_df[communes_df["label"] == selected_city].iloc[0]

ref_coords = (ref_data["latitude"], ref_data["longitude"])

rayon = st.slider("Rayon de recherche (km) :", 1, 50, 10)

progress_bar = st.progress(0)

df = communes_df.copy()

def calc_distance(row):
    return geodesic(ref_coords, (row["latitude"], row["longitude"])).km

# Calcul distance avec progression
distances = []
total = len(df)
for i, row in df.iterrows():
    distances.append(calc_distance(row))
    if i % 100 == 0:
        progress_bar.progress(min(i / total, 1.0))

df["distance_km"] = distances

communes_filtrees = df[df["distance_km"] <= rayon].sort_values("distance_km")

progress_bar.progress(1.0)
st.success(f"{len(communes_filtrees)} villes trouvées.")

# Carte
st.subheader("Carte interactive")
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

# Sélection villes à afficher
st.subheader("Cochez les villes à afficher sur la carte")
selected_villes = st.multiselect(
    "Sélectionnez les villes à afficher",
    options=communes_filtrees["label"],
    default=communes_filtrees["label"].tolist()
)

final_villes = communes_filtrees[communes_filtrees["label"].isin(selected_villes)]

# Tableau avec CP
st.subheader("Résultats")
st.dataframe(final_villes[["nom", "code_postal", "distance_km"]].reset_index(drop=True))

# Codes postaux à copier
codes_postaux = final_villes["code_postal"].tolist()
resultat_texte = ", ".join(codes_postaux)

st.text_area("Zone de chalandise :", resultat_texte, height=100)
