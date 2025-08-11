import streamlit as st
import requests
from geopy.distance import geodesic
import pandas as pd
import pydeck as pdk

# Mot de passe simple (exemple)
password = st.secrets["app_password"]
user_input = st.text_input("Entrez le mot de passe :", type="password")
if user_input != password:
    st.warning("Mot de passe incorrect")
    st.stop()

# Titre
st.markdown("<h1 style='color:#c82832;'>MAP MRKTG POLE PERF NXT</h1>", unsafe_allow_html=True)

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

# Fonction pour obtenir toutes les communes de France (coordonnées)
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
                "label": f'{c["nom"]} ({c.get("codePostal", "")})'  # pour l'autocomplétion
            })
        except:
            continue
    return pd.DataFrame(cleaned)

# Récupération du dataframe
communes_df = get_all_communes()

# Trouver l’index pour Aubervilliers, ou 0 si pas trouvé
filtered = communes_df[communes_df["nom"].str.lower() == "aubervilliers"]
if not filtered.empty:
    default_index = int(filtered.index[0])
else:
    default_index = 0

# Selectbox avec autocomplétion
ville_input = st.selectbox(
    "Entrez la ville (autocomplétion) :",
    options=communes_df["label"].tolist(),
    index=default_index
)

# Extraire nom de la ville depuis la sélection (avant parenthèse)
ville_nom = ville_input.split(" (")[0]

rayon = st.slider("Rayon de recherche (km) :", 1, 50, 10)

# Bouton pour lancer la recherche
if st.button("Lancer la recherche"):

    ref = get_commune_info(ville_nom)

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

    st.write(f"{len(communes_filtrees)} villes trouvées")

    # Affichage tableau sans colonne index
    st.dataframe(communes_filtrees[["nom", "code_postal", "distance_km"]])

    # Copier-coller du résultat textuel
    result_text = ", ".join(communes_filtrees["nom"] + " " + communes_filtrees["code_postal"])
    st.text_area("Résultat (copier-coller) :", result_text, height=150)

    # Carte claire avec villes en rouge
    st.subheader("Carte interactive")
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=communes_filtrees,
        get_position='[longitude, latitude]',
        get_radius=2000,
        get_fill_color='[255, 0, 45, 160]',  # rouge #ff002D
        pickable=True,
    )
    view_state = pdk.ViewState(
        latitude=ref["latitude"],
        longitude=ref["longitude"],
        zoom=9,
        pitch=0
    )
    st.pydeck_chart(pdk.Deck(
        layers=[layer],
        initial_view_state=view_state,
        tooltip={"text": "{nom} ({code_postal})"}
    ))
