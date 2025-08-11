import streamlit as st
import requests
from geopy.distance import geodesic
import pandas as pd
import pydeck as pdk
import unidecode

st.set_page_config(layout="wide")

st.markdown("<h1 style='color:#c82832;'>MAP MRKTG POLE PERF NXT</h1>", unsafe_allow_html=True)

# Fonction pour normaliser le texte (sans accents, minuscules)
def normalize_text(text):
    return unidecode.unidecode(text).lower()

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
            nom = c["nom"]
            cp = c.get("codePostal", "")
            label = f"{nom} ({cp})" if cp else nom
            cleaned.append({
                "nom": nom,
                "code_postal": cp,
                "latitude": lat,
                "longitude": lon,
                "label": label,
                "norm_nom": normalize_text(nom)
            })
        except:
            continue
    return pd.DataFrame(cleaned)

communes_df = get_all_communes()

# Barre de recherche avec normalisation et autocomplétion
ville_search = st.text_input("Rechercher la ville de référence (sans accent, tiret facultatif) :", value="Paris")
norm_ville = normalize_text(ville_search).replace(" ", "-")

# Filtrer les options avec correspondance approximative
options = communes_df[communes_df["norm_nom"].str.contains(norm_ville)]["label"].tolist()
if not options:
    options = communes_df["label"].tolist()

try:
    default_index = options.index(next(opt for opt in options if "paris" in opt.lower()))
except StopIteration:
    default_index = 0

ville_input = st.selectbox("Sélectionnez la ville :", options, index=default_index)

# Extraire le nom sans code postal
ville_nom = ville_input.split(" (")[0]

ref = get_commune_info(ville_nom)

if not ref:
    st.warning("Ville non trouvée via l'API. Vérifiez l'orthographe.")
    st.stop()

ref_coords = (ref['latitude'], ref['longitude'])

rayon = st.slider("Rayon de recherche (km) :", 1, 50, 10)

# Bouton de recherche
if st.button("Lancer la recherche"):

    with st.spinner("Calcul en cours..."):
        df = communes_df.copy()

        def calc_distance(row):
            return geodesic(ref_coords, (row["latitude"], row["longitude"])).km

        df["distance_km"] = df.apply(calc_distance, axis=1)
        communes_filtrees = df[(df["distance_km"] <= rayon) & (df["nom"] != ref["nom"])]
        communes_filtrees = communes_filtrees.sort_values("distance_km")

    st.success(f"{len(communes_filtrees)} villes trouvées dans un rayon de {rayon} km autour de {ref['nom']} ({ref['code_postal']})")

    # Carte avec cercles plus petits, zone de rayon bleu clair, fond gris clair
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=communes_filtrees,
        get_position='[longitude, latitude]',
        get_radius=500,
        get_fill_color='[255, 0, 45, 160]',  # rouge vif
        pickable=True,
    )
    circle_layer = pdk.Layer(
        "PolygonLayer",
        data=[{
            "polygon": pdk.utils.compute_circle([ref_coords[1], ref_coords[0]], rayon * 1000, 50),
            "fill_color": [100, 149, 237, 50],  # bleu clair transparent
        }],
        get_polygon="polygon",
        get_fill_color="fill_color",
        stroked=False,
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
        layers=[circle_layer, layer],
        initial_view_state=view_state,
        map_style='mapbox://styles/mapbox/light-v9'
    ))

    # Section checkbox pour cocher/décocher villes affichées (liste courte)
    villes_a_afficher = st.multiselect(
        "Cochez les villes à afficher sur la carte :",
        options=communes_filtrees["label"].tolist(),
        default=communes_filtrees["label"].tolist()
    )

    # Filtrer le df selon choix utilisateur
    df_final = communes_filtrees[communes_filtrees["label"].isin(villes_a_afficher)]

    # Tableau résultat sans index, avec nom et code postal
    st.dataframe(df_final[["nom", "code_postal", "distance_km"]].reset_index(drop=True))

    # Bouton copier les codes postaux au format "XXXXX, XXXXX"
    codes_postaux_str = ", ".join(df_final["code_postal"].astype(str).tolist())
    st.text_area("Codes postaux sélectionnés (copier-coller) :", codes_postaux_str, height=100)

