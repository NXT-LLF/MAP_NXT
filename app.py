import streamlit as st
import requests
from geopy.distance import geodesic
import pandas as pd
import pydeck as pdk
import unidecode

# Titre
st.markdown("<h1 style='color:#c82832;'>MAP MRKTG POLE PERF NXT</h1>", unsafe_allow_html=True)

# Fonction pour obtenir les coordonnées d’une ville
def get_commune_info(ville_input):
    url = f"https://geo.api.gouv.fr/communes?nom={ville_input}&fields=nom,code,codePostal,codesPostaux,centre&format=json&geometry=centre"
    r = requests.get(url)
    data = r.json()
    if not data:
        return None
    commune = data[0]
    cp = commune.get("codesPostaux", [""])[0] if "codesPostaux" in commune else commune.get("codePostal", "")
    return {
        "nom": commune["nom"],
        "code_postal": cp,
        "latitude": commune["centre"]["coordinates"][1],
        "longitude": commune["centre"]["coordinates"][0]
    }

# Fonction pour obtenir toutes les communes de France (coordonnées + code postal)
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
            cp = c.get("codesPostaux", [""])[0] if "codesPostaux" in c else c.get("codePostal", "")
            cleaned.append({
                "nom": c["nom"],
                "code_postal": cp,
                "latitude": lat,
                "longitude": lon
            })
        except:
            continue
    return pd.DataFrame(cleaned)

# Normalize function pour autocomplétion simplifiée (sans accent, tirets remplacés)
def normalize(text):
    return unidecode.unidecode(text.lower().replace("-", " ").strip())

# Charger les communes et préparer la liste d'autocomplétion
communes_df = get_all_communes()
communes_df["norm_nom"] = communes_df["nom"].apply(normalize)
communes_df["label"] = communes_df["nom"]  # juste le nom sans code postal ni ()

# Barre de recherche libre + autocomplétion simplifiée
ville_saisie = st.text_input("Rechercher la ville de référence :", "Aubervilliers")
norm_ville = normalize(ville_saisie)

# Filtrer pour autocomplétion sur base normalisée
options = communes_df[communes_df["norm_nom"].str.contains(norm_ville)]["label"].tolist()
if not options:
    options = communes_df["label"].tolist()

default_index = 0
# Essayer de positionner Aubervilliers ou 1ère ville trouvée
try:
    default_index = communes_df[communes_df["label"] == "Aubervilliers"].index[0]
except:
    default_index = 0

ville_input = st.selectbox("Sélectionnez la ville :", options, index=default_index)

# Rayon de recherche avec slider
rayon = st.slider("Rayon de recherche (km) :", 1, 50, 10)

# Trouver coords ville sélectionnée
ref = get_commune_info(ville_input)
if not ref:
    st.warning("Ville non trouvée via l'API. Vérifiez l'orthographe.")
    st.stop()

ref_coords = (ref["latitude"], ref["longitude"])

# Afficher carte en gris clair avec cercle bleu foncé correspondant au rayon (en temps réel)
st.subheader("Carte interactive - Rayon en temps réel")
circle_data = pd.DataFrame([{
    "latitude": ref["latitude"],
    "longitude": ref["longitude"],
    "rayon": rayon * 1000
}])

circle_layer = pdk.Layer(
    "ScatterplotLayer",
    data=circle_data,
    get_position='[longitude, latitude]',
    get_radius=100,
    get_fill_color=[255, 0, 45, 200],  # ville rouge vif
    pickable=True,
)

circle_radius_layer = pdk.Layer(
    "PolygonLayer",
    data=[pdk.data_utils.compute_circle([ref["longitude"], ref["latitude"]], rayon * 1000, 100)],
    get_polygon="coordinates",
    filled=True,
    opacity=0.15,
    get_fill_color=[0, 0, 255, 70],  # bleu clair semi transparent
    stroked=False,
)

view_state = pdk.ViewState(latitude=ref["latitude"], longitude=ref["longitude"], zoom=9, pitch=0)
st.pydeck_chart(pdk.Deck(layers=[circle_radius_layer, circle_layer], initial_view_state=view_state))

# Bouton pour lancer la recherche complète
if st.button("🚀 Lancer la recherche"):

    progress_bar = st.progress(0)
    df = communes_df.copy()

    # Calcul distances avec mise à jour progression
    distances = []
    total = len(df)
    for i, row in df.iterrows():
        dist = geodesic(ref_coords, (row["latitude"], row["longitude"])).km
        distances.append(dist)
        progress_bar.progress(int((i + 1) / total * 100))

    df["distance_km"] = distances

    # Filtrer par rayon et retirer ville de référence
    communes_filtrees = df[(df["distance_km"] <= rayon) & (df["nom"] != ref["nom"])]
    communes_filtrees = communes_filtrees.sort_values("distance_km")

    st.success(f"{len(communes_filtrees)} villes trouvées dans un rayon de {rayon} km autour de {ref['nom']} ({ref['code_postal']})")

    # Afficher tableau sans index, avec nom + code postal
    st.dataframe(communes_filtrees[["nom", "code_postal", "distance_km"]].reset_index(drop=True))

    # Afficher codes postaux concaténés prêts à copier
    cp_concat = ", ".join(communes_filtrees["code_postal"].astype(str).tolist())
    st.text_area("Codes postaux à copier :", cp_concat, height=100)

    # Carte avec les villes filtrées
    layer = pdk.Layer(
        "ScatterplotLayer",
        data=communes_filtrees,
        get_position='[longitude, latitude]',
        get_radius=500,
        get_fill_color='[255, 0, 45, 180]',  # rouge vif
        pickable=True,
    )
    view_state = pdk.ViewState(
        latitude=ref["latitude"],
        longitude=ref["longitude"],
        zoom=9,
        pitch=0
    )
    st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view_state))
