import streamlit as st
import requests
from geopy.distance import geodesic
import pandas as pd
import pydeck as pdk
import math
from unidecode import unidecode

st.markdown("<h1 style='color:#ff002d;'>MAP MRKTG POLE PERF NXT</h1>", unsafe_allow_html=True)

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

# Sélection ville de référence
ville_input = st.selectbox(
    "Rechercher la ville de référence :",
    options=communes_df["label"].tolist(),
    index=int(communes_df[communes_df["nom"].str.lower() == "paris"].index[0])
)

rayon = st.slider("Rayon de recherche (km) :", 1, 50, 10)

ref_data = communes_df[communes_df["label"] == ville_input].iloc[0]
ref_coords = (ref_data["latitude"], ref_data["longitude"])

with st.spinner('Calcul en cours...'):
    df = communes_df.copy()

    def calc_distance(row):
        return geodesic(ref_coords, (row["latitude"], row["longitude"])).km

    df["distance_km"] = df.apply(calc_distance, axis=1)
    communes_filtrees = df[df["distance_km"] <= rayon].sort_values("distance_km")

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

# Gestion multiselect avec ajout dynamique

if "selected_villes" not in st.session_state:
    st.session_state.selected_villes = communes_filtrees["label"].tolist()

st.subheader("Cochez les villes à afficher sur la carte")
selected_villes = st.multiselect(
    "Sélectionnez les villes à afficher",
    options=communes_filtrees["label"],
    default=st.session_state.selected_villes,
    key="multi"
)

nouvelle_ville = st.text_input("Ajouter une ville (exactement comme dans la liste)")

if st.button("Ajouter la ville"):
    if nouvelle_ville in communes_filtrees["label"].values:
        if nouvelle_ville not in st.session_state.selected_villes:
            st.session_state.selected_villes.append(nouvelle_ville)
            st.success(f"Ville '{nouvelle_ville}' ajoutée.")
        else:
            st.warning(f"La ville '{nouvelle_ville}' est déjà sélectionnée.")
    else:
        st.error(f"La ville '{nouvelle_ville}' n'existe pas dans la liste.")

# Synchroniser la sélection du multiselect avec l'état
if selected_villes != st.session_state.selected_villes:
    st.session_state.selected_villes = selected_villes

# Filtrer les villes finales à afficher
final_villes = communes_filtrees[communes_filtrees["label"].isin(st.session_state.selected_villes)]

# Affichage tableau avec CP
st.subheader("Résultats")
st.dataframe(final_villes[["nom", "code_postal", "distance_km"]].reset_index(drop=True))

# Codes postaux à copier
codes_postaux = final_villes["code_postal"].tolist()
resultat_texte = ", ".join(codes_postaux)

st.text_area("Zone de chalandise (codes postaux) :", resultat_texte, height=100)
