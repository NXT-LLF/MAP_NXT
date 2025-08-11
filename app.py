import streamlit as st
import requests
from geopy.distance import geodesic
import pandas as pd
import pydeck as pdk
import math
from unidecode import unidecode

st.markdown("<h1 style='color:#c82832;'>MAP MRKTG POLE PERF NXT</h1>", unsafe_allow_html=True)

# Fonction pour normaliser les noms pour autocomplétion (supprime accents et tirets)
def normalize_name(name):
    name = name.lower().replace("-", " ")
    name = unidecode(name)
    return name

# Fonction pour obtenir les coordonnées d’une ville
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

# Fonction pour obtenir toutes les communes de France (coordonnées + code postal)
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
                "label": f"{c['nom']} - {c.get('codePostal', '')}"
            })
        except:
            continue
    return pd.DataFrame(cleaned)

def compute_circle(lon, lat, radius_m, nb_points=50):
    coords = []
    R = 6371000  # rayon Terre en mètres
    for i in range(nb_points):
        angle = 2 * math.pi * i / nb_points
        dx = radius_m * math.cos(angle)
        dy = radius_m * math.sin(angle)
        dlat = dy / R
        dlon = dx / (R * math.cos(math.pi * lat / 180))
        lat_i = lat + dlat * 180 / math.pi
        lon_i = lon + dlon * 180 / math.pi
        coords.append([lon_i, lat_i])
    return coords

communes_df = get_all_communes()

# Recherche et sélection regroupées
search_input = st.text_input("Rechercher la ville de référence :", "Paris")

# Normalisation pour trouver la correspondance même sans tirets/accents
normalized_search = normalize_name(search_input)
matches = communes_df[communes_df["nom"].apply(lambda x: normalize_name(x)).str.contains(normalized_search)]
if not matches.empty:
    options = matches["label"].tolist()
    default_index = 0
else:
    options = communes_df["label"].tolist()
    default_index = communes_df[communes_df["nom"].str.lower() == "paris"].index[0]

ville_input = st.selectbox("Sélectionnez la ville :", options, index=default_index)

# Extrait nom et code postal de la sélection
selected_nom = ville_input.split(" - ")[0]
selected_cp = ville_input.split(" - ")[1]

rayon = st.slider("Rayon de recherche (km) :", 1, 50, 10)

if st.button("Lancer la recherche"):

    with st.spinner("Calcul en cours..."):
        ref = get_commune_info(selected_nom)

        if not ref:
            st.warning("Ville non trouvée via l'API. Vérifiez l'orthographe.")
            st.stop()

        ref_coords = (ref['latitude'], ref['longitude'])

        # Calcul des distances
        def calc_distance(row):
            return geodesic(ref_coords, (row["latitude"], row["longitude"])).km

        communes_df["distance_km"] = communes_df.apply(calc_distance, axis=1)

        communes_filtrees = communes_df[(communes_df["distance_km"] <= rayon) & (communes_df["nom"] != ref["nom"])]
        communes_filtrees = communes_filtrees.sort_values("distance_km")

        st.success(f"{len(communes_filtrees)} villes trouvées dans un rayon de {rayon} km autour de {ref['nom']} ({ref['code_postal']})")

        # Affichage du tableau sans index, sans colonne inutile, avec code postal visible
        st.dataframe(communes_filtrees[["nom", "code_postal", "distance_km"]].rename(columns={"nom": "Ville", "code_postal": "Code Postal", "distance_km": "Distance (km)"}), use_container_width=True)

        # Préparation du texte à copier : uniquement codes postaux séparés par virgule et espace
        codes_postaux_str = ", ".join(communes_filtrees["code_postal"].tolist())
        st.text_area("Codes postaux (copier/coller) :", value=codes_postaux_str, height=100)

        # Carte
        st.subheader("Carte interactive")
        circle_layer = pdk.Layer(
            "PolygonLayer",
            data=[{
                "polygon": compute_circle(ref_coords[1], ref_coords[0], rayon * 1000, 50),
                "fill_color": [100, 149, 237, 50],  # bleu clair transparent
            }],
            get_polygon="polygon",
            get_fill_color="fill_color",
            stroked=False,
            filled=True,
            extruded=False,
        )
        points_layer = pdk.Layer(
            "ScatterplotLayer",
            data=communes_filtrees,
            get_position='[longitude, latitude]',
            get_radius=500,
            get_fill_color=[255, 0, 45, 160],  # rouge vif
            pickable=True,
        )
        view_state = pdk.ViewState(
            latitude=ref["latitude"],
            longitude=ref["longitude"],
            zoom=9,
            pitch=0
        )
        st.pydeck_chart(pdk.Deck(
            layers=[circle_layer, points_layer],
            initial_view_state=view_state,
            map_style='light',
            tooltip={"text": "{nom} ({code_postal})"}
        ))
