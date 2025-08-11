import streamlit as st
import requests
from geopy.distance import geodesic
import pandas as pd
import pydeck as pdk
import math
from unidecode import unidecode

st.markdown("<h1 style='color:#c82832;'>MAP MRKTG POLE PERF NXT</h1>", unsafe_allow_html=True)

def get_commune_info(ville_input):
    ville_input = unidecode(ville_input.lower().replace(" ", "-"))
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
            cleaned.append({
                "nom": c["nom"],
                "code_postal": c.get("codePostal", ""),
                "latitude": lat,
                "longitude": lon,
                "label": f'{c["nom"]} ({c.get("codePostal","")})'
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

communes_df = get_all_communes()

# Barre de recherche avec autocomplétion améliorée (on va garder selectbox simple)
ville_input = st.selectbox(
    "Rechercher la ville de référence :",
    options=communes_df["label"].tolist(),
    index=communes_df[communes_df["nom"].str.lower() == "aubervilliers"].index[0]
)

rayon = st.slider("Rayon de recherche (km) :", 1, 50, 10)

# Extraire nom et code postal depuis la sélection
ref_nom = ville_input.split(" (")[0]
ref_code_postal = ville_input.split(" (")[1][:-1]

ref = {
    "nom": ref_nom,
    "code_postal": ref_code_postal,
    "latitude": communes_df.loc[communes_df["label"] == ville_input, "latitude"].values[0],
    "longitude": communes_df.loc[communes_df["label"] == ville_input, "longitude"].values[0]
}

ref_coords = (ref['latitude'], ref['longitude'])

with st.spinner('Calcul en cours...'):
    df = communes_df.copy()

    def calc_distance(row):
        return geodesic(ref_coords, (row["latitude"], row["longitude"])).km

    df["distance_km"] = df.apply(calc_distance, axis=1)
    communes_filtrees = df[(df["distance_km"] <= rayon)]
    communes_filtrees = communes_filtrees.sort_values("distance_km")

st.success(f"{len(communes_filtrees)} villes trouvées.")

# Carte au dessus de la sélection des villes à afficher
st.subheader("Carte interactive")
circle_polygon = create_circle_polygon(ref_coords, rayon * 1000)
circle_layer = pdk.Layer(
    "PolygonLayer",
    data=[{
        "polygon": circle_polygon,
        "fill_color": [173, 216, 230, 50],  # bleu clair translucide
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

# Cercle plus petit et rouge vif pour les villes
scatter_layer = pdk.Layer(
    "ScatterplotLayer",
    data=communes_filtrees,
    get_position='[longitude, latitude]',
    get_radius=500,
    get_fill_color=[255, 0, 45, 180],  # rouge vif
    pickable=True,
)

view_state = pdk.ViewState(
    latitude=ref["latitude"],
    longitude=ref["longitude"],
    zoom=9,
    pitch=0
)

st.pydeck_chart(pdk.Deck(
    layers=[circle_layer, scatter_layer],
    initial_view_state=view_state,
    map_style='light',
    tooltip={"text": "{nom} ({code_postal})"}
))

st.subheader("Cochez les villes à afficher sur la carte")
selected_villes = st.multiselect(
    "Sélectionnez les villes à afficher",
    options=communes_filtrees["label"],
    default=communes_filtrees["label"].tolist()
)

# Filtrer les villes selon sélection
final_villes = communes_filtrees[communes_filtrees["label"].isin(selected_villes)]

st.subheader("Résultats")
# Affichage tableau sans index avec colonne code_postal visible
st.dataframe(final_villes[["nom", "code_postal", "distance_km"]].reset_index(drop=True))

# Préparer texte au format code_postal séparés par virgule pour copier
codes_postaux = final_villes["code_postal"].tolist()
resultat_texte = ", ".join(codes_postaux)

st.text_area("Codes postaux des villes sélectionnées (copiez-collez) :", resultat_texte, height=100)
