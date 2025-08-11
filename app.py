import streamlit as st
import requests
from geopy.distance import geodesic
import pandas as pd
import pydeck as pdk
import unidecode

# Authentification simple
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    password = st.secrets["app_password"]
    user_input = st.text_input("Entrez le mot de passe :", type="password")
    if user_input == password:
        st.session_state.authenticated = True
        st.success("Mot de passe validé ! Rafraîchissez la page si besoin.")
    else:
        if user_input:
            st.warning("Mot de passe incorrect")
        st.stop()

# Titre
st.markdown("<h1 style='color:#c82832;'>MAP MRKTG POLE PERF NXT</h1>", unsafe_allow_html=True)

# Fonction pour obtenir toutes les communes
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
                "label": f'{c["nom"]} ({c.get("codePostal", "")})'
            })
        except:
            continue
    return pd.DataFrame(cleaned)

communes_df = get_all_communes()

# Fonction pour normaliser les entrées (pour gestion accents, tirets, etc)
def normalize_city_name(name):
    name = name.lower().replace("-", " ").replace("'", " ")
    name = unidecode.unidecode(name)  # Enlève accents
    name = " ".join(name.split())     # Nettoie espaces multiples
    return name

# Barre de recherche combinée (entrée + selectbox avec autocomplétion améliorée)
input_raw = st.text_input("Recherchez et sélectionnez la ville de référence :", "Aubervilliers")

# Normalisation de la saisie utilisateur
input_norm = normalize_city_name(input_raw)

# Recherche la ville la plus proche dans la liste
match_idx = communes_df["nom"].apply(lambda x: normalize_city_name(x)).eq(input_norm)
if match_idx.any():
    default_index = match_idx.idxmax()
else:
    default_index = 0

ville_input = st.selectbox(
    "Sélectionnez la ville (auto-complétion) :",
    options=communes_df["label"].tolist(),
    index=default_index
)

# Extraction du nom et code postal sélectionnés
selected_nom = ville_input.split(" (")[0]
selected_cp = ville_input.split(" (")[1][:-1]

# Rayon de recherche
rayon = st.slider("Rayon de recherche (km) :", 1, 50, 10)

# Calcul distances + filtres
ref_coords = (communes_df.loc[communes_df["nom"] == selected_nom, "latitude"].values[0],
              communes_df.loc[communes_df["nom"] == selected_nom, "longitude"].values[0])

def calc_distance(row):
    return geodesic(ref_coords, (row["latitude"], row["longitude"])).km

df = communes_df.copy()
df["distance_km"] = df.apply(calc_distance, axis=1)

# Filtre communes dans le rayon et différentes de la ville de référence
communes_filtrees = df[(df["distance_km"] <= rayon) & (df["nom"] != selected_nom)].sort_values("distance_km")

# Barre de progression verte pendant le calcul (simulateur rapide ici)
progress = st.progress(0)
for i in range(100):
    progress.progress(i + 1)
progress.empty()

# Affichage carte au-dessus de la sélection des villes
st.subheader("Carte interactive")
# Cercle de rayon en bleu clair
circle_layer = pdk.Layer(
    "PolygonLayer",
    data=[{
        "polygon": pdk.utils.compute_circle((ref_coords[1], ref_coords[0]), rayon * 1000, 100),
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

# Points villes (petits cercles rouges)
points_layer = pdk.Layer(
    "ScatterplotLayer",
    data=communes_filtrees,
    get_position='[longitude, latitude]',
    get_radius=500,
    get_fill_color=[255, 0, 45, 200],  # rouge vif
    pickable=True,
)

view_state = pdk.ViewState(
    latitude=ref_coords[0],
    longitude=ref_coords[1],
    zoom=9,
    pitch=0
)

# Carte gris clair (style light)
map_style = "mapbox://styles/mapbox/light-v11"

st.pydeck_chart(pdk.Deck(
    layers=[circle_layer, points_layer],
    initial_view_state=view_state,
    map_style=map_style,
    tooltip={"text": "{nom} ({code_postal})"}
))

# Section checkbox pour afficher/cacher villes (plus lisible en bas de la carte)
st.subheader("Cochez les villes à afficher sur la carte")
checkboxes = {}
for i, row in communes_filtrees.iterrows():
    checkboxes[i] = st.checkbox(f"{row['nom']} ({row['code_postal']})", value=True)

# Tableau résultats sans index, avec nom + code postal visible
st.subheader(f"{len(communes_filtrees)} villes trouvées autour de {selected_nom}")

# Ne garder que les villes cochées
filtered = communes_filtrees[[checkboxes[i] for i in communes_filtrees.index]]

st.dataframe(filtered[["nom", "code_postal", "distance_km"]].reset_index(drop=True))

# Format texte pour copier-coller uniquement les codes postaux, séparés par ", "
codes_postaux = ", ".join(filtered["code_postal"].astype(str).tolist())
st.text_area("Codes postaux à copier :", codes_postaux, height=80)

